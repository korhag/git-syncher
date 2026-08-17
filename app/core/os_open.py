from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path


# ------------------------------------------------------------
# Function: openFolderInExplorer
# Purpose: Open a folder in the OS file manager (Explorer / Finder / etc.).
# Input: folder_path (str | Path)
# Output: bool - True if the open command was started.
# ------------------------------------------------------------
def openFolderInExplorer(folder_path: str | Path) -> bool:
    path = Path(folder_path)
    if not path.is_dir():
        return False

    resolved = str(path.resolve())
    system = platform.system()
    try:
        if system == "Windows":
            os.startfile(resolved)  # type: ignore[attr-defined]
            return True
        if system == "Darwin":
            subprocess.Popen(["open", resolved])
            return True
        # Linux and other Unix-like
        subprocess.Popen(["xdg-open", resolved])
        return True
    except OSError:
        return False
