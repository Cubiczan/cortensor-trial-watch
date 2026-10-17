# RenewalGuard — Cortensor Hackathon #5 (OpenMinion 0.1.4 SDK)

RenewalGuard extends Trial Watch into a standing CFO agent. It audits a bank or card CSV for **free trials converting to paid**, **price hikes**, **forgotten subscriptions**, and **upcoming renewals**. It remembers vendors across runs, asks a second OpenMinion agent to check current pricing, and writes a monthly proposal ledger.

**RenewalGuard never cancels, renews, or pays a vendor.** Every proposal is stored with `status: pending_human` and `executed: false`. A human must approve every cancellation. Approving a row in the ledger records the decision only. There is no execute function.

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
