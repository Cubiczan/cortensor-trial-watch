"""Trial Watch: an OpenMinion agent that finds trials about to convert to paid,
forgotten subscriptions and price hikes, then drafts cancel steps that a human
must approve. Nothing is cancelled automatically."""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import uuid
from datetime import date, timedelta

from openminion import Agent, ProviderError, tool

from analyzer import analyze, load_rows

HERE = pathlib.Path(__file__).resolve().parent
STATE = pathlib.Path(os.environ.get("TRIALWATCH_STATE", HERE / ".trialwatch"))
APPROVALS = STATE / "approvals.jsonl"
TRACE = STATE / "tool_trace.jsonl"
DEFAULT_CONFIG = HERE / ".openminion" / ".openminion" / "agents.json"

# Merchants the deterministic analyzer actually flagged in the current run.
# queue_cancellation refuses anything else (guards against model hallucination).
_FLAGGED: dict[str, dict] = {}


def _log(tool_name: str, **fields) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    with TRACE.open("a") as f:
        f.write(json.dumps({"tool": tool_name, **fields}) + "\n")


def _actionable(item: dict) -> list[str]:
    reasons = list(item["flags"])
    if item["stale"]:
        reasons.append("stale: no recent charge, may still be billing/forgotten")
    return reasons


@tool(
    name="plugin.trialwatch.analyze_transactions",
    description="Analyze a bank/card CSV (absolute path) and return recurring charges, "
    "flags, actionable items with suggested cancel-by deadlines, and upcoming renewals.",
)
def analyze_transactions(csv_path: str) -> dict:
    path = pathlib.Path(csv_path).expanduser()
    if not path.is_absolute():
        path = (HERE / path).resolve()
    out = analyze(load_rows(path.read_text()))
    _FLAGGED.clear()
    actionable = []
    for item in out["recurring"]:
        reasons = _actionable(item)
        if not reasons:
            continue
        cancel_by = (date.fromisoformat(item["next_expected"]) - timedelta(days=1)).isoformat()
        _FLAGGED[item["merchant"].lower()] = item
        actionable.append({"merchant": item["merchant"], "monthly_cost": item["monthly_cost"],
                           "reasons": reasons, "cancel_by": cancel_by})
    out["actionable"] = actionable
    _log("analyze_transactions", csv_path=str(path), recurring=len(out["recurring"]),
         actionable=[a["merchant"] for a in actionable])
    return out


@tool(
    name="plugin.trialwatch.queue_cancellation",
    description="Queue ONE cancellation for HUMAN approval (never cancels anything). "
    "Merchant must exactly match a merchant from analyze_transactions.actionable. Call once per merchant.",
)
def queue_cancellation(merchant: str, reason: str, deadline: str) -> dict:
    key = merchant.strip().lower()
    if _FLAGGED and key not in _FLAGGED:
        _log("queue_cancellation", merchant=merchant, rejected="not in analyzer output")
        return {"ok": False, "result": "rejected", "error": f"{merchant!r} was not flagged by analyze_transactions",
                "valid_merchants": [v["merchant"] for v in _FLAGGED.values()]}
    STATE.mkdir(parents=True, exist_ok=True)
    existing = []
    if APPROVALS.exists():
        existing = [json.loads(l) for l in APPROVALS.read_text().splitlines() if l.strip()]
    if any(e["merchant"].lower() == key and e["status"] == "pending_human" for e in existing):
        _log("queue_cancellation", merchant=merchant, deduped=True)
        return {"ok": True, "result": "already_queued", "merchant": merchant}
    item = _FLAGGED.get(key, {})
    entry = {"id": uuid.uuid4().hex[:8], "merchant": item.get("merchant", merchant), "reason": reason,
             "deadline": deadline, "monthly_cost": item.get("monthly_cost"), "status": "pending_human"}
    with APPROVALS.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    _log("queue_cancellation", merchant=merchant, deadline=deadline)
    return {"ok": True, "result": "queued_for_human_approval", "merchant": entry["merchant"], "deadline": deadline}


TOOLS = [analyze_transactions, queue_cancellation]

INSTRUCTIONS = (
    "You are Trial Watch, a frugal finance agent. First call plugin.trialwatch.analyze_transactions "
    "with the CSV path. Then call plugin.trialwatch.queue_cancellation exactly once for each entry in "
    "the tool output's `actionable` list, using its exact merchant name and its cancel_by date as deadline. "
    "Do not queue anything else and do not repeat calls. You never cancel anything; a human approves. "
    "Finish with a short ranked list (highest monthly cost first): merchant, monthly cost, why, cancel-by "
    "date, plus total monthly and annual savings if all are cancelled. Use only numbers from the tool output."
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
                                             source_module="trialwatch")
        except Exception as exc:  # already registered / API changed
            if "duplicate" not in str(exc).lower():
                raise


def run_audit(csv: str, *, config: str | None, agent_id: str, model: str | None,
              session_id: str | None = None, timeout: float = 240.0):
    register_tool_manifests()
    csv_abs = str(pathlib.Path(csv).expanduser().resolve())
    with Agent(config_path=config, agent_id=agent_id, model=model, instructions=INSTRUCTIONS,
               tools=TOOLS, forced_tools=["plugin.trialwatch.analyze_transactions"],
               session_id=session_id or f"trial-watch-{uuid.uuid4().hex[:8]}") as agent:
        return agent.run(f"Audit my subscriptions in the statement at {csv_abs} and queue cancellations.",
                         timeout_seconds=timeout)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("csv", nargs="?", default="samples/sample-transactions.csv")
    ap.add_argument("--config", default=os.environ.get("OPENMINION_CONFIG", str(DEFAULT_CONFIG)),
                    help="OpenMinion agents.json (created by ./setup.sh; holds no secrets)")
    ap.add_argument("--agent", default=os.environ.get("TRIALWATCH_AGENT", "trialwatch"),
                    help="configured OpenMinion agent profile (e.g. a Cortensor Portal profile)")
    ap.add_argument("--model", default=os.environ.get("TRIALWATCH_MODEL"), help="override model id")
    ap.add_argument("--session", default=None, help="session id (reuse to keep memory across runs)")
    a = ap.parse_args()
    cfg = a.config if pathlib.Path(a.config).exists() else None
    try:
        res = run_audit(a.csv, config=cfg, agent_id=a.agent, model=a.model, session_id=a.session)
    except ProviderError as exc:
        print(f"provider failed: {exc.code}: {exc.message}")
        return 1
    print(res.text)
    print(f"\nsession={res.session_id} run_state={res.run_state} stats={json.dumps(res.stats)}")
    if APPROVALS.exists():
        print(f"\nVerified approval queue (written by the tool, not the model) -> {APPROVALS}:")
        for line in APPROVALS.read_text().splitlines():
            e = json.loads(line)
            print(f"  [{e['status']}] {e['merchant']:<24} ${e.get('monthly_cost') or 0:>7}/mo  cancel by {e['deadline']}  - {e['reason']}")
        tot = sum(json.loads(l).get("monthly_cost") or 0 for l in APPROVALS.read_text().splitlines())
        print(f"  potential savings if approved: ${tot:.2f}/mo, ${tot*12:.2f}/yr. Nothing was cancelled.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
