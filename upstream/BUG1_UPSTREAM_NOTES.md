# OpenMinion 0.1.4 — prepared fix for FINDINGS bug #1

**Do not open this as a pull request from the RenewalGuard branch.** It is a separated patch against the OpenMinion 0.1.4 sources. The installed requirement stays `openminion==0.1.4`. RenewalGuard still calls `register_tool_manifests()` so it runs on the stock SDK.

## Bug

`Agent(tools=[function decorated with @tool])` does not show that function to the model.

`_register_tools_for_run` adds the spec to `ToolRegistry` and sets `prompt_visible_runtime_name`. The model-facing surface is `get_model_exposure_specs`, which reads the binding manager. Decorated tools are not in that manager. Two further gates make the documented plain-name quickstart fail even if a caller registers a manifest by hand:

1. `requires_explicit_exposure_profile` hides any name that is not a built-in id and not `plugin.` / `mcp.`. `collect_execution_tool_schemas` then skips it.
2. `validate_manifest` rejects that same plain name (`non-canonical model_tool_id='lookup_order'`).
3. `_canonical_specs` drops every id outside `ALL_MODEL_TOOL_IDS_SET`, including valid dynamic `plugin.*` ids, so a manifest that does register still does not appear on the canonical exposure list.

## Reproduction (stock 0.1.4, no model call)

```text
tools ['lookup_order', 'plugin.trialwatch.analyze_transactions']
exposure [] count 0
schema count 1
has lookup False
has analyze True
reg fail lookup_order ToolRuntimeError ... non-canonical model_tool_id='lookup_order'
registered analyze_transactions
exposure after manifest interesting [] count 0
schema has lookup False analyze True
```

`tests/api/test_decorated_tool_exposure.py` on stock 0.1.4 fails at `lookup_order.tool_decl.name == "plugin.user.lookup_order"` because the decorator still keeps the plain name. On the patched tree the same test passes.

## Fix in this patch

`upstream/openminion-0.1.4-bug1-decorated-tools-not-exposed.patch`

- `openminion/tools/decorator.py` — plain names become `plugin.user.<fn>`. Names that are already canonical or `plugin.` / `mcp.` are unchanged, so RenewalGuard's `plugin.trialwatch.*` tools stay as written.
- `openminion/api/agent.py` — for the duration of the run, register each decorated family's manifest and JSON schema on the binding manager, then unregister both. `forced_tools=["lookup_order"]` is rewritten to the namespaced id. A non-canonical handoff id is skipped instead of failing the run.
- `openminion/modules/tool/exposure/__init__.py` — keep dynamic `plugin.` / `mcp.` ids in `_canonical_specs`.
- `openminion/modules/tool/runtime/manager.py` — `unregister_manifest` so the temporary manifest does not leak into the next run.
- `tests/api/test_decorated_tool_exposure.py` — asserts the plain `@tool` is exposed as `plugin.user.lookup_order` with an `order_id` parameter, disappears after unregister, and can be registered again.

`patch -p1 --dry-run` against the 0.1.4 copies of those files succeeded.

## How to try it

```bash
# from a checkout of the OpenMinion repo at the 0.1.4 tag
patch -p1 < path/to/openminion-0.1.4-bug1-decorated-tools-not-exposed.patch
python -m pytest tests/api/test_decorated_tool_exposure.py -q
```

Observed here on 2026-10-17:

- Patched tree: `1 passed`.
- Stock 0.1.4, same test: `1 failed` (`lookup_order` was not namespaced).

## Suggested upstream PR (for a human to open later)

Title: `Expose decorated Agent tools on the model surface`

Body sketch:

> `Agent(tools=[@tool fn])` registers the callable on `ToolRegistry` only. `get_model_exposure_specs` reads binding-manager manifests and then drops non-built-in ids, so the entry call goes out with zero user tools. Plain names also fail `validate_manifest`.
>
> This patch namespaces plain decorator names to `plugin.user.<fn>`, registers and unregisters that manifest for the run, publishes the args-model schema, and keeps dynamic ids in `_canonical_specs`. `tests/api/test_decorated_tool_exposure.py` covers a `lookup_order` tool through register and unregister.

Link the original report in this repo's FINDINGS.md (bug 1) when that PR is opened. A report alone does not earn the hackathon fix bonus; this file is the prepared fix, not the submission.
