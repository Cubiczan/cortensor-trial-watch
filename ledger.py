"""Monthly CFO proposal ledger. Nothing in this file cancels, renews, or pays a vendor."""
from __future__ import annotations

import csv
import json
from pathlib import Path

# GUARDRAIL: copied onto every export. Proposals are notes for a human.
GUARDRAIL = (
    "RenewalGuard never cancels, renews, or pays a vendor. "
    "Every row is a proposal. executed is always false. "
    "A human must approve every cancellation."
)

COLUMNS = [
    "id",
    "queued_at",
    "merchant",
    "action",
    "reason",
    "deadline",
    "monthly_cost",
    "status",
    "pricing_recommendation",
    "pricing_delta_pct",
    "executed",
]


def load_approvals(path: Path) -> list[dict]:
    file = Path(path)
    if not file.exists():
        return []
    return [json.loads(line) for line in file.read_text().splitlines() if line.strip()]


def normalize(row: dict) -> dict:
    """Force the guardrail field. A stored true would still export as false."""
    return {
        "id": row.get("id"),
        "queued_at": row.get("queued_at") or "",
        "merchant": row.get("merchant"),
        "action": row.get("action") or "cancel",
        "reason": row.get("reason") or "",
        "deadline": row.get("deadline") or "",
        "monthly_cost": row.get("monthly_cost"),
        "status": row.get("status"),
        "pricing_recommendation": row.get("pricing_recommendation") or "",
        "pricing_delta_pct": row.get("pricing_delta_pct") if row.get("pricing_delta_pct") is not None else "",
        "executed": False,
    }


def select_month(rows: list[dict], month: str | None) -> list[dict]:
    if not month:
        return list(rows)
    return [row for row in rows if str(row.get("queued_at") or "").startswith(month)]


def export_ledger(approvals: Path, dest_dir: Path, month: str | None, formats=("csv", "json")) -> dict[str, Path]:
    rows = [normalize(row) for row in select_month(load_approvals(approvals), month)]
    if any(row["executed"] is not False for row in rows):
        raise RuntimeError("guardrail violated: a ledger row was marked executed")
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    label = month or "all"
    written: dict[str, Path] = {}
    if "json" in formats:
        payload = {
            "month": month,
            "guardrail": GUARDRAIL,
            "executed": False,
            "proposals": rows,
        }
        path = dest / f"cfo-ledger-{label}.json"
        path.write_text(json.dumps(payload, indent=2) + "\n")
        written["json"] = path
    if "csv" in formats:
        path = dest / f"cfo-ledger-{label}.csv"
        with path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        written["csv"] = path
    return written
