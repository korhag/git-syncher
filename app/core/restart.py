from __future__ import annotations

import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

import flet as ft

from app.core.instance_lock import releaseAppLock
from app.core.shortcuts import launcherPython, projectRoot

# Survive parent exit without CREATE_NO_WINDOW (that freezes Flet GUI).
_CREATE_NEW_PROCESS_GROUP = 0x00000200


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
# Function: _spawnWindows
# Purpose: Start Git Syncher via venv pythonw/python (no cmd console).
# ------------------------------------------------------------
def _spawnWindows(root: Path, page: Optional[ft.Page]) -> bool:
    python = launcherPython(root)
    if python is None:
        return False
    try:
        subprocess.Popen(
            [str(python), "-m", "app.main", "--restart"],
            cwd=str(root),
            creationflags=_CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
        )
    except OSError:
        return False

    # The new process waits for the lock. Let Flet close its viewer and
    # clean up normally, with a hard exit as a fallback.
    _scheduleHardExit(5.0)
    if page is not None:
        try:
            page.window.visible = False
            page.update()
        except Exception:
            pass
        try:
            page.run_task(page.window.destroy)
        except Exception:
            pass
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
        return _spawnWindows(root, page)
    if not (root / ".venv" / "bin" / "python").is_file():
        return False

    # Drop single-instance lock before spawn so the new process can acquire it.
    releaseAppLock()

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
