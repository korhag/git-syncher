from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from app.core.git_service import GitService, _CREATE_NO_WINDOW


# ------------------------------------------------------------
# Tests: Git executable resolution and hidden console
# ------------------------------------------------------------
class TestGitExecutable:
    # --------------------------------------------------------
    # Method: testPrefersGitExeOverCmd
    # --------------------------------------------------------
    def testPrefersGitExeOverCmd(self, tmp_path: Path) -> None:
        cmd = tmp_path / "git.cmd"
        exe = tmp_path / "git.exe"
        cmd.write_text("@echo off\n", encoding="utf-8")
        exe.write_text("", encoding="utf-8")
        with patch("app.core.git_service.shutil.which", return_value=str(cmd)):
            resolved = GitService.resolveGitExecutable()
        assert resolved == str(exe)

    # --------------------------------------------------------
    # Method: testHideConsoleKwargsOnWindows
    # --------------------------------------------------------
    def testHideConsoleKwargsOnWindows(self) -> None:
        if os.name != "nt":
            assert GitService._hideConsoleKwargs() == {}
            return
        kwargs = GitService._hideConsoleKwargs()
        assert kwargs.get("creationflags", 0) & _CREATE_NO_WINDOW
        assert "startupinfo" in kwargs
