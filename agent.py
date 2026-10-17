"""RenewalGuard (extends Trial Watch): an OpenMinion agent that finds trials
about to convert, forgotten subscriptions, price hikes, and upcoming renewals,
then drafts cancellations and renewals that a human must approve.

GUARDRAIL: RenewalGuard never cancels, renews, or pays a vendor. It only writes
proposals with status pending_human. A human must approve every cancellation.
`executed` is always false. There is no execute function.
"""
from __future__ import annotations

import argparse
import contextvars
import json
import os
import pathlib
import re
import uuid
from datetime import date, datetime, timedelta, timezone

from openminion import Agent, ProviderError, tool

from analyzer import analyze, load_rows
from ledger import GUARDRAIL, export_ledger
from memory import decision_status, remember_recurring, record_decision
from pricing import run_pricing_subagent

HERE = pathlib.Path(__file__).resolve().parent
STATE = pathlib.Path(os.environ.get("TRIALWATCH_STATE", HERE / ".trialwatch"))
APPROVALS = STATE / "approvals.jsonl"
TRACE = STATE / "tool_trace.jsonl"
DEFAULT_CONFIG = HERE / ".openminion" / ".openminion" / "agents.json"

# Stated in code, the ledger export, and the README. Do not add an executor.
HUMAN_APPROVAL_GUARDRAIL = GUARDRAIL

# Merchants the deterministic analyzer flagged (cancellations) or merely knows
# (renewals). queue_* refuses anything else (guards against model hallucination).
_FLAGGED: dict[str, dict] = {}
_KNOWN: dict[str, dict] = {}
_CALENDAR: dict[str, dict] = {}

_PARENT: contextvars.ContextVar = contextvars.ContextVar("renewalguard_parent", default=None)
_RUN_CONFIG: contextvars.ContextVar = contextvars.ContextVar("renewalguard_config", default=None)
_RUN_MODEL: contextvars.ContextVar = contextvars.ContextVar("renewalguard_model", default=None)


def _log(tool_name: str, **fields) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    with TRACE.open("a") as handle:
        handle.write(json.dumps({"tool": tool_name, **fields}) + "\n")


def _actionable(item: dict) -> list[str]:
    reasons = list(item["flags"])
    if item["stale"]:
        reasons.append("stale: no recent charge, may still be billing/forgotten")
    return reasons


def _read_approvals() -> list[dict]:
    if not APPROVALS.exists():
        return []
    return [json.loads(line) for line in APPROVALS.read_text().splitlines() if line.strip()]


def _write_proposal(entry: dict) -> None:
    # Hard guard: this function cannot record an executed vendor action.
    entry["executed"] = False
    entry["status"] = "pending_human"
    STATE.mkdir(parents=True, exist_ok=True)
    with APPROVALS.open("a") as handle:
        handle.write(json.dumps(entry) + "\n")


@tool(
    name="plugin.trialwatch.analyze_transactions",
    description="Analyze a bank/card CSV (absolute path) and return recurring charges, "
    "flags, actionable items with suggested cancel-by deadlines, and the renewal calendar.",
)
def analyze_transactions(csv_path: str) -> dict:
    path = pathlib.Path(csv_path).expanduser()
    if not path.is_absolute():
        path = (HERE / path).resolve()
    out = analyze(load_rows(path.read_text()))
    stored = remember_recurring(STATE, out["recurring"])
    _FLAGGED.clear()
    _KNOWN.clear()
    _CALENDAR.clear()
    for item in out["recurring"]:
        _KNOWN[item["merchant"].lower()] = item
    for entry in out.get("renewal_calendar") or []:
        _CALENDAR[entry["merchant"].lower()] = entry
    actionable = []
    for item in out["recurring"]:
        reasons = _actionable(item)
        if not reasons:
            continue
        if decision_status(STATE, item["merchant"], "cancel") == "rejected":
            continue
        cancel_by = (date.fromisoformat(item["next_expected"]) - timedelta(days=1)).isoformat()
        _FLAGGED[item["merchant"].lower()] = item
        actionable.append({
            "merchant": item["merchant"],
            "monthly_cost": item["monthly_cost"],
            "reasons": reasons,
            "cancel_by": cancel_by,
        })
    out["actionable"] = actionable
    out["vendor_memory_count"] = len(stored["vendors"])
    _log("analyze_transactions", csv_path=str(path), recurring=len(out["recurring"]),
         actionable=[item["merchant"] for item in actionable])
    return out


def _queue(merchant: str, action: str, reason: str, deadline: str, *, pricing: dict | None = None) -> dict:
    key = merchant.strip().lower()
    if action not in {"cancel", "renew", "renegotiate"}:
        return {
            "ok": False,
            "result": "rejected",
            "error": "action must be cancel, renew, or renegotiate",
            "executed": False,
        }
    prior = decision_status(STATE, merchant, action)
    if prior == "rejected":
        _log("queue_" + action, merchant=merchant, already_rejected=True)
        return {"ok": True, "result": "already_rejected", "merchant": merchant, "action": action, "executed": False}
    if prior == "approved":
        return {"ok": True, "result": "already_decided", "merchant": merchant, "action": action, "executed": False}
    if action == "cancel":
        if _FLAGGED and key not in _FLAGGED:
            _log("queue_cancellation", merchant=merchant, rejected="not in analyzer output")
            return {
                "ok": False,
                "result": "rejected",
                "error": f"{merchant!r} was not flagged by analyze_transactions",
                "valid_merchants": [item["merchant"] for item in _FLAGGED.values()],
                "executed": False,
            }
        source = _FLAGGED.get(key, {})
    else:
        calendar = _CALENDAR.get(key)
        if _KNOWN and key not in _KNOWN:
            return {
                "ok": False,
                "result": "rejected",
                "error": f"{merchant!r} is not a known subscription",
                "executed": False,
            }
        if key in _FLAGGED:
            return {
                "ok": False,
                "result": "rejected",
                "error": f"{merchant!r} is a cancellation candidate; queue a cancellation instead",
                "executed": False,
            }
        if _CALENDAR and (not calendar or not calendar.get("within_lead_time")):
            return {
                "ok": False,
                "result": "rejected",
                "error": f"{merchant!r} is not inside its renewal lead time",
                "executed": False,
            }
        source = _KNOWN.get(key, {})
    if any(
        row["merchant"].lower() == key and row.get("action", "cancel") == action and row["status"] == "pending_human"
        for row in _read_approvals()
    ):
        _log("queue_" + action, merchant=merchant, deduped=True)
        return {"ok": True, "result": "already_queued", "merchant": merchant, "action": action, "executed": False}
    entry = {
        "id": uuid.uuid4().hex[:8],
        "merchant": source.get("merchant", merchant),
        "action": action,
        "reason": reason,
        "deadline": deadline,
        "monthly_cost": source.get("monthly_cost"),
        "status": "pending_human",
        "queued_at": datetime.now(timezone.utc).isoformat(),
        "executed": False,
        "pricing_recommendation": (pricing or {}).get("recommendation"),
        "pricing_delta_pct": (pricing or {}).get("delta_pct"),
    }
    _write_proposal(entry)
    _log("queue_" + action, merchant=merchant, deadline=deadline, action=action)
    result = "queued_for_human_approval" if action == "cancel" else "queued_renewal_for_human_approval"
    return {
        "ok": True,
        "result": result,
        "merchant": entry["merchant"],
        "action": action,
        "deadline": deadline,
        "executed": False,
    }


@tool(
    name="plugin.trialwatch.queue_cancellation",
    description="Queue ONE cancellation for HUMAN approval (never cancels anything). "
    "Merchant must exactly match a merchant from analyze_transactions.actionable. Call once per merchant.",
)
def queue_cancellation(merchant: str, reason: str, deadline: str) -> dict:
    return _queue(merchant, "cancel", reason, deadline)


@tool(
    name="plugin.renewalguard.queue_renewal",
    description="Queue ONE renewal or renegotiation for HUMAN approval (never renews or pays anything). "
    "action is 'renew' or 'renegotiate'. Merchant must be inside the renewal calendar lead time "
    "and must not be an actionable cancellation.",
)
def queue_renewal(merchant: str, action: str, reason: str, deadline: str) -> dict:
    return _queue(merchant, action.strip().lower(), reason, deadline)


@tool(
    name="plugin.renewalguard.delegate_pricing_check",
    description="Delegate a current-price check to the RenewalGuard pricing sub-agent before a renewal "
    "decision. Returns Python-computed list price, percent difference, and recommendation. "
    "Does not cancel, renew, or pay.",
)
def delegate_pricing_check(merchant: str, billed_monthly: float) -> dict:
    result = run_pricing_subagent(
        merchant,
        billed_monthly,
        parent=_PARENT.get(),
        config=_RUN_CONFIG.get(),
        model=_RUN_MODEL.get(),
    )
    _log("delegate_pricing_check", merchant=merchant, recommendation=result.get("recommendation"),
         delegated=result.get("delegated"))
    return result


TOOLS = [analyze_transactions, queue_cancellation, queue_renewal, delegate_pricing_check]

INSTRUCTIONS = (
    "You are RenewalGuard, a frugal CFO agent extending Trial Watch. "
    "You never cancel, renew, or pay a vendor. Every proposal waits for a human. "
    "First call plugin.trialwatch.analyze_transactions with the CSV path. "
    "Then call plugin.renewalguard.delegate_pricing_check once for each renewal_calendar entry "
    "whose within_lead_time is true, passing that merchant and its monthly_cost. "
    "Then call plugin.trialwatch.queue_cancellation exactly once for each entry in `actionable`, "
    "using its exact merchant name and its cancel_by date as deadline. "
    "Then call plugin.renewalguard.queue_renewal once for each within_lead_time merchant that is "
    "NOT in actionable: action is renegotiate when the pricing recommendation is renegotiate, "
    "otherwise renew. Use that calendar entry's cancel_by as the deadline. "
    "Do not queue anything else and do not repeat calls. "
    "Finish with a short ranked list (highest monthly cost first) using only numbers from the tools: "
    "merchant, monthly cost, why, deadline, plus total monthly and annual savings if the proposed "
    "cancellations are approved. State that nothing was cancelled."
)


def register_tool_manifests(tools=TOOLS) -> None:
    """Workaround for OpenMinion 0.1.4: functions passed to Agent(tools=[...]) are added to the
    ToolRegistry but not to the binding manager, so the model never sees them. Registering their
    derived manifests makes them model-visible (needs a `plugin.` prefixed tool name)."""
    from openminion.modules.tool.framework import derive_manifest
    from openminion.modules.tool.runtime.dispatch import get_registry_manager

    manager = get_registry_manager()
    for fn in tools:
        try:
            manager.register_module_manifest(derive_manifest(fn.tool_family_spec()),
                                             source_module="renewalguard")
        except Exception as exc:  # already registered / API changed
            if "duplicate" not in str(exc).lower():
                raise


def apply_human_decision(merchant: str, action: str, status: str, note: str = "") -> dict:
    """Record a person's decision. Does not cancel, renew, or pay the vendor."""
    recorded = record_decision(STATE, merchant, action, status, note)
    if APPROVALS.exists():
        lines = []
        for line in APPROVALS.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            same = row.get("merchant", "").lower() == merchant.strip().lower()
            same = same and row.get("action", "cancel") == action and row.get("status") == "pending_human"
            if same:
                row["status"] = status
                row["decision_note"] = note
                row["executed"] = False
            lines.append(json.dumps(row))
        APPROVALS.write_text(("\n".join(lines) + "\n") if lines else "")
    return recorded


def run_audit(csv: str, *, config: str | None, agent_id: str, model: str | None,
              session_id: str | None = None, timeout: float = 240.0):
    register_tool_manifests()
    csv_abs = str(pathlib.Path(csv).expanduser().resolve())
    parent_token = _RUN_CONFIG.set(config)
    model_token = _RUN_MODEL.set(model)
    try:
        with Agent(config_path=config, agent_id=agent_id, model=model, instructions=INSTRUCTIONS,
                   tools=TOOLS, forced_tools=["plugin.trialwatch.analyze_transactions"],
                   session_id=session_id or f"renewalguard-{uuid.uuid4().hex[:8]}") as agent:
            parent = _PARENT.set(agent)
            try:
                return agent.run(
                    f"Audit subscriptions in the statement at {csv_abs}. "
                    "Queue cancellation and renewal proposals for human approval. Do not execute any of them.",
                    timeout_seconds=timeout,
                )
            finally:
                _PARENT.reset(parent)
    finally:
        _RUN_CONFIG.reset(parent_token)
        _RUN_MODEL.reset(model_token)


def configure_client(client: str | None) -> None:
    """Point state files at one client's books. Empty client uses the shared directory."""
    global STATE, APPROVALS, TRACE
    root = pathlib.Path(os.environ.get("TRIALWATCH_STATE", HERE / ".trialwatch"))
    if client:
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", client.strip()) or "client"
        root = root / "clients" / safe
    STATE = root
    APPROVALS = root / "approvals.jsonl"
    TRACE = root / "tool_trace.jsonl"


def _parse_decision(text: str) -> tuple[str, str, str]:
    merchant, sep, rest = text.partition(":")
    action, eq, status = rest.partition("=")
    if not sep or not eq or not merchant.strip() or not action.strip() or not status.strip():
        raise ValueError(f"decision must look like 'Merchant:cancel=rejected', got {text!r}")
    return merchant.strip(), action.strip().lower(), status.strip().lower()


def _print_ledger() -> None:
    if not APPROVALS.exists():
        print("\nNo proposals yet. Nothing was cancelled.")
        return
    print(f"\nVerified proposal ledger (written by tools, not the model) -> {APPROVALS}:")
    print(HUMAN_APPROVAL_GUARDRAIL)
    rows = _read_approvals()
    for entry in rows:
        cost = entry.get("monthly_cost") or 0
        action = entry.get("action", "cancel")
        print(
            f"  [{entry['status']}] {action:<12} {entry['merchant']:<24} "
            f"${cost:>7}/mo  by {entry.get('deadline')}  executed={entry.get('executed', False)}  - {entry.get('reason')}"
        )
    savings = sum(
        (row.get("monthly_cost") or 0)
        for row in rows
        if row.get("action", "cancel") == "cancel" and row.get("status") != "rejected"
    )
    print(f"  potential savings if cancellations are approved: ${savings:.2f}/mo, ${savings * 12:.2f}/yr.")
    print("  Nothing was cancelled, renewed, or paid.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", nargs="?", help="bank/card CSV to audit (default: samples/sample-transactions.csv)")
    parser.add_argument("--config", default=os.environ.get("OPENMINION_CONFIG", str(DEFAULT_CONFIG)),
                        help="OpenMinion agents.json (created by ./setup.sh; holds no secrets)")
    parser.add_argument("--agent", default=os.environ.get("TRIALWATCH_AGENT", "trialwatch"),
                        help="configured OpenMinion agent profile (e.g. a Cortensor Portal profile)")
    parser.add_argument("--model", default=os.environ.get("TRIALWATCH_MODEL"), help="override model id")
    parser.add_argument("--session", default=None, help="session id (reuse to keep OpenMinion memory across runs)")
    parser.add_argument("--client", default=None, help="client name; keeps a separate local vendor memory and ledger")
    parser.add_argument("--decide", action="append", default=[],
                        help="record a human decision MERCHANT:action=approved|rejected (does not execute it)")
    parser.add_argument("--export-ledger", metavar="YYYY-MM", default=None,
                        help="write the monthly CFO ledger (CSV and JSON) and, with no CSV, exit")
    parser.add_argument("--format", choices=["csv", "json", "both"], default="both")
    args = parser.parse_args()
    configure_client(args.client)
    for item in args.decide:
        merchant, action, status = _parse_decision(item)
        apply_human_decision(merchant, action, status)
        print(f"recorded human decision (not executed): {merchant} {action}={status}")
    if args.export_ledger and not args.csv:
        formats = ("csv", "json") if args.format == "both" else (args.format,)
        written = export_ledger(APPROVALS, STATE / "ledger", args.export_ledger, formats)
        for kind, path in written.items():
            print(f"wrote {kind}: {path}")
        print(HUMAN_APPROVAL_GUARDRAIL)
        return 0
    csv = args.csv or "samples/sample-transactions.csv"
    cfg = args.config if pathlib.Path(args.config).exists() else None
    try:
        res = run_audit(csv, config=cfg, agent_id=args.agent, model=args.model, session_id=args.session)
    except ProviderError as exc:
        print(f"provider failed: {exc.code}: {exc.message}")
        return 1
    print(res.text)
    print(f"\nsession={res.session_id} run_state={res.run_state} stats={json.dumps(res.stats)}")
    _print_ledger()
    if args.export_ledger:
        formats = ("csv", "json") if args.format == "both" else (args.format,)
        written = export_ledger(APPROVALS, STATE / "ledger", args.export_ledger, formats)
        for kind, path in written.items():
            print(f"wrote {kind}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
