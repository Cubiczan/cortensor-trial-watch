# Trial Watch — Cortensor Hackathon #5 (OpenMinion 0.1.4 SDK)

An agent that audits a bank/card CSV for **free trials converting to paid**, **price hikes** and
**forgotten subscriptions**, then queues cancellations **for human approval**. It never cancels
anything itself: every action lands in `.trialwatch/approvals.jsonl` with `status: pending_human`.

## Setup
```bash
uv venv .venv && uv pip install -p .venv -r requirements.txt   # openminion==0.1.4, pytest
cp .env.example .env    # put your OPENAI_API_KEY in .env (gitignored), then:
set -a; source .env; set +a
./setup.sh              # writes a project-local OpenMinion config to .openminion/ (no secrets inside)
```
`setup.sh` runs `openminion setup --provider openai --model gpt-4o-mini --agent trialwatch` into a
project-local home, then sets `tool_call_strategy=native` and a 240 s turn timeout. The API key is
only ever read from the `OPENAI_API_KEY` environment variable.

## Usage
```bash
.venv/bin/pytest -q                                            # deterministic tests (no model, no key)
.venv/bin/python agent.py samples/sample-transactions.csv      # real model run
.venv/bin/python agent.py samples/chase-style-card.csv --model gpt-4.1-mini
.venv/bin/python agent.py samples/smb-checking-debit-credit.csv --session my-books   # reuse memory
```
Samples (all fictional): `sample-transactions.csv` (ISO dates, signed amounts),
`chase-style-card.csv` (MM/DD/YYYY card export, weekly + monthly + annual charges, variable spend noise),
`smb-checking-debit-credit.csv` (YYYY/MM/DD, separate Debit/Credit columns, quarterly insurance).
Regenerate with `python samples/generate_synthetic.py`. Recorded real runs are in `runs/`.

## How it uses the OpenMinion SDK
```
Agent(config_path, agent_id="trialwatch", instructions, tools=[...], forced_tools=[analyze], session_id)
  └─ turn 1 (forced tool) ── plugin.trialwatch.analyze_transactions(csv_path)
        deterministic analyzer.py: parse any common CSV layout → group by merchant → cadence
        (weekly/monthly/quarterly/yearly) → flags (trial→paid, price up, stale) → `actionable` + cancel_by
  └─ model loop ─────────── plugin.trialwatch.queue_cancellation(merchant, reason, deadline) × N
        guard: rejects merchants the analyzer did not flag (anti-hallucination), dedupes repeats,
        writes pending_human entries only
  └─ final answer ───────── ranked list + savings; agent.py then prints the tool-written ledger
```
- **`@tool`** turns plain Python functions into typed tools (pydantic arg models from signatures).
- **`forced_tools`** guarantees the analysis runs before the model reasons about anything.
- **`session_id`** gives durable session memory across runs (`--session`).
- **`ProviderError`** is caught for clean provider failures; `AgentRunResult.stats` reports tokens/tool calls.
- Numbers are computed in Python, not by the model; the model chooses and explains actions.
- `register_tool_manifests()` in `agent.py` is a workaround for an SDK 0.1.4 issue (see FINDINGS.md).

## Swap in Cortensor (bonus)
The agent is provider-agnostic. Once Cortensor Portal / Router access is granted, run
export `CORTENSOR_API_KEY` and run
`TRIALWATCH_PROVIDER=cortensor-portal TRIALWATCH_MODEL=<gemma-4 model id> ./setup.sh`
(OpenMinion's built-in preset, endpoint `https://api.cortensor.app/v1`; use `cortensor-router` for a
direct router node), then run the same commands. No code changes are needed. Gemma 4 via Cortensor is the intended
production model; OpenAI `gpt-4o-mini` was used for development runs.

## Building Blocks Tested / What We Learned
See [FINDINGS.md](FINDINGS.md).
