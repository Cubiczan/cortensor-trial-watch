import json
import pathlib

import agent
from analyzer import analyze, load_rows

S = pathlib.Path(__file__).parent / "samples"


def _by(name):
    a = analyze(load_rows((S / name).read_text()))
    return a, {r["merchant"]: r for r in a["recurring"]}


def test_detects_trial_and_stale():
    _, by = _by("sample-transactions.csv")
    assert any("trial" in f for f in by["Customer Io"]["flags"])
    assert by["Gym Flex Membership"]["stale"]
    assert any("price up" in f for f in by["Netflix"]["flags"])


def test_chase_style_card_export():
    a, by = _by("chase-style-card.csv")
    assert any("trial" in f for f in by["Adobe Creative Cld"]["flags"])
    assert any("price up" in f for f in by["Dropbox Plus"]["flags"])
    assert by["Dropbox Plus"]["price_change_pct"] == 25.02
    assert by["Peloton Membership Ny"]["stale"]
    assert by["Nyt Digital Weekly"]["cadence"] == "weekly"
    assert by["Amazon Prime Annual"]["cadence"] == "yearly"
    calendar = {row["merchant"]: row for row in a["renewal_calendar"]}
    assert calendar["Amazon Prime Annual"]["lead_time_days"] == 30
    assert not any(k.startswith(("Shell", "Uber")) for k in by)  # variable spend is not a subscription


def test_debit_credit_columns_and_quarterly():
    a, by = _by("smb-checking-debit-credit.csv")
    assert by["Hiscox Insurance Qtr"]["cadence"] == "quarterly"
    assert any("trial" in f for f in by["Notion Labs Team"]["flags"])
    assert by["Slack Technologies"]["monthly_cost"] == 12.5
    assert by["Zoom Us"]["stale"]
    assert a["totals"]["income"] > 0


def test_queue_guard_rejects_hallucinated_merchant_and_dedupes(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "STATE", tmp_path)
    monkeypatch.setattr(agent, "APPROVALS", tmp_path / "approvals.jsonl")
    monkeypatch.setattr(agent, "TRACE", tmp_path / "trace.jsonl")
    out = agent.analyze_transactions(str(S / "sample-transactions.csv"))
    names = [x["merchant"] for x in out["actionable"]]
    assert set(names) == {"Customer Io", "Gym Flex Membership", "Netflix"}
    assert agent.queue_cancellation("Merchant A", "x", "2026-10-20")["result"] == "rejected"
    assert agent.queue_cancellation("Customer Io", "trial", "2026-10-03")["result"] == "queued_for_human_approval"
    assert agent.queue_cancellation("customer io", "trial", "2026-10-03")["result"] == "already_queued"
    lines = (tmp_path / "approvals.jsonl").read_text().splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["status"] == "pending_human"
