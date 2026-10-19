from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from app.core import shortcuts


# ------------------------------------------------------------
# Function: _touch
# Purpose: Create an empty file and its parent folders.
# ------------------------------------------------------------
def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    return path


# ------------------------------------------------------------
# Tests: installShortcuts
# ------------------------------------------------------------
class TestInstallShortcuts:
    # --------------------------------------------------------
    # Method: testWindowsStartMenuShortcut
    # Purpose: PowerShell receives the venv python, repo, and icon.
    # --------------------------------------------------------
    def testWindowsStartMenuShortcut(self, tmp_path: Path, monkeypatch) -> None:
        root = tmp_path / "my app"
        pythonw = _touch(root / ".venv" / "Scripts" / "pythonw.exe")
        icon = root / "assets" / "icon.ico"
        icon.parent.mkdir(parents=True)
        icon.write_bytes(b"ico")
        appdata = tmp_path / "Roaming"
        monkeypatch.setenv("APPDATA", str(appdata))
        calls: list[list[str]] = []

        def fake_run(args, **_kwargs):
            calls.append(list(args))
            return subprocess.CompletedProcess(args, 0, "", "")

        with patch.object(shortcuts.subprocess, "run", side_effect=fake_run):
            result = shortcuts._installWindows(root)

        link = appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Git Syncher.lnk"
        assert result.ok is True
        assert result.path == link
        assert len(calls) == 1
        script = calls[0][-1]
        assert "WScript.Shell" in script
        assert "CreateShortcut" in script
        assert str(link) in script
        assert str(pythonw) in script
        assert str(root) in script
        assert str(icon) in script
        assert "-m app.main" in script

    # --------------------------------------------------------
    # Method: testWindowsPowerShellFailure
    # Purpose: A failing shortcut command is reported, not raised.
    # --------------------------------------------------------
    def testWindowsPowerShellFailure(self, tmp_path: Path, monkeypatch) -> None:
        root = tmp_path / "repo"
        _touch(root / ".venv" / "Scripts" / "python.exe")
        monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))

        def fake_run(args, **_kwargs):
            return subprocess.CompletedProcess(args, 1, "", "access denied")

        with patch.object(shortcuts.subprocess, "run", side_effect=fake_run):
            result = shortcuts._installWindows(root)

        assert result.ok is False
        assert "access denied" in result.message

    # --------------------------------------------------------
    # Method: testWindowsMissingVenv
    # Purpose: No interpreter means no shortcut and no PowerShell call.
    # --------------------------------------------------------
    def testWindowsMissingVenv(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
        with patch.object(shortcuts.subprocess, "run") as run_mock:
            result = shortcuts._installWindows(tmp_path)
        assert result.ok is False
        run_mock.assert_not_called()

    # --------------------------------------------------------
    # Method: testLinuxDesktopFile
    # Purpose: The .desktop file launches the venv and uses the icon.
    # --------------------------------------------------------
    def testLinuxDesktopFile(self, tmp_path: Path) -> None:
        root = tmp_path / "my app"
        python = _touch(root / ".venv" / "bin" / "python")
        icon = root / "assets" / "icon.png"
        icon.parent.mkdir(parents=True)
        icon.write_bytes(b"png")
        home = tmp_path / "home"

        with (
            patch.object(shortcuts.Path, "home", return_value=home),
            patch.object(shortcuts.shutil, "which", return_value=None),
        ):
            result = shortcuts._installLinux(root)

        desktop = home / ".local" / "share" / "applications" / "git-syncher.desktop"
        assert result.ok is True
        assert result.path == desktop
        text = desktop.read_text(encoding="utf-8")
        assert f"Exec={shortcuts._desktopQuote(str(python))} -m app.main" in text
        assert f"Path={root}" in text
        assert f"Icon={icon}" in text
        assert "Terminal=false" in text
        assert "Categories=Development;" in text
        assert text.endswith("\n")
        assert "\r" not in text

    # --------------------------------------------------------
    # Method: testLinuxUpdatesDesktopDatabase
    # Purpose: Refresh the menu cache when the tool exists.
    # --------------------------------------------------------
    def testLinuxUpdatesDesktopDatabase(self, tmp_path: Path) -> None:
        root = tmp_path / "repo"
        _touch(root / ".venv" / "bin" / "python")
        home = tmp_path / "home"
        calls: list[list[str]] = []

        def fake_run(args, **_kwargs):
            calls.append(list(args))
            return subprocess.CompletedProcess(args, 0, "", "")

        with (
            patch.object(shortcuts.Path, "home", return_value=home),
            patch.object(shortcuts.shutil, "which", return_value="/usr/bin/update-desktop-database"),
            patch.object(shortcuts.subprocess, "run", side_effect=fake_run),
        ):
            result = shortcuts._installLinux(root)

        assert result.ok is True
        assert calls[0][0] == "/usr/bin/update-desktop-database"
        assert calls[0][1] == str(home / ".local" / "share" / "applications")

    # --------------------------------------------------------
    # Method: testDarwinSkipped
    # Purpose: macOS is reported as skipped so install can continue.
    # --------------------------------------------------------
    def testDarwinSkipped(self, tmp_path: Path) -> None:
        with (
            patch.object(shortcuts.os, "name", "posix"),
            patch.object(shortcuts.sys, "platform", "darwin"),
        ):
            result = shortcuts.installShortcuts(tmp_path)
        assert result.ok is False
        assert result.skipped is True
        assert "macOS" in result.message

    # --------------------------------------------------------
    # Method: testCliSuccessExitCode
    # Purpose: A written shortcut exits 0.
    # --------------------------------------------------------
    def testCliSuccessExitCode(self) -> None:
        ok = shortcuts.ShortcutResult(ok=True, message="Start Menu shortcut: x")
        with patch.object(shortcuts, "installShortcuts", return_value=ok):
            assert shortcuts.main() == 0

    # --------------------------------------------------------
    # Method: testCliSkippedExitCode
    # Purpose: An unsupported OS does not fail the installer.
    # --------------------------------------------------------
    def testCliSkippedExitCode(self) -> None:
        skipped = shortcuts.ShortcutResult(ok=False, skipped=True, message="skipped")
        with patch.object(shortcuts, "installShortcuts", return_value=skipped):
            assert shortcuts.main() == 0

    # --------------------------------------------------------
    # Method: testCliFailureExitCode
    # Purpose: A real shortcut error fails the module.
    # --------------------------------------------------------
    def testCliFailureExitCode(self) -> None:
        failed = shortcuts.ShortcutResult(ok=False, message="failed")
        with patch.object(shortcuts, "installShortcuts", return_value=failed):
            assert shortcuts.main() == 1
