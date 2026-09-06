from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional


# ------------------------------------------------------------
# Function: expandFolderPath
# Purpose: Expand ~ and strip quotes so typed paths work.
# ------------------------------------------------------------
def expandFolderPath(raw: str) -> str:
    text = (raw or "").strip().strip('"').strip("'")
    if not text:
        return ""
    return str(Path(text).expanduser())


# ------------------------------------------------------------
# Function: _runDialog
# Purpose: Run a GUI picker. Returns (path, launched).
#          launched is False if the binary could not start.
# ------------------------------------------------------------
def _runDialog(command: list[str], timeout_seconds: int = 600) -> tuple[Optional[str], bool]:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except FileNotFoundError:
        return None, False
    except (OSError, subprocess.TimeoutExpired):
        return None, False
    if result.returncode != 0:
        return None, True
    lines = (result.stdout or "").strip().splitlines()
    if not lines:
        return None, True
    chosen = lines[-1].strip()
    return (chosen or None), True


# ------------------------------------------------------------
# Function: _pickLinux
# Purpose: Zenity / kdialog / yad (Flet FilePicker needs Zenity
#          too, but Flutter often fails under VNC).
# ------------------------------------------------------------
def _pickLinux(title: str, initial_directory: str) -> tuple[Optional[str], bool]:
    start = expandFolderPath(initial_directory)
    if shutil.which("zenity"):
        command = [
            "zenity",
            "--file-selection",
            "--directory",
            f"--title={title}",
        ]
        if start:
            command.append(f"--filename={start.rstrip('/')}/")
        return _runDialog(command)
    if shutil.which("kdialog"):
        return _runDialog(
            ["kdialog", "--getexistingdirectory", start or str(Path.home())]
        )
    if shutil.which("yad"):
        return _runDialog(
            ["yad", "--file-selection", "--directory", f"--title={title}"]
        )
    return None, False


# ------------------------------------------------------------
# Function: _pickMac
# Purpose: Native choose-folder dialog via osascript.
# ------------------------------------------------------------
def _pickMac(title: str) -> tuple[Optional[str], bool]:
    safe_title = title.replace('"', "")
    script = f'POSIX path of (choose folder with prompt "{safe_title}")'
    return _runDialog(["osascript", "-e", script])


# ------------------------------------------------------------
# Function: _pickWindows
# Purpose: WinForms folder browser (STA).
# ------------------------------------------------------------
def _pickWindows(title: str) -> tuple[Optional[str], bool]:
    safe_title = title.replace("'", "")
    script = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "$d = New-Object System.Windows.Forms.FolderBrowserDialog; "
        f"$d.Description = '{safe_title}'; "
        "$d.ShowNewFolderButton = $true; "
        "if ($d.ShowDialog() -eq 'OK') { $d.SelectedPath }"
    )
    return _runDialog(
        ["powershell", "-NoProfile", "-STA", "-Command", script]
    )


# ------------------------------------------------------------
# Function: _pickTkinter
# Purpose: Tcl/Tk directory dialog when other tools are missing.
# ------------------------------------------------------------
def _pickTkinter(title: str, initial_directory: str) -> tuple[Optional[str], bool]:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception:
        return None, False
    start = expandFolderPath(initial_directory)
    root = tk.Tk()
    root.withdraw()
    try:
        root.wm_attributes("-topmost", 1)
    except Exception:
        pass
    try:
        chosen = filedialog.askdirectory(
            parent=root,
            title=title,
            initialdir=start or None,
            mustexist=True,
        )
    except Exception:
        return None, False
    finally:
        try:
            root.destroy()
        except Exception:
            pass
    return (chosen or None), True


# ------------------------------------------------------------
# Function: pickerHelpMessage
# Purpose: What to show when Browse cannot open a dialog.
# ------------------------------------------------------------
def pickerHelpMessage() -> str:
    if sys.platform.startswith("linux"):
        return (
            "Browse needs a folder dialog (install with: sudo apt install zenity). "
            "You can type the folder path instead."
        )
    return "Browse could not open a folder dialog. Type the folder path instead."


# ------------------------------------------------------------
# Function: pickDirectory
# Purpose: Show a native folder picker. Returns (path, error).
#          Success: (path, None). Cancel: (None, None).
#          No dialog available: (None, help text).
# ------------------------------------------------------------
def pickDirectory(
    title: str = "Select folder",
    initial_directory: str = "",
) -> tuple[Optional[str], Optional[str]]:
    if sys.platform == "win32":
        chosen, shown = _pickWindows(title)
        if not shown:
            chosen, shown = _pickTkinter(title, initial_directory)
    elif sys.platform == "darwin":
        chosen, shown = _pickMac(title)
        if not shown:
            chosen, shown = _pickTkinter(title, initial_directory)
    else:
        chosen, shown = _pickLinux(title, initial_directory)
        if not shown:
            chosen, shown = _pickTkinter(title, initial_directory)

    if chosen:
        return expandFolderPath(chosen), None
    if shown:
        return None, None
    return None, pickerHelpMessage()
