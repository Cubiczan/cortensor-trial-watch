Name
RenewalGuard — Trial Watch for Cortensor

Tagline / one-liner
An OpenMinion agent that watches SaaS trials and renewals, remembers every vendor across sessions, checks pricing with a delegated sub-agent, and prepares a monthly CFO approval ledger — but never cancels, renews, or pays without a human.

Description
Free trials and annual SaaS invoices do not announce themselves. A $1 trial becomes $59.99, a seat that nobody opened keeps billing, and a price step of 25% lands on the card before anyone compares it to the current list price. A fractional CFO watching several small clients cannot hold every vendor, every cancel-by date, and last month's "keep this one" decision in their head. The money leaks because the renewal is silent.

RenewalGuard extends Trial Watch into one repeatable CFO workflow.

Audit. Read a bank or card CSV and flag trials that converted, price hikes, forgotten subscriptions, and upcoming renewals. Cadence, lead time, and percents are computed in Python.

Cross-session vendor memory. Every vendor and subscription is stored in .trialwatch/vendors.json (or a per-client directory). A cancellation a human already rejected is not queued again on the next run.

Renewal calendar. Upcoming charges carry lead-time alerts (weekly 3 days, monthly 14, quarterly 21, yearly 30) and a cancel-by date the day before the charge. A single annual invoice is treated as a yearly renewal.

Delegated pricing check. Before a renewal decision, the parent agent calls OpenMinion subagent() to run a second agent, pricing-check, against a local price fixture. The percent versus list price comes from Python, not from the model's arithmetic.

Monthly CFO ledger. Export a month of proposed cancellations, renewals, and renegotiations as CSV and JSON.

Guardrail. Every proposal is pending_human with executed: false. RenewalGuard never cancels, renews, or pays a vendor. Recording an approval does not contact the vendor. There is no execute function.

How it uses OpenMinion 0.1. The workflow is an OpenMinion 0.1.4 Agent, not a prompt wrapped around a script. @tool exposes the analyzer, the cancellation queue, the renewal queue, and the pricing handoff. forced_tools runs the deterministic audit before the model reasons. session_id keeps the OpenMinion session. subagent() builds the pricing-check child with its own instructions and tool list. ProviderError and AgentRunResult.stats cover provider failures and token or tool-call counts. The same agent swaps to Cortensor Portal or Router with one setup command when that access is granted.

Findings. FINDINGS.md records five OpenMinion 0.1.4 / Cortensor SDK bugs from real model runs: (1) decorated @tool functions passed to Agent(tools=[...]) are never shown to the model; (2) manifest validation rejects plain tool names unless they use an mcp. or plugin. prefix; (3) a str return value is dropped, so the model invents merchants; (4) a result key named status (including pending_human) is counted as a tool error; (5) the default 90-second turn timeout fires on a multi-tool turn. Bug #1 is the highest-impact break. A prepared upstream patch, not applied to the pinned SDK and not opened as an upstream pull request, is in upstream/ (openminion-0.1.4-bug1-decorated-tools-not-exposed.patch and BUG1_UPSTREAM_NOTES.md). This repo still uses register_tool_manifests() so stock 0.1.4 runs.

Demo. DEMO_SCRIPT.md is the timed 3-minute video script: the silent-renewal problem, one SMB audit, a second run that respects last month's rejection, the delegated pricing check on a 25% hike, the approval ledger, and the findings plus the prepared fix. Nothing is cancelled on camera.

Tests. pytest on stock OpenMinion 0.1.4, with no model and no API key: 11 passed. The transcript is TEST_OUTPUT.md.

Hackathon. Cortensor Hackathon #5 on DoraHacks (https://dorahacks.io/hackathon/2418/detail). Deadline 19 December 2026, 2:59 AM ET.

AI use: this project was built with AI assistance (Cursor cloud agent, Grok). The hackathon allows that. The workflow, the guardrail, and the tests are in this repository so a reviewer can re-run them and the builder can explain the work.

GitHub
https://github.com/Cubiczan/cortensor-trial-watch

Tech stack
Python, OpenMinion 0.1.4 SDK (Agent, @tool, forced_tools, session_id, subagent), pytest, local JSON vendor memory and CSV/JSON ledger, OpenAI gpt-4o-mini for development runs, Cortensor Portal / Router (Gemma 4) via the built-in provider preset when access is granted.
