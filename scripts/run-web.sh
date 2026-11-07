#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  echo "missing venv; run: uv sync" >&2
  exit 1
fi
exec "$ROOT/.venv/bin/python" -m vic3_mcp.webapp "$@"
