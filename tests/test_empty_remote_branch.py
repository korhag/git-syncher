from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from app.core.git_service import GitService
from app.models.project import ProjectConfig


# ------------------------------------------------------------
# Tests: empty-remote / default branch helpers
# ------------------------------------------------------------
class TestSuggestBranchNames:
    # --------------------------------------------------------
    # Method: testIncludesMainAndMaster
    # --------------------------------------------------------
    def testIncludesMainAndMaster(self) -> None:
        git = GitService()
        names = git.suggestBranchNames()
        assert "main" in names
        assert "master" in names
        assert names[0]  # non-empty preferred default

    # --------------------------------------------------------
    # Method: testResolvePrefersExplicit
    # --------------------------------------------------------
    def testResolvePrefersExplicit(self) -> None:
        git = GitService()
        assert git.resolveBranchForSave(".", "develop") == "develop"
        resolved = git.resolveBranchForSave("")
        assert resolved in git.suggestBranchNames()


# ------------------------------------------------------------
# Tests: checkoutSavedBranch on empty remote
# ------------------------------------------------------------
class TestCheckoutEmptyRemote:
    # --------------------------------------------------------
    # Method: _git
    # --------------------------------------------------------
    @staticmethod
    def _git(cwd: Path, *args: str) -> None:
        completed = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr

    # --------------------------------------------------------
    # Method: testRenamesLocalWhenOriginBranchMissing
    # --------------------------------------------------------
    def testRenamesLocalWhenOriginBranchMissing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / "local"
            bare = Path(tmp) / "remote.git"
            local.mkdir()
            self._git(local, "init", "-b", "master")
            self._git(local, "config", "user.email", "t@example.com")
            self._git(local, "config", "user.name", "Test")
            (local / "README").write_text("hi\n", encoding="utf-8")
            self._git(local, "add", "README")
            self._git(local, "commit", "-m", "init")
            self._git(Path(tmp), "init", "--bare", str(bare))
            self._git(local, "remote", "add", "origin", str(bare))

            git = GitService()
            project = ProjectConfig(
                id="p1",
                name="Demo",
                path=str(local),
                remote_url=str(bare),
                default_branch="main",
            )
            outcome = git.checkoutSavedBranch(project)
            assert outcome.success
            blob = f"{outcome.title} {outcome.message}".lower()
            assert "first push" in blob
            assert git.detectBranch(local) == "main"
