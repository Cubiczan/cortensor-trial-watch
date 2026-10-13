# Trial Watch — demo video script (~2:30)

**0:00–0:15 — Hook.** "Free trials quietly become $100-a-month bills. Trial Watch is an OpenMinion agent
that reads your card statement, finds trials that converted, price hikes and forgotten subscriptions,
and queues cancellations for *you* to approve. It never cancels anything on its own."

**0:15–0:40 — Input.** Show `samples/chase-style-card.csv`: 130 rows, coffee, fuel, rides, plus a $1 Adobe
trial that became $59.99, Dropbox going 11.99→14.99, a Peloton membership that stopped showing up.

**0:40–1:10 — Architecture.** `Agent(...)` with two `@tool`s. `forced_tools` makes the deterministic analyzer
run first (cadence detection, trial/price/stale flags, cancel-by dates). The model then calls
`queue_cancellation` once per flagged merchant. A guard rejects merchants the analyzer didn't flag.

**1:10–1:50 — Live run.** `python agent.py samples/chase-style-card.csv` → model summary → the verified
approval ledger printed from `approvals.jsonl`: Adobe $59.99, Peloton $44, Dropbox $14.99 →
$118.98/mo, $1,427.76/yr. "Status: pending_human. Nothing was cancelled."

**1:50–2:10 — Robustness.** Run `smb-checking-debit-credit.csv` (debit/credit columns, quarterly insurance):
Customer.io and Notion trials, Zoom forgotten, Slack price hike. Show `pytest -q` → 4 passed.

**2:10–2:30 — SDK findings + Cortensor.** "We found and worked around four SDK issues — decorated tools not
reaching the model, name validation, dropped string returns, `status` keys counted as errors — all in
FINDINGS.md. Swap to Cortensor Portal / Gemma 4 with one setup command once access is granted."
