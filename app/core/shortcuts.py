from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.core import windows_shortcut

APP_NAME = "Git Syncher"
APP_USER_MODEL_ID = "GitSyncher.Desktop"
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
        return _windowsLauncher(root)
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
# Function: _desktopQuote
# Purpose: Quote one Exec argument for a .desktop file.
# ------------------------------------------------------------
def _desktopQuote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def ensureWindowsShortcut(root: Path) -> ShortcutResult:
    """Register this checkout and repair shortcuts created by earlier versions."""
    root = root.resolve()
    python = _windowsLauncher(root)
    if python is None:
        return ShortcutResult(ok=False, message="Virtual environment was not found.")
    icon = root / "assets" / "icon.ico"
    if not icon.is_file():
        return ShortcutResult(ok=False, message=f"The Git Syncher icon is missing: {icon}")

    try:
        link_path = windows_shortcut.programsFolder() / f"{APP_NAME}.lnk"
        windows_shortcut.ensureLink(
            link_path,
            windows_shortcut.Link(
                target=python,
                working_directory=root,
                arguments="-m app.main",
                icon=icon,
                description=APP_NAME,
                app_id=APP_USER_MODEL_ID,
            ),
        )
    except OSError as exc:
        return ShortcutResult(ok=False, message=f"Could not register the Start Menu shortcut: {exc}")
    return ShortcutResult(ok=True, message=f"Start Menu shortcut: {link_path}", path=link_path)


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
        return ensureWindowsShortcut(folder)
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
