# RenewalGuard — demo video script (3:00)

Reshoot. Do not reuse the Trial Watch `demo.mp4` as the submission video. Screen recording with a terminal and the ledger files is enough. No frontend.

**0:00–0:30 — The leak.** "A fractional CFO watches renewals for several small clients. Trials turn into $100 bills, annual invoices show up once, and last month's 'keep it' decision gets forgotten. RenewalGuard is an OpenMinion agent that remembers the vendors, watches the cancel-by date, and will not cancel anything itself."

**0:30–1:10 — One audit.** `python agent.py samples/smb-checking-debit-credit.csv --client demo --session demo`. Point at the forced tool: the deterministic analyzer flags Customer.io and Notion trials, a stale Zoom seat, and the Slack price hike, and builds the renewal calendar (monthly 14-day lead, quarterly 21, yearly 30). Show `pytest -q` is green before the model run so the numbers are not coming from the model.

**1:10–1:40 — Memory across runs.** `python agent.py --client demo --decide "Customer Io:cancel=rejected"`, then run the same CSV again. The second run does not put Customer.io back on the actionable list. Open `.trialwatch/clients/demo/vendors.json` and show `decisions.cancel.status = rejected` and `executed: false`. "Rejected last month stays rejected. The agent did not cancel it, and it did not ask again."

**1:40–2:10 — Delegated pricing check.** On a renewal inside the lead window (Dropbox on the chase sample, or the synthetic 11.99 → 14.99 case), the parent calls `delegate_pricing_check`. That constructs a second OpenMinion agent with `subagent(..., name="pricing-check")`. The child calls `check_vendor_price` against `fixtures/vendor_prices.json`. The tool, not the model, returns "renegotiate" and about 25% above list. "The sub-agent only brings back a price. It cannot renew or pay."

**2:10–2:40 — The monthly ledger.** `python agent.py --client demo --export-ledger <YYYY-MM>`. Open the CSV and the JSON. Columns: merchant, action (`cancel`, `renew`, or `renegotiate`), reason, deadline, monthly cost, `pending_human`, `executed=false`. Read the guardrail line out loud: nothing was cancelled, renewed, or paid. A human still has to approve every cancellation.

**2:40–3:00 — Findings and the prepared fix.** "A quarter of the score is building blocks. FINDINGS.md has the OpenMinion 0.1.4 bugs we hit, including decorated `@tool`s never reaching the model. `upstream/` has a patch and a test that exposes `plugin.user.lookup_order` on a patched tree and removes it when the run ends. We did not open an upstream PR from this branch. Portal / Gemma 4 is one `setup.sh` command when access lands."
