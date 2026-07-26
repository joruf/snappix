#!/usr/bin/env bash
# Cross-platform guard for Linux hosts.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ -x .venv/bin/python3 ]]; then
  exec .venv/bin/python3 scripts/check_cross_platform.py
elif [[ -x .venv/bin/python ]]; then
  exec .venv/bin/python scripts/check_cross_platform.py
fi
exec python3 scripts/check_cross_platform.py
