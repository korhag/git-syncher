from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Hide the PowerShell window that writes the Start Menu shortcut.
_CREATE_NO_WINDOW = 0x08000000

APP_NAME = "Git Syncher"
LINUX_DESKTOP_NAME = "git-syncher.desktop"


# ------------------------------------------------------------
# Class: ShortcutResult
# Purpose: Outcome of writing the Start Menu / application menu icon.
# ------------------------------------------------------------
@dataclass
class ShortcutResult:
    ok: bool
    message: str
    path: Optional[Path] = None
    skipped: bool = False


# ------------------------------------------------------------
# Function: projectRoot
# Purpose: Repo root (folder that contains run.bat / run.sh).
# ------------------------------------------------------------
def projectRoot() -> Path:
    return Path(__file__).resolve().parents[2]


# ------------------------------------------------------------
# Function: consolePython
# Purpose: Venv interpreter for pip and scripts (python.exe, not pythonw).
# ------------------------------------------------------------
def consolePython(root: Path) -> Optional[Path]:
    if os.name == "nt":
        python = root / ".venv" / "Scripts" / "python.exe"
    else:
        python = root / ".venv" / "bin" / "python"
    if python.is_file():
        return python
    return None


# ------------------------------------------------------------
# Function: launcherPython
# Purpose: Interpreter the menu icon should start. Prefers pythonw on Windows.
# ------------------------------------------------------------
def launcherPython(root: Path) -> Optional[Path]:
    if os.name == "nt":
        pythonw = root / ".venv" / "Scripts" / "pythonw.exe"
        if pythonw.is_file():
            return pythonw
        return consolePython(root)
    return consolePython(root)


# ------------------------------------------------------------
# Function: _windowsLauncher
# Purpose: pythonw/python path used by the Windows shortcut, even if tests
#          call this on another operating system.
# ------------------------------------------------------------
def _windowsLauncher(root: Path) -> Optional[Path]:
    pythonw = root / ".venv" / "Scripts" / "pythonw.exe"
    if pythonw.is_file():
        return pythonw
    python = root / ".venv" / "Scripts" / "python.exe"
    if python.is_file():
        return python
    return None


# ------------------------------------------------------------
# Function: _unixLauncher
# Purpose: venv python path used by the Linux .desktop file.
# ------------------------------------------------------------
def _unixLauncher(root: Path) -> Optional[Path]:
    python = root / ".venv" / "bin" / "python"
    if python.is_file():
        return python
    return None


# ------------------------------------------------------------
# Function: _psQuote
# Purpose: Single-quote a string for a PowerShell command.
# ------------------------------------------------------------
def _psQuote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


# ------------------------------------------------------------
# Function: _desktopQuote
# Purpose: Quote one Exec argument for a .desktop file.
# ------------------------------------------------------------
def _desktopQuote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


# ------------------------------------------------------------
# Function: _hiddenProcessKwargs
# Purpose: Windows flags so a helper process does not flash a console.
# ------------------------------------------------------------
def _hiddenProcessKwargs() -> dict:
    if os.name != "nt":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    return {
        "creationflags": _CREATE_NO_WINDOW,
        "startupinfo": startupinfo,
    }


# ------------------------------------------------------------
# Function: _installWindows
# Purpose: Write Git Syncher.lnk into the current user's Start Menu.
# ------------------------------------------------------------
def _installWindows(root: Path) -> ShortcutResult:
    python = _windowsLauncher(root)
    if python is None:
        return ShortcutResult(
            ok=False,
            message="Virtual environment was not found, so the Start Menu shortcut was not created.",
        )

    appdata = os.environ.get("APPDATA", "").strip()
    if not appdata:
        return ShortcutResult(
            ok=False,
            message="APPDATA is not set, so the Start Menu shortcut was not created.",
        )

    programs = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    try:
        programs.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return ShortcutResult(ok=False, message=f"Could not open the Start Menu folder: {exc}")

    link_path = programs / f"{APP_NAME}.lnk"
    icon_path = root / "assets" / "icon.ico"
    lines = [
        "$shell = New-Object -ComObject WScript.Shell",
        f"$shortcut = $shell.CreateShortcut({_psQuote(str(link_path))})",
        f"$shortcut.TargetPath = {_psQuote(str(python))}",
        "$shortcut.Arguments = '-m app.main'",
        f"$shortcut.WorkingDirectory = {_psQuote(str(root))}",
        "$shortcut.WindowStyle = 1",
        f"$shortcut.Description = {_psQuote(APP_NAME)}",
    ]
    if icon_path.is_file():
        lines.append(f"$shortcut.IconLocation = {_psQuote(str(icon_path))}")
    lines.append("$shortcut.Save()")

    try:
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "; ".join(lines),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
            **_hiddenProcessKwargs(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return ShortcutResult(ok=False, message=f"Could not create the Start Menu shortcut: {exc}")

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        if detail:
            return ShortcutResult(
                ok=False,
                message=f"Could not create the Start Menu shortcut: {detail}",
            )
        return ShortcutResult(ok=False, message="Could not create the Start Menu shortcut.")

    return ShortcutResult(
        ok=True,
        message=f"Start Menu shortcut: {link_path}",
        path=link_path,
    )


# ------------------------------------------------------------
# Function: _installLinux
# Purpose: Write a .desktop file into the user application menu.
# ------------------------------------------------------------
def _installLinux(root: Path) -> ShortcutResult:
    python = _unixLauncher(root)
    if python is None:
        return ShortcutResult(
            ok=False,
            message="Virtual environment was not found, so the application menu shortcut was not created.",
        )

    applications = Path.home() / ".local" / "share" / "applications"
    try:
        applications.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return ShortcutResult(
            ok=False,
            message=f"Could not open the application menu folder: {exc}",
        )

    desktop_path = applications / LINUX_DESKTOP_NAME
    icon_path = root / "assets" / "icon.png"
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        "Version=1.1",
        f"Name={APP_NAME}",
        "Comment=Track and sync local Git projects",
        f"Exec={_desktopQuote(str(python))} -m app.main",
        f"Path={root}",
        "Terminal=false",
        "Categories=Development;",
        "StartupNotify=true",
    ]
    if icon_path.is_file():
        lines.append(f"Icon={icon_path}")
    content = "\n".join(lines) + "\n"

    try:
        desktop_path.write_text(content, encoding="utf-8", newline="\n")
    except OSError as exc:
        return ShortcutResult(
            ok=False,
            message=f"Could not write the application menu shortcut: {exc}",
        )

    updater = shutil.which("update-desktop-database")
    if updater:
        try:
            subprocess.run(
                [updater, str(applications)],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            pass

    return ShortcutResult(
        ok=True,
        message=f"Application menu shortcut: {desktop_path}",
        path=desktop_path,
    )


# ------------------------------------------------------------
# Function: installShortcuts
# Purpose: Create or refresh the menu icon for this install.
#          Running it again rewrites the paths (safe after a move).
# Input: root - repo folder. Defaults to this checkout.
# ------------------------------------------------------------
def installShortcuts(root: Optional[Path] = None) -> ShortcutResult:
    folder = (root or projectRoot()).resolve()
    if os.name == "nt":
        return _installWindows(folder)
    if sys.platform == "darwin":
        return ShortcutResult(
            ok=False,
            skipped=True,
            message="Shortcuts are not installed on macOS.",
        )
    if sys.platform.startswith("linux"):
        return _installLinux(folder)
    return ShortcutResult(
        ok=False,
        skipped=True,
        message="Shortcuts are not supported on this system.",
    )


# ------------------------------------------------------------
# Function: main
# Purpose: CLI used by scripts/install.bat and scripts/install.sh.
# Output: int - 0 when the icon was written or this OS is skipped.
# ------------------------------------------------------------
def main() -> int:
    result = installShortcuts()
    print(result.message)
    if result.ok or result.skipped:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
