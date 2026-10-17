# RenewalGuard — Trial Watch for Cortensor

An OpenMinion agent that watches SaaS trials and renewals, remembers every vendor across sessions, checks pricing with a delegated sub-agent, and prepares a monthly CFO approval ledger — but never cancels, renews, or pays without a human.

## The problem

Free trials and annual SaaS invoices do not announce themselves. A $1 trial becomes $59.99, a seat that nobody opened keeps billing, and a price step of 25% lands on the card before anyone compares it to the current list price. A fractional CFO watching several small clients cannot hold every vendor, every cancel-by date, and last month's "keep this one" decision in their head. The money leaks because the renewal is silent.

## What it does

RenewalGuard extends Trial Watch into one repeatable CFO workflow:

- **Audit.** Read a bank or card CSV and flag trials that converted, price hikes, forgotten subscriptions, and upcoming renewals. Cadence, lead time, and percents are computed in Python.
- **Cross-session vendor memory.** Every vendor and subscription is stored in `.trialwatch/vendors.json` (or a per-client directory). A cancellation a human already rejected is not queued again on the next run.
- **Renewal calendar.** Upcoming charges carry lead-time alerts (weekly 3 days, monthly 14, quarterly 21, yearly 30) and a cancel-by date the day before the charge. A single annual invoice is treated as a yearly renewal.
- **Delegated pricing check.** Before a renewal decision, the parent agent calls OpenMinion `subagent()` to run a second agent, `pricing-check`, against a local price fixture. The percent versus list price comes from Python, not from the model's arithmetic.
- **Monthly CFO ledger.** `--export-ledger YYYY-MM` writes CSV and JSON of proposed cancellations, renewals, and renegotiations.
- **Guardrail.** Every proposal is `pending_human` with `executed: false`. RenewalGuard never cancels, renews, or pays a vendor. Recording an approval does not contact the vendor. There is no execute function.

## How it uses OpenMinion 0.1

The workflow is an OpenMinion 0.1.4 `Agent`, not a prompt wrapped around a script. `@tool` exposes the analyzer, the cancellation queue, the renewal queue, and the pricing handoff. `forced_tools` runs the deterministic audit before the model reasons. `session_id` keeps the OpenMinion session. `subagent()` builds the pricing-check child with its own instructions and tool list. `ProviderError` and `AgentRunResult.stats` cover provider failures and token or tool-call counts. The same agent swaps to Cortensor Portal or Router with one `setup.sh` command when that access is granted.

## Findings

[FINDINGS.md](FINDINGS.md) records five OpenMinion 0.1.4 / Cortensor SDK bugs from real model runs, plus the workarounds that made the agent reliable:

1. Decorated `@tool` functions passed to `Agent(tools=[…])` are never shown to the model.
2. Manifest validation rejects plain tool names unless they use an `mcp.` or `plugin.` prefix.
3. A `str` return value is dropped, so the model invents merchants.
4. A result key named `status` (including `pending_human`) is counted as a tool error.
5. The default 90-second turn timeout fires on a multi-tool turn.

Bug #1 is the highest-impact break: the documented quickstart sends the entry call with zero user tools. A prepared upstream patch, not applied to the pinned SDK and not opened as an upstream pull request, is in [upstream/](upstream/) (`openminion-0.1.4-bug1-decorated-tools-not-exposed.patch` and `BUG1_UPSTREAM_NOTES.md`). This repo still uses `register_tool_manifests()` so stock 0.1.4 runs.

## Demo

[DEMO_SCRIPT.md](DEMO_SCRIPT.md) is the timed 3-minute video script: the silent-renewal problem, one SMB audit, a second run that respects last month's rejection, the delegated pricing check on a 25% hike, the approval ledger, and the findings plus the prepared fix. Record from that script. Nothing is cancelled on camera.

## Tests

`pytest` on stock OpenMinion 0.1.4, with no model and no API key: **11 passed**. The transcript is [TEST_OUTPUT.md](TEST_OUTPUT.md). The suite covers the original trial, stale, price, and hallucination guards, plus vendor memory, the renewal alert, the pricing sub-agent factory, and a monthly ledger whose `executed` flag stays false.

## Hackathon

Cortensor Hackathon #5 on DoraHacks (https://dorahacks.io/hackathon/2418/detail). Build a small working agent with the OpenMinion 0.1 Python SDK, one repeatable workflow, a real model-backed run, and a written account of the building blocks that broke. Deadline 19 December 2026, 2:59 AM ET.

**AI use:** this project was built with AI assistance (Cursor cloud agent, Grok). The hackathon allows that. The workflow, the guardrail, and the tests are in this repository so a reviewer can re-run them and the builder can explain the work.

The same BUIDL fields, ready to paste into the DoraHacks form, are in [BUIDL.md](BUIDL.md).

---

## Setup
```bash
uv venv .venv && uv pip install -p .venv -r requirements.txt   # openminion==0.1.4, pytest
cp .env.example .env    # put your OPENAI_API_KEY in .env (gitignored), then:
set -a; source .env; set +a
./setup.sh              # writes a project-local OpenMinion config to .openminion/ (no secrets inside)
```
`setup.sh` runs `openminion setup --provider openai --model gpt-4o-mini --agent trialwatch` into a
project-local home, then sets `tool_call_strategy=native` and a 240 s turn timeout. The API key is
only ever read from the `OPENAI_API_KEY` environment variable. The pricing sub-agent shares that
runtime via OpenMinion `subagent()`; it does not need a second setup profile.

## Usage
```bash
.venv/bin/pytest -q                                            # deterministic tests (no model, no key)
.venv/bin/python agent.py samples/sample-transactions.csv      # real model run
.venv/bin/python agent.py samples/smb-checking-debit-credit.csv --client acme --session acme
.venv/bin/python agent.py --client acme --decide "Customer Io:cancel=rejected"
.venv/bin/python agent.py --client acme --export-ledger 2026-10
```
`--decide` records a human approval or rejection (`MERCHANT:action=approved|rejected`). It does not contact the vendor. A rejected cancellation is not queued again on the next run.

`--export-ledger YYYY-MM` writes `cfo-ledger-YYYY-MM.csv` and `.json` under `.trialwatch/ledger/` (or `.trialwatch/clients/<client>/ledger/`). The export repeats the guardrail and forces `executed` to false.

`--client` keeps a separate vendor memory and ledger for each set of books. `--session` is still the OpenMinion session id.

Samples (all fictional): `sample-transactions.csv` (ISO dates, signed amounts),
`chase-style-card.csv` (MM/DD/YYYY card export, weekly + monthly + annual charges, variable spend noise),
`smb-checking-debit-credit.csv` (YYYY/MM/DD, separate Debit/Credit columns, quarterly insurance).
Regenerate with `python samples/generate_synthetic.py`. Recorded real runs of the original Trial Watch audit are in `runs/`.

## How it uses the OpenMinion SDK
```
Agent(config_path, agent_id="trialwatch", instructions, tools=[...], forced_tools=[analyze], session_id)
  └─ turn 1 (forced tool) ── plugin.trialwatch.analyze_transactions(csv_path)
        deterministic analyzer.py: parse the CSV → cadence → flags → renewal calendar
        memory.py writes .trialwatch/vendors.json (decisions survive the next process)
  └─ model loop
        plugin.renewalguard.delegate_pricing_check(merchant, billed_monthly)
            subagent(parent, name="pricing-check")  ← second OpenMinion agent
              └─ plugin.renewalguard.check_vendor_price  (local fixtures/vendor_prices.json)
            numeric result is the Python comparison, not the model's arithmetic
        plugin.trialwatch.queue_cancellation(...)     cancellation proposals only
        plugin.renewalguard.queue_renewal(...)        renew / renegotiate proposals only
  └─ final answer ───────── ranked list; agent.py prints the tool-written ledger
```
- **`@tool`** turns plain Python functions into typed tools.
- **`forced_tools`** guarantees the analysis runs before the model reasons about anything.
- **`subagent()`** is the delegation building block: the pricing check is a child agent with its own instructions and tool allow-list, not a second call hidden inside the parent prompt.
- **`session_id`** (`--session`) is OpenMinion's session memory. Vendor decisions are also stored locally so a rejected cancellation cannot be re-queued if the model session is new.
- **`ProviderError`** is caught for clean provider failures; `AgentRunResult.stats` reports tokens and tool calls.
- Numbers (cadence, lead time, price-change percent, list-price delta) are computed in Python.
- `register_tool_manifests()` in `agent.py` is still required on stock OpenMinion 0.1.4. A prepared upstream fix for that bug is in [upstream/](upstream/) and is not applied to the installed package.

Lead times on the renewal calendar: weekly 3 days, monthly 14, quarterly 21, yearly 30. Cancel-by is the day before the next expected charge. A single charge is treated as yearly only when the description says annual or yearly.

## Swap in Cortensor (bonus)
The agent is provider-agnostic. Once Cortensor Portal / Router access is granted,
export `CORTENSOR_API_KEY` and run
`TRIALWATCH_PROVIDER=cortensor-portal TRIALWATCH_MODEL=<gemma-4 model id> ./setup.sh`
(OpenMinion's built-in preset, endpoint `https://api.cortensor.app/v1`; use `cortensor-router` for a
direct router node), then run the same commands. No code changes are needed. Gemma 4 via Cortensor is the intended
production model; OpenAI `gpt-4o-mini` was used for development runs.

## Building Blocks Tested / What We Learned
See [FINDINGS.md](FINDINGS.md). The upstream patch for bug #1 is [upstream/BUG1_UPSTREAM_NOTES.md](upstream/BUG1_UPSTREAM_NOTES.md).

## AI use
This extension was implemented with AI assistance (Cursor cloud agent, Grok). The workflow, guardrail, and tests are in this repo so a reviewer can re-run them. The hackathon allows AI-assisted development; the builder still needs to be able to explain the agent.
