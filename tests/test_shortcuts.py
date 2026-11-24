from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core import shortcuts, windows_shortcut


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
    def testWindowsStartMenuShortcut(self, tmp_path: Path, monkeypatch) -> None:
        root = tmp_path / "my app"
        pythonw = _touch(root / ".venv" / "Scripts" / "pythonw.exe")
        icon = _touch(root / "assets" / "icon.ico")
        programs = tmp_path / "Redirected Programs"
        monkeypatch.setattr(windows_shortcut, "programsFolder", lambda: programs)
        with patch.object(windows_shortcut, "ensureLink") as ensure:
            result = shortcuts.ensureWindowsShortcut(root)
        assert result.ok
        assert result.path == programs / "Git Syncher.lnk"
        ensure.assert_called_once_with(result.path, windows_shortcut.Link(
            target=pythonw, working_directory=root, arguments="-m app.main", icon=icon,
            description="Git Syncher", app_id="GitSyncher.Desktop",
        ))

    def testWindowsRegistrationFailure(self, tmp_path: Path, monkeypatch) -> None:
        _touch(tmp_path / ".venv" / "Scripts" / "python.exe")
        _touch(tmp_path / "assets" / "icon.ico")
        monkeypatch.setattr(windows_shortcut, "programsFolder", lambda: tmp_path)
        with patch.object(windows_shortcut, "ensureLink", side_effect=OSError("access denied")):
            result = shortcuts.ensureWindowsShortcut(tmp_path)
        assert not result.ok
        assert "access denied" in result.message

    def testWindowsMissingVenv(self, tmp_path: Path) -> None:
        with patch.object(windows_shortcut, "ensureLink") as ensure:
            result = shortcuts.ensureWindowsShortcut(tmp_path)
        assert not result.ok
        ensure.assert_not_called()

    @pytest.mark.skipif(os.name != "nt", reason="exercises Windows shell links")
    def testRepairLegacyLinkAndKeepWorkingRegistration(self, tmp_path: Path, monkeypatch) -> None:
        root = tmp_path / "Derya'nın çalışma alanı"
        pythonw = _touch(root / ".venv" / "Scripts" / "pythonw.exe")
        icon = _touch(root / "assets" / "icon.ico")
        programs = tmp_path / "Programs"
        programs.mkdir()
        link = programs / "Git Syncher.lnk"
        monkeypatch.setattr(windows_shortcut, "programsFolder", lambda: programs)
        # Reproduce the installed WScript link from v1.23.1 (no explicit AppUserModelID).
        subprocess.run([
            "powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
            "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:TEST_LINK); "
            "$s.TargetPath = $env:TEST_TARGET; $s.Save()",
        ], check=True, env={**os.environ, "TEST_LINK": str(link), "TEST_TARGET": str(pythonw)})
        assert windows_shortcut.readLink(link).app_id == ""

        assert shortcuts.ensureWindowsShortcut(root).ok
        assert windows_shortcut.readLink(link) == windows_shortcut.Link(
            target=pythonw, working_directory=root, arguments="-m app.main", icon=icon,
            description="Git Syncher", app_id="GitSyncher.Desktop",
        )
        # Verify Explorer sees the same ID through its independent automation API.
        explorer = subprocess.run([
            "powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
            "$folder = (New-Object -ComObject Shell.Application).NameSpace($env:TEST_PROGRAMS); "
            "$folder.ParseName('Git Syncher.lnk').ExtendedProperty('System.AppUserModel.ID')",
        ], check=True, capture_output=True, text=True,
            env={**os.environ, "TEST_PROGRAMS": str(programs)})
        assert explorer.stdout.strip() == "GitSyncher.Desktop"
        # A normal launch must not rewrite a valid link.
        with patch.object(windows_shortcut, "_save_link", side_effect=AssertionError):
            assert shortcuts.ensureWindowsShortcut(root).ok

        # A failed refresh must leave the previous working shortcut intact.
        old_bytes = link.read_bytes()
        new_root = tmp_path / "new folder"
        _touch(new_root / ".venv" / "Scripts" / "pythonw.exe")
        _touch(new_root / "assets" / "icon.ico")
        with patch.object(windows_shortcut, "_save_link", side_effect=OSError("disk full")):
            assert not shortcuts.ensureWindowsShortcut(new_root).ok
        assert link.read_bytes() == old_bytes
        assert list(programs.iterdir()) == [link]
        assert shortcuts.ensureWindowsShortcut(new_root).ok
        assert windows_shortcut.readLink(link).working_directory == new_root

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
