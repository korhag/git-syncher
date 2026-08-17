#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -x ".venv/bin/python" ]]; then
  echo "Virtual environment missing. Running install.sh..."
  echo
  bash ./install.sh
  echo
fi

exec .venv/bin/python -m app.main
