#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi

.venv/bin/pip install -q pip -U
.venv/bin/pip install -q "git+https://github.com/agentskills/agentskills.git#subdirectory=skills-ref"

.venv/bin/skills-ref validate skills/manifest

if command -v jq >/dev/null 2>&1 && [[ -f .cursor-plugin/plugin.json ]]; then
  jq empty .cursor-plugin/plugin.json
fi

if command -v jq >/dev/null 2>&1 && [[ -f plugin.json ]]; then
  jq empty plugin.json
fi

echo "cloud-agent-install: ok"
