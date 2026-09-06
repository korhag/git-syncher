#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# ------------------------------------------------------------
# venvIsReady: Python 3.11+ and Flet with ft.run (0.80+).
# ------------------------------------------------------------
venvIsReady() {
  [[ -x ".venv/bin/python" ]] || return 1
  .venv/bin/python -c "import sys, flet as ft; raise SystemExit(0 if sys.version_info >= (3, 11) and hasattr(ft, 'run') else 1)" 2>/dev/null
}

if ! venvIsReady; then
  echo "Virtual environment missing or incompatible (need Python 3.11+ and Flet 0.80+)."
  echo "Running install.sh..."
  echo
  bash ./install.sh
  echo
fi

if ! venvIsReady; then
  echo "[ERROR] Still cannot start. Install Python 3.11+ and run ./install.sh" >&2
  exit 1
fi

exec .venv/bin/python -m app.main
