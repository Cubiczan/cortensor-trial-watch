# FINDINGS — OpenMinion 0.1.4 SDK, built for Cortensor Hackathon #5

Model used for real runs: OpenAI `gpt-4o-mini` (also tried `gpt-4.1-mini`, `gpt-5-mini`) via
OpenMinion's `openai` provider. Date: 2026-10-13. Recorded outputs: `runs/`.

## SDK features tested
| Feature | Result |
| --- | --- |
| `openminion setup --no-chat --provider openai --model …` into a project-local `--home-root` | ✅ works; config contains no secrets (`api_key_env`) |
| `Agent(config_path=…, agent_id=…, model=…)` | ✅ |
| `@tool(name=…, description=…)` typed tools | ⚠️ only after workaround (bug 1, 2) |
| `forced_tools=[…]` | ✅ once tools are visible, the forced tool always runs first |
| `session_id` durable sessions / memory capture | ✅ runs complete; metadata shows memory capture |
| `AgentRunResult.stats` / `.raw["metadata"]` | ✅ very useful for debugging (tokens, tool calls, termination reason) |
| `ProviderError` handling | ✅ |
| `setup --list-providers` shows `cortensor-portal` / `cortensor-router` presets | ✅ (not run: no Portal access yet) |

## Real-run results (gpt-4o-mini, after fixes)
| CSV | Rows | Recurring found | Queued for approval | Savings if approved | Tool errors |
| --- | --- | --- | --- | --- | --- |
| sample-transactions.csv | 46 | 5 | Customer.io (trial→$100), Gym Flex (stale), Netflix (price up) | $156.99/mo | 0 |
| chase-style-card.csv | 130 | 6 | Adobe ($1 trial→$59.99), Peloton (stale), Dropbox (11.99→14.99) | $118.98/mo | 0 |
| smb-checking-debit-credit.csv | 65 | 7 | Customer.io, Notion (trial→team), Zoom (stale), Slack (price up) | $176.49/mo | 0 |
Each run: 2 LLM calls, ~5.1–5.5K input tokens, ~18–20 s. Nothing was cancelled; all entries are `pending_human`.

## What broke (and the fixes)
1. **`@tool` functions passed to `Agent(tools=[…])` are never shown to the model.** `_register_tools_for_run`
   adds the specs to the `ToolRegistry`, but the model-facing surface comes from the binding manager
   (`get_registry_manager().model_provider_specs`) which only knows bootstrap manifests. Result: the entry
   call is sent with **zero tools**, the model replies "I'll analyze that now…" and the turn ends
   (`tool_calls: 0`). The README quickstart (`lookup_order`) also produced no tool call in our test. **Workaround:**
   `register_module_manifest(derive_manifest(fn.tool_family_spec()))` before the run (`register_tool_manifests()`).
2. **Manifest validation rejects plain tool names** (`non-canonical model_tool_id='analyze_transactions'`); only
   built-in ids or `mcp.`/`plugin.` prefixes are accepted, so the tools are named `plugin.trialwatch.*`.
   The decorator should either namespace automatically or document this.
3. **A `str` return value is dropped.** The model saw `{"outputs":{},"summary":"Tool executed successfully"}`
   instead of the JSON string, and invented "Merchant A/B/C". Returning a `dict` fixes it.
4. **A result dict containing `"status": "pending_human"` is counted as a tool error** (`tool_errors: 3` though
   the writes succeeded), which triggered retries and once ended the turn with
   "[act] repeated identical tool calls detected without reaching a final answer". Renaming the key to
   `result` gave `tool_errors: 0`. Reserved result keys should be documented.
5. **Default 90 s `chat_turn_timeout_seconds`** raised `TurnTimeoutError` on a 4-tool turn when retries piled up.
   Raising `runtime.chat_turn_timeout_seconds` to 240 in config (done by `setup.sh`) fixed it; `agent.py` also
   passes `Agent.run(timeout_seconds=240)`.
6. **Workspace root = config directory.** The grounding facts showed `cwd: …/.openminion`, so relative paths
   from the user resolve against the config dir. We resolve CSV paths to absolute before the run.
7. **Prompt routing heuristics:** short prompts (≤8 words) are classified `no_tool_answer` and file-like
   paths as `file_context_request` before tools are considered. Worth surfacing in `stats`.
8. **Overhead:** each turn makes extra control calls (memory-capture `submit_output`, freshness classifier,
   judge) — about 3–4 provider requests per user turn and ~1.4K tokens of runtime system prompt.

## Model behaviour observed
- With real tool output, gpt-4o-mini picked exactly the analyzer's actionable merchants every run.
- **Arithmetic in the final prose is unreliable** (e.g. said $125.18/mo vs true $118.98; $2,077.88/yr vs
  $2,117.88). gpt-4.1-mini once invented monthly costs and dates. Hence: all numbers are computed in Python,
  the approval ledger is written by the tool, and `agent.py` prints that ledger as the source of truth.
- The anti-hallucination guard in `queue_cancellation` (reject merchants not flagged) is cheap and worth it.

## Prepared fix for bug 1 (not submitted upstream)

Reproduced on the installed 0.1.4 tree (2026-10-17), without a model call:

- A plain `@tool(name="lookup_order")` is absent from `collect_execution_tool_schemas` (`requires_explicit_exposure_profile` hides it) and `register_module_manifest(derive_manifest(...))` raises `non-canonical model_tool_id='lookup_order'`.
- `plugin.trialwatch.analyze_transactions` is present in execution schemas via `prompt_visible_runtime_name`, but `get_model_exposure_specs` still returns nothing for it after the manifest is registered, because `_canonical_specs` drops every id outside `ALL_MODEL_TOOL_IDS_SET`, including `plugin.*` / `mcp.*`.

That is why `Agent(tools=[decorated_fn])` sends the entry call with no user tool unless the caller both prefixes `plugin.` and registers a manifest (the workaround still in `agent.py`). The fix belongs in OpenMinion, not in this dependency pin. Patch, notes, and the exposure test are in [upstream/](upstream/). No upstream pull request was opened.

## Delegation building block (RenewalGuard)

`plugin.renewalguard.delegate_pricing_check` calls `openminion.api.handoff.subagent` with `name="pricing-check"` and the fixture price tool. The child does not share the parent's transcript. Percent difference is computed in `pricing.py` before the child runs; the model note is commentary. Offline tests inject the factory. A live audit delegates only when the parent `Agent` is on the stack. No new SDK bug was filed from the delegation path: the child still depends on the bug 1 workaround (`register_tool_manifests`) on stock 0.1.4.

## Feedback / suggestions for Cortensor & OpenMinion
- Fix bug 1 (highest impact: the documented Python quickstart doesn't call tools) and add a test that
  `Agent(tools=[decorated_fn])` exposes the tool in the provider payload.
- Auto-namespace decorated tools (`plugin.<module>.<fn>`) and serialize `str` returns as tool output.
- Expose a `debug=True` / `explain_routing` flag listing the tools actually sent to the model per call.
- Document how `Agent.run(timeout_seconds=…)` relates to `runtime.chat_turn_timeout_seconds`.
- A "lean" mode that skips freshness/memory/judge control calls would cut cost for metered providers like the
  Cortensor network.
- Provide a Gemma 4 Portal preset example in docs so the swap is one command.
