#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if command -v uv >/dev/null 2>&1; then
  if [[ ! -d .venv ]]; then uv venv --python 3.13 .venv; fi
  uv pip install --python .venv/bin/python -r backend/requirements.lock
else
  if [[ ! -d .venv ]]; then python3 -m venv .venv; fi
  .venv/bin/python -m pip install -r backend/requirements.lock
fi
.venv/bin/python -m playwright install chromium
npm --prefix frontend ci
printf '\nApp dependencies ready. Run ./scripts/setup-local-models.sh for voice and AI.\n'
