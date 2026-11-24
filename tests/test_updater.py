from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import patch

from app.core.shortcuts import ShortcutResult
from app.core.updater import updateApp


# ------------------------------------------------------------
# Function: _repo
# Purpose: Minimal Git Syncher checkout for update tests.
# ------------------------------------------------------------
def _repo(tmp_path: Path, version: str = "1.16.0", requirements: str = "flet==0.86.5\n") -> Path:
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    app_dir = root / "app"
    app_dir.mkdir()
    (app_dir / "__init__.py").write_text(f'__version__ = "{version}"\n', encoding="utf-8")
    (root / "requirements.txt").write_text(requirements, encoding="utf-8")
    if os.name == "nt":
        python = root / ".venv" / "Scripts" / "python.exe"
    else:
        python = root / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    return root


# ------------------------------------------------------------
# Function: _completed
# Purpose: A finished process result for a fake command.
# ------------------------------------------------------------
def _completed(args: list[str], returncode: int = 0, stdout: str = "", stderr: str = ""):
    return subprocess.CompletedProcess(args, returncode, stdout, stderr)


# ------------------------------------------------------------
# Tests: updateApp
# ------------------------------------------------------------
class TestUpdateApp:
    # --------------------------------------------------------
    # Method: _runUpdate
    # Purpose: Call updateApp with Git and the menu icon mocked.
    # --------------------------------------------------------
    def _runUpdate(self, root: Path, fake_run, shortcut: ShortcutResult | None = None):
        icon = shortcut or ShortcutResult(ok=True, message="icon ok")
        with (
            patch("app.core.updater.GitService.resolveGitExecutable", return_value="git"),
            patch("app.core.updater.GitService.isGitAvailable", return_value=True),
            patch("app.core.updater.subprocess.run", side_effect=fake_run),
            patch("app.core.updater.installShortcuts", return_value=icon),
        ):
            return updateApp(root)

    # --------------------------------------------------------
    # Method: testNotAGitCheckout
    # Purpose: A copied folder without .git is refused.
    # --------------------------------------------------------
    def testNotAGitCheckout(self, tmp_path: Path) -> None:
        result = updateApp(tmp_path)
        assert result.ok is False
        assert "not a Git checkout" in result.message

    # --------------------------------------------------------
    # Method: testGitMissing
    # Purpose: No git binary is a clear failure.
    # --------------------------------------------------------
    def testGitMissing(self, tmp_path: Path) -> None:
        root = _repo(tmp_path)
        with (
            patch("app.core.updater.GitService.resolveGitExecutable", return_value="git"),
            patch("app.core.updater.GitService.isGitAvailable", return_value=False),
        ):
            result = updateApp(root)
        assert result.ok is False
        assert "Git was not found" in result.message

    # --------------------------------------------------------
    # Method: testLocalEditsBlockPull
    # Purpose: Tracked changes stop the update before pull.
    # --------------------------------------------------------
    def testLocalEditsBlockPull(self, tmp_path: Path) -> None:
        root = _repo(tmp_path)
        commands: list[list[str]] = []

        def fake_run(args, **_kwargs):
            commands.append(list(args))
            return _completed(args, stdout=" M app/main.py\n")

        result = self._runUpdate(root, fake_run)
        assert result.ok is False
        assert "local edits" in result.message
        assert not any("pull" in cmd for cmd in commands)

    # --------------------------------------------------------
    # Method: testAlreadyUpToDateSkipsPip
    # Purpose: An unchanged requirements.txt does not reinstall.
    # --------------------------------------------------------
    def testAlreadyUpToDateSkipsPip(self, tmp_path: Path) -> None:
        root = _repo(tmp_path)
        commands: list[list[str]] = []

        def fake_run(args, **_kwargs):
            commands.append(list(args))
            if "status" in args:
                return _completed(args)
            if "pull" in args:
                return _completed(args, stdout="Already up to date.\n")
            raise AssertionError(args)

        result = self._runUpdate(root, fake_run)
        assert result.ok is True
        assert result.updated is False
        assert "Already up to date (v1.16.0)." in result.message
        pull = next(cmd for cmd in commands if "pull" in cmd)
        assert "--ff-only" in pull
        assert "--no-rebase" in pull
        assert not any("pip" in arg for cmd in commands for arg in cmd)

    # --------------------------------------------------------
    # Method: testRequirementsChangeReinstalls
    # Purpose: A new requirements.txt runs pip, then reports versions.
    # --------------------------------------------------------
    def testRequirementsChangeReinstalls(self, tmp_path: Path) -> None:
        root = _repo(tmp_path)
        commands: list[list[str]] = []

        def fake_run(args, **_kwargs):
            commands.append(list(args))
            if "status" in args:
                return _completed(args)
            if "pull" in args:
                (root / "requirements.txt").write_text("flet==0.99.0\n", encoding="utf-8")
                (root / "app" / "__init__.py").write_text(
                    '__version__ = "1.17.0"\n',
                    encoding="utf-8",
                )
                return _completed(args, stdout="Fast-forward\n")
            if "pip" in args:
                return _completed(args)
            raise AssertionError(args)

        result = self._runUpdate(root, fake_run)
        assert result.ok is True
        assert result.updated is True
        assert result.version_before == "1.16.0"
        assert result.version_after == "1.17.0"
        assert "Updated 1.16.0 to 1.17.0." in result.message
        assert "Dependencies were reinstalled." in result.message
        pip = next(cmd for cmd in commands if "pip" in cmd)
        assert "--index-url" in pip
        assert "https://pypi.org/simple" in pip
        assert "requirements.txt" in pip

    # --------------------------------------------------------
    # Method: testPullFailure
    # Purpose: A rejected pull is shown and does not restart the flow.
    # --------------------------------------------------------
    def testPullFailure(self, tmp_path: Path) -> None:
        root = _repo(tmp_path)

        def fake_run(args, **_kwargs):
            if "status" in args:
                return _completed(args)
            if "pull" in args:
                return _completed(args, returncode=1, stderr="fatal: Could not read from remote.\n")
            raise AssertionError(args)

        result = self._runUpdate(root, fake_run)
        assert result.ok is False
        assert "Could not download updates." in result.message
        assert "Could not read from remote" in result.message

    # --------------------------------------------------------
    # Method: testPullTimeout
    # Purpose: A hung download becomes a normal failure result.
    # --------------------------------------------------------
    def testPullTimeout(self, tmp_path: Path) -> None:
        root = _repo(tmp_path)

        def fake_run(args, **_kwargs):
            if "pull" in args:
                raise subprocess.TimeoutExpired(args, 120)
            return _completed(args)

        result = self._runUpdate(root, fake_run)
        assert result.ok is False
        assert "timed out" in result.message

    # --------------------------------------------------------
    # Method: testPipFailure
    # Purpose: A failed reinstall does not count as a finished update.
    # --------------------------------------------------------
    def testPipFailure(self, tmp_path: Path) -> None:
        root = _repo(tmp_path)

        def fake_run(args, **_kwargs):
            if "status" in args:
                return _completed(args)
            if "pull" in args:
                (root / "requirements.txt").write_text("flet==0.99.0\n", encoding="utf-8")
                return _completed(args, stdout="Fast-forward\n")
            if "pip" in args:
                return _completed(args, returncode=1, stderr="ERROR: No matching distribution\n")
            raise AssertionError(args)

        result = self._runUpdate(root, fake_run)
        assert result.ok is False
        assert result.updated is True
        assert "Could not install dependencies." in result.message

    # --------------------------------------------------------
    # Method: testShortcutFailureStillSucceeds
    # Purpose: Code that downloaded is still an update if the icon fails.
    # --------------------------------------------------------
    def testShortcutFailureStillSucceeds(self, tmp_path: Path) -> None:
        root = _repo(tmp_path)

        def fake_run(args, **_kwargs):
            if "status" in args:
                return _completed(args)
            if "pull" in args:
                return _completed(args, stdout="Already up to date.\n")
            raise AssertionError(args)

        result = self._runUpdate(
            root,
            fake_run,
            shortcut=ShortcutResult(ok=False, message="disk full"),
        )
        assert result.ok is True
        assert "disk full" in result.message
