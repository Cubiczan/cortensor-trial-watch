"""RenewalGuard behavior that does not need a model or an API key."""
import json
import pathlib
from datetime import date

import agent
import pricing
from analyzer import analyze
from ledger import GUARDRAIL, export_ledger


def _state(monkeypatch, tmp_path):
    monkeypatch.setattr(agent, "STATE", tmp_path)
    monkeypatch.setattr(agent, "APPROVALS", tmp_path / "approvals.jsonl")
    monkeypatch.setattr(agent, "TRACE", tmp_path / "trace.jsonl")


def test_renewal_calendar_alerts_price_rise_inside_lead_time():
    rows = [
        {"date": date(2026, 1, 1), "desc": "DROPBOX PLUS", "amount": -11.99},
        {"date": date(2026, 1, 31), "desc": "DROPBOX PLUS", "amount": -11.99},
        {"date": date(2026, 3, 2), "desc": "DROPBOX PLUS", "amount": -14.99},
        {"date": date(2026, 3, 20), "desc": "GROCERY MART", "amount": -10.00},
    ]
    calendar = {row["merchant"]: row for row in analyze(rows)["renewal_calendar"]}
    entry = calendar["Dropbox Plus"]
    assert entry["within_lead_time"] is True
    assert entry["lead_time_days"] == 14
    assert entry["days_until"] == 12
    assert entry["cancel_by"] == "2026-03-31"
    assert entry["alert"] == "renews in 12 days, price up 25%"


def test_single_annual_charge_is_yearly_and_one_offs_are_not():
    rows = [
        {"date": date(2026, 5, 1), "desc": "AMAZON PRIME ANNUAL", "amount": -139.00},
        {"date": date(2026, 6, 2), "desc": "SHELL OIL 57442", "amount": -48.10},
        {"date": date(2026, 9, 1), "desc": "OFFICE SUPPLIES", "amount": -20.00},
    ]
    by = {row["merchant"]: row for row in analyze(rows)["recurring"]}
    assert list(by) == ["Amazon Prime Annual"]
    assert by["Amazon Prime Annual"]["cadence"] == "yearly"
    calendar = analyze(rows)["renewal_calendar"]
    assert calendar[0]["lead_time_days"] == 30


def test_vendor_memory_persists_and_rejected_cancellation_is_not_requeued(tmp_path, monkeypatch):
    _state(monkeypatch, tmp_path)
    sample = "samples/sample-transactions.csv"
    first = agent.analyze_transactions(sample)
    assert "Customer Io" in {item["merchant"] for item in first["actionable"]}
    assert agent.queue_cancellation("Customer Io", "trial", "2026-10-03")["result"] == "queued_for_human_approval"
    stored = json.loads((tmp_path / "vendors.json").read_text())
    assert "customer io" in stored["vendors"]
    agent.apply_human_decision("Customer Io", "cancel", "rejected", note="keep it")
    second = agent.analyze_transactions(sample)
    assert "Customer Io" not in {item["merchant"] for item in second["actionable"]}
    again = agent.queue_cancellation("Customer Io", "trial", "2026-10-03")
    assert again["result"] == "already_rejected"
    assert again["executed"] is False
    rows = [json.loads(line) for line in (tmp_path / "approvals.jsonl").read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["status"] == "rejected"
    assert rows[0]["executed"] is False
    remembered = json.loads((tmp_path / "vendors.json").read_text())["vendors"]["customer io"]
    assert len(remembered["history"]) == 2
    assert remembered["decisions"]["cancel"]["executed"] is False


def test_price_fixture_recommendations():
    hike = pricing.check_vendor_price("Dropbox Plus", 14.99)
    assert hike["recommendation"] == "renegotiate"
    assert hike["delta_pct"] == 25.02
    assert hike["executed"] is False
    same = pricing.check_vendor_price("Spotify USA", 11.99)
    assert same["recommendation"] == "renew"
    unknown = pricing.check_vendor_price("Totally Unknown Vendor", 9.00)
    assert unknown["recommendation"] == "review"
    assert unknown["list_price_monthly"] is None


def test_pricing_delegation_uses_openminion_subagent(monkeypatch):
    calls = {}

    def fake_subagent(parent, **kwargs):
        calls["parent"] = parent
        calls["kwargs"] = kwargs
        child = type("Child", (), {})()
        calls["child"] = child
        return child

    monkeypatch.setattr("openminion.api.handoff.subagent", fake_subagent)
    parent = object()
    child = pricing.default_pricing_agent_factory(parent=parent, config=None, model="gpt-4o-mini")
    assert child is calls["child"]
    assert child.forced_tools == ["plugin.renewalguard.check_vendor_price"]
    assert calls["parent"] is parent
    assert calls["kwargs"]["name"] == "pricing-check"
    assert pricing.check_vendor_price in calls["kwargs"]["tools"]
    assert "never cancel" in calls["kwargs"]["instructions"]

    class FakeChild:
        name = "pricing-check"
        subagent_context = type("Ctx", (), {"child_agent_id": "pricing-check"})()

        def run(self, message, timeout_seconds=None):
            calls["message"] = message
            calls["timeout"] = timeout_seconds
            return type("Result", (), {"text": "list price is below the bill"})()

    out = pricing.run_pricing_subagent(
        "Dropbox Plus",
        14.99,
        parent=parent,
        agent_factory=lambda **kwargs: FakeChild(),
    )
    assert out["delegated"] is True
    assert out["child_agent_id"] == "pricing-check"
    assert out["recommendation"] == "renegotiate"
    assert out["delta_pct"] == 25.02
    assert out["executed"] is False
    assert "Dropbox Plus" in calls["message"]


def test_direct_fixture_when_no_parent_agent():
    out = pricing.run_pricing_subagent("Netflix", 17.99)
    assert out["delegated"] is False
    assert out["mode"] == "direct_fixture"
    assert out["recommendation"] == "renegotiate"


def test_renewal_proposal_and_monthly_ledger(tmp_path, monkeypatch):
    _state(monkeypatch, tmp_path)
    csv = tmp_path / "books.csv"
    csv.write_text(
        "Date,Description,Amount\n"
        "2026-01-01,SPOTIFY USA,-11.99\n"
        "2026-01-31,SPOTIFY USA,-11.99\n"
        "2026-03-02,SPOTIFY USA,-11.99\n"
        "2026-03-20,GROCERY MART,-10.00\n"
    )
    out = agent.analyze_transactions(str(csv))
    assert out["actionable"] == []
    queued = agent.queue_renewal("Spotify Usa", "renew", "price matches list", "2026-03-31")
    assert queued["result"] == "queued_renewal_for_human_approval"
    assert queued["executed"] is False
    assert agent.queue_renewal("Merchant A", "renew", "nope", "2026-03-31")["result"] == "rejected"
    # A cancellation candidate must not also be queued as a renewal.
    flagged = tmp_path / "flagged.csv"
    flagged.write_text(
        "Date,Description,Amount\n"
        "2026-01-01,DROPBOX PLUS,-11.99\n"
        "2026-01-31,DROPBOX PLUS,-11.99\n"
        "2026-03-02,DROPBOX PLUS,-14.99\n"
        "2026-03-20,GROCERY MART,-10.00\n"
    )
    agent.analyze_transactions(str(flagged))
    assert agent.queue_cancellation("Dropbox Plus", "price up 25%", "2026-03-31")["result"] == "queued_for_human_approval"
    assert agent.queue_renewal("Dropbox Plus", "renegotiate", "also up", "2026-03-31")["result"] == "rejected"

    rows = [json.loads(line) for line in (tmp_path / "approvals.jsonl").read_text().splitlines()]
    assert {row["action"] for row in rows} == {"renew", "cancel"}
    assert all(row["status"] == "pending_human" and row["executed"] is False for row in rows)
    rows[0]["queued_at"] = "2026-10-02T00:00:00+00:00"
    rows[1]["queued_at"] = "2026-11-02T00:00:00+00:00"
    rows[0]["executed"] = True  # a bad write must still export as not executed
    (tmp_path / "approvals.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    written = export_ledger(tmp_path / "approvals.jsonl", tmp_path / "ledger", "2026-10")
    exported = json.loads(written["json"].read_text())
    assert exported["guardrail"] == GUARDRAIL
    assert exported["executed"] is False
    assert len(exported["proposals"]) == 1
    assert exported["proposals"][0]["executed"] is False
    assert exported["proposals"][0]["queued_at"].startswith("2026-10")
    csv_text = written["csv"].read_text()
    assert "executed" in csv_text.splitlines()[0]
    assert "True" not in csv_text
    assert agent.HUMAN_APPROVAL_GUARDRAIL == GUARDRAIL
    assert "never cancels, renews, or pays" in agent.__doc__
    readme = pathlib.Path(__file__).parent.joinpath("README.md").read_text()
    assert "never cancels, renews, or pays" in readme
    assert "pending_human" in readme
