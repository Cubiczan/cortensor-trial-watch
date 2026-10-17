# Tasks

## 1. Renewal calendar

- [x] 1.1 Add cadence lead times, price-change percent, single-charge annual detection, and `renewal_calendar` on `analyze()` output. Verify with pytest cases for a monthly renewal inside 14 days ("renews in N days, price up 25%"), a yearly annual-keyword charge, and the existing sample CSVs still detecting trials, stale charges, and quarterly cadence.

## 2. Vendor memory

- [x] 2.1 Persist vendors under the state directory and skip re-queueing a cancellation a human already rejected. Verify with a pytest that a second `analyze_transactions` call still lists the merchant and that `queue_cancellation` returns `already_rejected` without a new approval row.

## 3. Pricing sub-agent

- [x] 3.1 Add the local price fixture and Python comparison (`renew` / `renegotiate` / `review`) plus `run_pricing_subagent`, whose default factory calls OpenMinion `subagent` named `pricing-check`. Verify with pytest that a billed amount 25% above list returns `renegotiate`, an unknown merchant returns `review`, and the default factory calls `subagent` with the price-check tool.

## 4. Approval ledger and guardrail

- [x] 4.1 Queue renewal and renegotiation proposals separately from cancellations, export a month as CSV and JSON, and keep `executed` false with the human-approval guardrail in code and the README. Verify with pytest that a hallucinated merchant is rejected, an in-window renewal proposal stays `pending_human`, the export contains that month only, and every exported row has `executed` false.

## 5. Agent workflow, demo, and upstream bug #1

- [x] 5.1 Wire the new tools and CLI (`--session` already exists, add `--client`, `--decide`, `--export-ledger`) without dropping the forced analysis and cancellation guard. Update README, DEMO_SCRIPT.md (timed 3-minute renewal workflow), and FINDINGS.md. Verify by running the full pytest suite and saving the output in TEST_OUTPUT.md.
- [x] 5.2 Prepare a separated OpenMinion 0.1.4 patch and notes for bug #1 under `upstream/`, and run the patch's exposure test against a patched tree. Do not open an upstream pull request. Verify the patched tree exposes `plugin.user.lookup_order` from a plain `@tool` and removes it after the run.
