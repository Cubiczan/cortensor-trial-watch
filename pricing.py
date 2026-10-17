"""Pricing evidence and the OpenMinion pricing-check sub-agent.

Numbers come from the local fixture. The sub-agent may explain them.
It cannot cancel, renew, or pay a vendor.
"""
from __future__ import annotations

import json
import pathlib

from openminion import tool

HERE = pathlib.Path(__file__).resolve().parent
FIXTURE = HERE / "fixtures" / "vendor_prices.json"
# Billed more than this far above list → renegotiate. Otherwise renew (or review).
RENEGOTIATE_OVER_LIST = 1.10

PRICING_INSTRUCTIONS = (
    "You are the RenewalGuard pricing-check sub-agent. "
    "Call plugin.renewalguard.check_vendor_price exactly once with the merchant and billed monthly amount. "
    "Report only the numbers the tool returns. "
    "You never cancel, renew, or pay a vendor. You only compare price."
)


def _load_prices() -> dict:
    payload = json.loads(FIXTURE.read_text())
    return {str(key).strip().lower(): value for key, value in payload.get("prices", {}).items()}


def _merchant_key(merchant: str) -> str:
    return " ".join(merchant.strip().lower().split())


@tool(
    name="plugin.renewalguard.check_vendor_price",
    description="Compare a vendor's billed monthly amount with the local price fixture. "
    "Returns list price, percent difference, and renew/renegotiate/review. Does not change any subscription.",
)
def check_vendor_price(merchant: str, billed_monthly: float) -> dict:
    """Deterministic price comparison. Does not cancel, renew, or pay."""
    billed = round(float(billed_monthly), 2)
    listed = _load_prices().get(_merchant_key(merchant))
    base = {
        "merchant": " ".join(merchant.split()),
        "billed_monthly": billed,
        "source": "fixtures/vendor_prices.json",
        "executed": False,
    }
    if not listed or listed.get("list_price_monthly") is None:
        return {
            **base,
            "list_price_monthly": None,
            "delta_pct": None,
            "plan": None,
            "recommendation": "review",
            "note": "No fixture price for this vendor. Do not invent one. Nothing was cancelled or renewed.",
        }
    list_price = round(float(listed["list_price_monthly"]), 2)
    delta = round((billed - list_price) / list_price * 100, 2) if list_price else None
    if list_price and billed > list_price * RENEGOTIATE_OVER_LIST:
        recommendation = "renegotiate"
    else:
        recommendation = "renew"
    return {
        **base,
        "list_price_monthly": list_price,
        "delta_pct": delta,
        "plan": listed.get("plan"),
        "recommendation": recommendation,
        "note": "Pricing evidence only. Nothing was cancelled, renewed, or paid.",
    }


def default_pricing_agent_factory(*, parent, config, model):
    """Build the second OpenMinion agent. Requires the live parent runtime."""
    from openminion.api.handoff import subagent

    if parent is None:
        raise RuntimeError("pricing sub-agent requires a parent OpenMinion agent")
    child = subagent(
        parent,
        name="pricing-check",
        instructions=PRICING_INSTRUCTIONS,
        tools=[check_vendor_price],
        model=model or getattr(parent, "model", None),
        timeout_seconds=120,
    )
    child.forced_tools = ["plugin.renewalguard.check_vendor_price"]
    return child


def run_pricing_subagent(merchant: str, billed_monthly: float, *, parent=None, config=None,
                         model=None, agent_factory=None) -> dict:
    """Return Python price evidence. Delegate to the sub-agent when a parent is active.

    The model note is explanatory. Callers must use the numeric fields from this dict,
    which were computed before the sub-agent ran.
    """
    evidence = check_vendor_price(merchant, billed_monthly)
    factory = agent_factory
    if factory is None and parent is None:
        return {
            **evidence,
            "delegated": False,
            "mode": "direct_fixture",
            "child_agent_id": None,
        }
    if factory is None:
        factory = default_pricing_agent_factory
    child = factory(parent=parent, config=config, model=model)
    result = child.run(
        (
            f"Check current pricing for {evidence['merchant']} billed at "
            f"{evidence['billed_monthly']} per month. Call the price tool once. "
            "Do not cancel, renew, or pay anything."
        ),
        timeout_seconds=120,
    )
    context = getattr(child, "subagent_context", None)
    child_id = getattr(context, "child_agent_id", None) or getattr(child, "name", "pricing-check")
    return {
        **evidence,
        "delegated": True,
        "mode": "openminion_subagent",
        "child_agent_id": child_id,
        "model_note": (getattr(result, "text", "") or "")[:500],
        "executed": False,
    }
