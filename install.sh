#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

echo "========================================"
echo " Git Syncher - Linux/macOS install"
echo "========================================"
echo

if command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON=python
else
  echo "[ERROR] Python 3 was not found."
  echo "Install Python 3.11+ (e.g. sudo apt install python3 python3-venv python3-pip)"
  exit 1
fi

"$PYTHON" --version
echo

if command -v git >/dev/null 2>&1; then
  git --version
  echo
else
  echo "[WARN] Git was not found on PATH."
  echo "Install Git (e.g. sudo apt install git / brew install git)"
  echo "The app needs Git to sync projects."
  echo
fi

echo "Creating virtual environment (.venv)..."
if [[ -x ".venv/bin/python" ]]; then
  echo ".venv already exists - reusing it."
else
  "$PYTHON" -m venv .venv
fi

echo "Upgrading pip..."
.venv/bin/python -m pip install --upgrade pip

echo "Installing dependencies from requirements.txt..."
.venv/bin/python -m pip install -r requirements.txt

chmod +x run.sh install.sh 2>/dev/null || true

echo
echo "========================================"
echo " Install complete."
echo " Start the app with:  ./run.sh"
echo "========================================"
