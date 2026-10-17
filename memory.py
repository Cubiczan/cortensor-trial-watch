"""Local vendor memory. Survives new processes. Does not cancel or pay anyone."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ACTIONS = ("cancel", "renew", "renegotiate")
DECISIONS = ("approved", "rejected")


def vendors_path(state: Path) -> Path:
    return Path(state) / "vendors.json"


def load_vendors(state: Path) -> dict:
    path = vendors_path(state)
    if not path.exists():
        return {"vendors": {}}
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        return {"vendors": {}}
    data.setdefault("vendors", {})
    return data


def save_vendors(state: Path, data: dict) -> None:
    root = Path(state)
    root.mkdir(parents=True, exist_ok=True)
    vendors_path(root).write_text(json.dumps(data, indent=2) + "\n")


def remember_recurring(state: Path, recurring: list[dict], *, seen_at: str | None = None) -> dict:
    """Merge this run's subscriptions into the local vendor file."""
    data = load_vendors(state)
    now = seen_at or datetime.now(timezone.utc).isoformat()
    for item in recurring:
        key = item["merchant"].strip().lower()
        prev = data["vendors"].get(key, {})
        history = list(prev.get("history") or [])
        history.append({
            "seen": now,
            "monthly_cost": item.get("monthly_cost"),
            "last_amount": item.get("last_amount"),
            "flags": list(item.get("flags") or []),
        })
        data["vendors"][key] = {
            "merchant": item["merchant"],
            "cadence": item.get("cadence"),
            "monthly_cost": item.get("monthly_cost"),
            "last_amount": item.get("last_amount"),
            "last_charge": item.get("last_charge"),
            "next_expected": item.get("next_expected"),
            "flags": list(item.get("flags") or []),
            "first_seen": prev.get("first_seen", now),
            "last_seen": now,
            "history": history[-24:],
            "decisions": dict(prev.get("decisions") or {}),
        }
    save_vendors(state, data)
    return data


def decision_status(state: Path, merchant: str, action: str) -> str | None:
    rec = load_vendors(state)["vendors"].get(merchant.strip().lower())
    if not rec:
        return None
    decision = (rec.get("decisions") or {}).get(action) or {}
    status = decision.get("status")
    return status if status in DECISIONS else None


def record_decision(state: Path, merchant: str, action: str, status: str, note: str = "") -> dict:
    """Store a human decision. This never contacts the vendor."""
    if action not in ACTIONS:
        raise ValueError(f"action must be one of {ACTIONS}")
    if status not in DECISIONS:
        raise ValueError(f"status must be one of {DECISIONS}")
    data = load_vendors(state)
    key = merchant.strip().lower()
    rec = data["vendors"].setdefault(key, {
        "merchant": merchant.strip(),
        "history": [],
        "decisions": {},
    })
    rec.setdefault("decisions", {})
    # executed is always false: approving a proposal does not perform it.
    entry = {
        "status": status,
        "at": datetime.now(timezone.utc).isoformat(),
        "note": note,
        "executed": False,
    }
    rec["decisions"][action] = entry
    save_vendors(state, data)
    return entry
