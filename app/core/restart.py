from __future__ import annotations

import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

import flet as ft

from app.core.instance_lock import releaseAppLock

# Survive parent exit without CREATE_NO_WINDOW (that freezes Flet GUI).
_CREATE_NEW_PROCESS_GROUP = 0x00000200


# ------------------------------------------------------------
# Function: projectRoot
# Purpose: Resolve the repo root (folder that contains run.bat / run.sh).
# ------------------------------------------------------------
def projectRoot() -> Path:
    return Path(__file__).resolve().parents[2]


# ------------------------------------------------------------
# Function: _scheduleHardExit
# Purpose: Daemon thread sleeps briefly then os._exit (safety net).
# ------------------------------------------------------------
def _scheduleHardExit(delay_seconds: float = 1.0) -> None:
    def hard_exit() -> None:
        time.sleep(delay_seconds)
        os._exit(0)

    threading.Thread(target=hard_exit, daemon=True).start()


# ------------------------------------------------------------
# Function: _windowsPython
# Purpose: Prefer pythonw.exe (no console); else python.exe.
# ------------------------------------------------------------
def _windowsPython(root: Path) -> Optional[Path]:
    pythonw = root / ".venv" / "Scripts" / "pythonw.exe"
    if pythonw.is_file():
        return pythonw
    python = root / ".venv" / "Scripts" / "python.exe"
    if python.is_file():
        return python
    return None


# ------------------------------------------------------------
# Function: _spawnWindows
# Purpose: Start Git Syncher via venv pythonw/python (no cmd console).
# ------------------------------------------------------------
def _spawnWindows(root: Path) -> bool:
    python = _windowsPython(root)
    if python is None:
        return False
    # CREATE_NEW_PROCESS_GROUP only — CREATE_NO_WINDOW freezes Flet.
    subprocess.Popen(
        [str(python), "-m", "app.main"],
        cwd=str(root),
        creationflags=_CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
    )
    return True


# ------------------------------------------------------------
# Function: _spawnUnix
# Purpose: Start a new Git Syncher process detached from this session.
# ------------------------------------------------------------
def _spawnUnix(root: Path) -> bool:
    venv_python = root / ".venv" / "bin" / "python"
    if not venv_python.is_file():
        return False
    subprocess.Popen(
        [str(venv_python), "-m", "app.main"],
        cwd=str(root),
        start_new_session=True,
        close_fds=True,
    )
    return True


# ------------------------------------------------------------
# Function: restartApp
# Purpose: Launch a new instance, hide this window, then hard-exit.
# Input: page (optional) - Flet page to hide before exit.
# Output: bool - False if no venv interpreter found.
# ------------------------------------------------------------
def restartApp(page: Optional[ft.Page] = None) -> bool:
    root = projectRoot()
    if os.name == "nt":
        can_launch = _windowsPython(root) is not None
    else:
        can_launch = (root / ".venv" / "bin" / "python").is_file()
    if not can_launch:
        return False

    # Drop single-instance lock before spawn so the new process can acquire it.
    releaseAppLock()

    if os.name == "nt":
        if not _spawnWindows(root):
            return False
    else:
        if not _spawnUnix(root):
            return False

    # Delayed hard-exit after child has time to take the lock and paint.
    _scheduleHardExit(1.0)

    if page is not None:
        try:
            page.window.visible = False
            page.update()
        except Exception:
            pass

    return True
