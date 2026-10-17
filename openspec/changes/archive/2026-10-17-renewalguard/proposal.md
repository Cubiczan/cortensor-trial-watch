# Proposal

## Why

Trial Watch already flags trials, price hikes, and forgotten subscriptions, but a fractional CFO needs a standing renewal agent: vendors remembered across runs, deadlines before a charge hits, a second look at current price, and a monthly proposal ledger a human still has to approve. Cortensor Hackathon #5 scores a working OpenMinion workflow and building-block findings, and the deadline is 19 Dec 2026.

## What Changes

- Persist vendors and subscriptions in local storage and respect prior human approvals and rejections, including never re-queueing a rejected cancellation.
- Add a deterministic renewal calendar with cadence-based lead times, cancel-by dates, and alerts such as a renewal inside the lead window with a computed price-change percent.
- Delegate pricing evidence to a second OpenMinion agent (`subagent`) that checks a local price fixture before renewal or renegotiation proposals.
- Export a monthly CFO ledger as CSV and JSON covering proposed cancellations, renewals, and renegotiations.
- Keep the existing human-approval guardrail: the agent never cancels, renews, or pays a vendor. Every proposal stays `pending_human` until a person records a decision, and `executed` stays false.
- Prepare an upstream patch and notes for OpenMinion 0.1.4 bug #1 (decorated `@tool` functions not reaching the model). Do not open an upstream pull request.
- Update the README and replace the demo script with a timed 3-minute RenewalGuard walkthrough.

## Capabilities

### New Capabilities

- `vendor-memory`: Cross-session local memory of vendors, subscriptions, and human decisions.
- `renewal-calendar`: Upcoming renewals, lead-time alerts, and cancel-by deadlines computed in Python.
- `pricing-delegation`: A second OpenMinion pricing-check agent used before renewal decisions.
- `approval-ledger`: Monthly CSV/JSON export of proposed cancellations, renewals, and renegotiations, with the no-execution guardrail.

### Modified Capabilities

- None. This repo has no existing OpenSpec capabilities. Trial Watch behavior (deterministic analysis, hallucination guard, `pending_human` cancellations) stays and is extended.

## Impact

- `analyzer.py` gains renewal-calendar fields and single-charge annual detection. Existing recurring detection for the sample CSVs stays.
- `agent.py` gains memory, delegation, renewal proposals, ledger CLI, and an explicit guardrail constant.
- New modules: `memory.py`, `pricing.py`, `ledger.py`, plus `fixtures/vendor_prices.json`.
- Tests extend the current pytest suite. No model key is required for tests.
- `upstream/` holds the OpenMinion 0.1.4 patch and notes. The installed SDK in this repo is not forked.
- README, DEMO_SCRIPT.md, and FINDINGS.md describe the workflow, the guardrail, and the prepared fix.
