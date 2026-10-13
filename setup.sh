#!/usr/bin/env bash
# Creates a project-local OpenMinion config (no secrets: the key is read from $OPENAI_API_KEY at runtime).
set -euo pipefail
cd "$(dirname "$0")"
PROVIDER="${TRIALWATCH_PROVIDER:-openai}"
MODEL="${TRIALWATCH_MODEL:-gpt-4o-mini}"
[ -d .venv ] || { uv venv .venv && uv pip install -p .venv -r requirements.txt; }
.venv/bin/openminion --home-root .openminion setup --no-chat --provider "$PROVIDER" --model "$MODEL" --agent trialwatch
.venv/bin/python - <<'PY'
import json, pathlib
p = pathlib.Path(".openminion/.openminion/agents.json"); d = json.loads(p.read_text())
d["runtime"]["chat_turn_timeout_seconds"] = 240.0          # default 90s is too short for multi-tool turns
for prov in (d["providers"], d["system"]["providers"]):
    if "openai" in prov: prov["openai"]["tool_call_strategy"] = "native"
p.write_text(json.dumps(d, indent=2))
print("config ready:", p)
PY
