from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional

import flet as ft

from app.core.instance_lock import releaseAppLock


# ------------------------------------------------------------
# Function: projectRoot
# Purpose: Resolve the repo root (folder that contains run.bat / run.sh).
# ------------------------------------------------------------
def projectRoot() -> Path:
    return Path(__file__).resolve().parents[2]


# ------------------------------------------------------------
# Function: restartApp
# Purpose: Launch run.bat (Windows) or run.sh (Unix), then exit this process.
# Input: page (optional) - Flet page to close before exit.
# Output: bool - False if the launch script is missing.
# ------------------------------------------------------------
def restartApp(page: Optional[ft.Page] = None) -> bool:
    root = projectRoot()
    if os.name == "nt":
        script = root / "run.bat"
        if not script.is_file():
            return False
    else:
        script = root / "run.sh"
        if not script.is_file():
            return False

    # Drop single-instance lock before spawn so the new process can acquire it.
    releaseAppLock()

    if os.name == "nt":
        # New console so the restarted app survives after this process exits.
        subprocess.Popen(
            ["cmd.exe", "/c", str(script)],
            cwd=str(root),
            creationflags=subprocess.CREATE_NEW_CONSOLE | subprocess.CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
        )
    else:
        subprocess.Popen(
            ["bash", str(script)],
            cwd=str(root),
            start_new_session=True,
            close_fds=True,
        )

    if page is not None:
        try:
            page.window.close()
        except Exception:
            pass

    # Hard exit so Flet / threads do not keep the old instance alive.
    os._exit(0)
    return True  # unreachable; keeps type checkers calm
