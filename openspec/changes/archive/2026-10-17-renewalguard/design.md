# Design

## Context

Trial Watch is a single OpenMinion 0.1.4 agent. `analyzer.py` detects cadence, trial conversion, price steps, and stale charges. `agent.py` forces `plugin.trialwatch.analyze_transactions`, then the model calls `plugin.trialwatch.queue_cancellation`. Proposals land in `.trialwatch/approvals.jsonl` with `status: pending_human`. Decorated tools reach the model only after `register_tool_manifests()` because of SDK bug #1. See proposal.md for why this becomes RenewalGuard.

## Goals / Non-Goals

**Goals:**

- Keep the current analyzer tests and the hallucination guard.
- Store vendor memory beside the existing state directory.
- Compute renewal dates, lead times, and percents in Python.
- Call OpenMinion `subagent()` for the pricing check when a parent agent is active.
- Export one month of proposals as CSV and JSON.
- Make the no-execution guardrail a constant, a ledger field, and a README statement.
- Ship a separated upstream patch for bug #1, verified against the 0.1.4 sources, without opening an upstream PR.

**Non-Goals:**

- Live web scraping of vendor pricing pages. The sub-agent reads a local fixture.
- A recorded Portal/Gemma 4 run. No Portal key is available.
- Changing OpenMinion inside this repo's runtime dependency (`openminion==0.1.4` stays).
- Auto-cancelling or auto-renewing anything, including after a human marks a proposal approved.

## Decisions

1. **Memory file is `vendors.json` under the state directory.** One JSON document is easier to merge across runs than another jsonl. Decisions are keyed by merchant and action (`cancel`, `renew`, `renegotiate`). Alternative: reuse only OpenMinion `session_id` memory. That memory is model-side and can forget a rejection; the product guard is a local file the queue checks before writing.

2. **Renewal calendar is part of `analyze()`.** Lead times are weekly 3, monthly 14, quarterly 21, yearly 30 days. Cancel-by is the day before `next_expected`. A single charge is yearly only when the description contains annual/yearly wording, so fuel and grocery one-offs stay out. Alternative: a separate calendar pass over the tool output. Keeping it inside `analyze()` means the model and the tests see one deterministic payload.

3. **Pricing numbers are computed before the sub-agent speaks.** `check_vendor_price` compares the billed monthly amount to `fixtures/vendor_prices.json`. Above 10 percent of list → `renegotiate`; missing fixture → `review`; otherwise `renew`. On a live audit the parent calls `openminion.api.handoff.subagent` with name `pricing-check` and that tool. The dict returned to the parent still uses the Python comparison, because model arithmetic is already unreliable (FINDINGS.md). Alternative: let the sub-agent be the only source of the percent. That would put a judged number back in the model.

4. **Proposals share one jsonl.** Cancellations keep `queue_cancellation`. Renewals and renegotiations use `queue_renewal`. Both write `executed: false` and `status: pending_human`. A human decision updates the row and the vendor memory and does not call a vendor. Monthly export filters `queued_at` by `YYYY-MM`.

5. **Bug #1 stays upstream.** Reproduction on 0.1.4: a plain `@tool` name is hidden by `requires_explicit_exposure_profile` and fails manifest validation; `get_model_exposure_specs` drops ids outside `ALL_MODEL_TOOL_IDS_SET`, including `plugin.*`. The patch auto-namespaces plain names to `plugin.user.<fn>`, registers the manifest for the run, and keeps dynamic ids on the canonical exposure surface. This repo keeps the existing `register_tool_manifests()` workaround so 0.1.4 still runs.

## Risks / Trade-offs

- [Sub-agent needs a live model and a parent runtime] → Tests inject the factory and assert `subagent` is the production factory. Offline audits still return the Python price check and label `delegated: false`.
- [Global tool-registry manifests can leak if a run aborts] → The patch unregisters in the same `finally` path as temporary tools. Notes call out the process-global manager.
- [Annual detection could swallow a one-off with the word "annual" in the memo] → The keyword check is limited to annual/yearly/per year, and variable multi-charge merchants still go through the consistency filter.
- [Approving a proposal could be misread as execution] → `executed` is the literal `false` on write and on export, and the README says approval is a note, not a vendor action.

## Migration Plan

Existing `.trialwatch/approvals.jsonl` rows remain valid. New fields (`action`, `queued_at`, `executed`) appear on new rows. Export treats a missing `queued_at` as outside a month filter only when the timestamp is absent; those legacy rows are included when the month argument is omitted. No data migration script. Rollback is reverting the branch; state files are gitignored.

## Open Questions

None that change the spec. Portal/Gemma 4 swap stays the existing `setup.sh` provider switch until access exists.
