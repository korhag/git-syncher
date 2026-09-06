#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

MIN_MAJOR=3
MIN_MINOR=11

echo "========================================"
echo " Git Syncher - Linux/macOS install"
echo "========================================"
echo

# ------------------------------------------------------------
# pythonMeetsMin: True if interpreter is Python 3.11+.
# ------------------------------------------------------------
pythonMeetsMin() {
  local bin="$1"
  [[ -x "$bin" ]] || return 1
  "$bin" -c "import sys; raise SystemExit(0 if sys.version_info >= (${MIN_MAJOR}, ${MIN_MINOR}) else 1)" 2>/dev/null
}

# ------------------------------------------------------------
# findSystemPython: First python3.13/3.12/3.11/3 on PATH that is new enough.
# ------------------------------------------------------------
findSystemPython() {
  local candidate
  for candidate in python3.13 python3.12 python3.11 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && pythonMeetsMin "$(command -v "$candidate")"; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

# ------------------------------------------------------------
# ensureUv: Install uv to ~/.local/bin if it is not already on PATH.
# ------------------------------------------------------------
ensureUv() {
  if command -v uv >/dev/null 2>&1; then
    command -v uv
    return 0
  fi
  if [[ -x "${HOME}/.local/bin/uv" ]]; then
    echo "${HOME}/.local/bin/uv"
    return 0
  fi
  if ! command -v curl >/dev/null 2>&1; then
    echo "[ERROR] curl is required to install uv (and a local Python ${MIN_MAJOR}.${MIN_MINOR}+)." >&2
    return 1
  fi
  echo "Installing uv to ~/.local/bin ..." >&2
  curl -LsSf https://astral.sh/uv/install.sh | sh >&2
  if [[ -x "${HOME}/.local/bin/uv" ]]; then
    echo "${HOME}/.local/bin/uv"
    return 0
  fi
  if command -v uv >/dev/null 2>&1; then
    command -v uv
    return 0
  fi
  echo "[ERROR] uv installed but was not found on PATH." >&2
  return 1
}

# ------------------------------------------------------------
# createVenvWithUv: Download CPython 3.12 and create .venv with it.
# ------------------------------------------------------------
createVenvWithUv() {
  local uv_bin
  uv_bin="$(ensureUv)"
  echo "System Python is older than ${MIN_MAJOR}.${MIN_MINOR}."
  echo "Installing a local Python 3.12 with uv..."
  echo
  "$uv_bin" python install 3.12
  "$uv_bin" venv --python 3.12 --seed .venv
}

PYTHON=""
if PYTHON="$(findSystemPython)"; then
  echo "Using $($PYTHON --version 2>&1) ($PYTHON)"
  echo
else
  if command -v python3 >/dev/null 2>&1; then
    python3 --version
  elif command -v python >/dev/null 2>&1; then
    python --version
  else
    echo "[ERROR] Python was not found."
  fi
  echo
  echo "Git Syncher needs Python ${MIN_MAJOR}.${MIN_MINOR}+ (this app uses Flet 0.80+ / ft.run)."
  echo "Debian 11 / Raspberry Pi OS Bullseye only has 3.9 — a local 3.12 will be installed."
  echo
  PYTHON=""
fi

if command -v git >/dev/null 2>&1; then
  git --version
  echo
else
  echo "[WARN] Git was not found on PATH."
  echo "Install Git (e.g. sudo apt install git / brew install git)"
  echo "The app needs Git to sync projects."
  echo
fi

if [[ -x ".venv/bin/python" ]] && ! pythonMeetsMin ".venv/bin/python"; then
  echo "Existing .venv uses $(.venv/bin/python --version 2>&1), which cannot run this app."
  echo "Removing it so a Python ${MIN_MAJOR}.${MIN_MINOR}+ environment can be created."
  echo
  rm -rf .venv
fi

echo "Creating virtual environment (.venv)..."
if [[ -x ".venv/bin/python" ]]; then
  echo ".venv already exists - reusing it ($(.venv/bin/python --version 2>&1))."
else
  if [[ -n "$PYTHON" ]]; then
    "$PYTHON" -m venv .venv
  else
    createVenvWithUv
  fi
fi

if ! pythonMeetsMin ".venv/bin/python"; then
  echo "[ERROR] .venv is still on $(.venv/bin/python --version 2>&1)."
  echo "Install Python ${MIN_MAJOR}.${MIN_MINOR}+ and re-run ./install.sh"
  exit 1
fi

if ! .venv/bin/python -m pip --version >/dev/null 2>&1; then
  echo "pip missing from .venv — bootstrapping with ensurepip..."
  .venv/bin/python -m ensurepip --upgrade
fi

echo "Upgrading pip..."
# Raspberry Pi / Debian often add piwheels, which has a stub flet-web package.
# Ignore pip.conf extra-index-url and install Flet from PyPI.
export PIP_CONFIG_FILE=/dev/null
export PIP_INDEX_URL="https://pypi.org/simple"
unset PIP_EXTRA_INDEX_URL

.venv/bin/python -m pip install --upgrade pip --index-url https://pypi.org/simple

echo "Installing dependencies from requirements.txt..."
.venv/bin/python -m pip install --index-url https://pypi.org/simple -r requirements.txt

chmod +x run.sh install.sh 2>/dev/null || true

echo
echo "========================================"
echo " Install complete."
echo " Start the app with:  ./run.sh"
echo "========================================"
