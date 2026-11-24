from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from app.core.git_service import GitService
from app.models.project import ProjectConfig


# ------------------------------------------------------------
# Helper: _git
# ------------------------------------------------------------
def _git(cwd: Path, *args: str) -> None:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


# ------------------------------------------------------------
# Tests: clone into empty folder
# ------------------------------------------------------------
class TestCloneRepo:
    # --------------------------------------------------------
    # Method: _seedBareMain
    # --------------------------------------------------------
    def _seedBareMain(self, tmp: Path) -> Path:
        bare = tmp / "remote.git"
        seed = tmp / "seed"
        seed.mkdir()
        _git(tmp, "init", "--bare", str(bare))
        _git(seed, "init", "-b", "main")
        _git(seed, "config", "user.email", "t@example.com")
        _git(seed, "config", "user.name", "Test")
        (seed / "README.md").write_text("hello\n", encoding="utf-8")
        _git(seed, "add", "README.md")
        _git(seed, "commit", "-m", "init")
        _git(seed, "remote", "add", "origin", str(bare))
        _git(seed, "push", "-u", "origin", "main")
        _git(bare, "symbolic-ref", "HEAD", "refs/heads/main")
        return bare

    # --------------------------------------------------------
    # Method: testCloneIntoEmptyFolder
    # --------------------------------------------------------
    def testCloneIntoEmptyFolder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            bare = self._seedBareMain(base)
            dest = base / "dest"
            dest.mkdir()
            git = GitService()
            project = ProjectConfig(
                id="c1",
                name="Cloned",
                path=str(dest),
                remote_url=str(bare),
                default_branch="main",
                username="Test",
                email="t@example.com",
            )
            outcome = git.cloneRepo(project, dest, "main")
            assert outcome.success, outcome.message or outcome.title
            assert git.isRepo(dest)
            assert git.detectBranch(dest) == "main"
            assert git.detectRemoteUrl(dest) == str(bare)
            assert (dest / "README.md").is_file()

    # --------------------------------------------------------
    # Method: testCloneRefusesNonEmptyFolder
    # --------------------------------------------------------
    def testCloneRefusesNonEmptyFolder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            bare = self._seedBareMain(base)
            dest = base / "dest"
            dest.mkdir()
            (dest / "keep.txt").write_text("nope\n", encoding="utf-8")
            git = GitService()
            project = ProjectConfig(
                id="c2",
                name="Cloned",
                path=str(dest),
                remote_url=str(bare),
            )
            outcome = git.cloneRepo(project, dest, "main")
            assert outcome.success is False
            assert "empty" in (outcome.message or "").lower()

    # --------------------------------------------------------
    # Method: testListRemoteBranchesWithoutLocalFolder
    # --------------------------------------------------------
    def testListRemoteBranchesWithoutLocalFolder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            bare = self._seedBareMain(base)
            git = GitService()
            project = ProjectConfig(
                id="c3",
                name="temp",
                path=str(base / "missing-folder"),
                remote_url=str(bare),
            )
            branches, default_branch, err = git.listRemoteBranches(project)
            assert err == ""
            assert "main" in branches
            assert default_branch == "main"

    # --------------------------------------------------------
    # Method: testDisplayNameFromRemoteUrl
    # --------------------------------------------------------
    def testDisplayNameFromRemoteUrl(self) -> None:
        assert (
            GitService.displayNameFromRemoteUrl(
                "https://github.com/korhag/MyCad.git"
            )
            == "MyCad"
        )
        assert GitService.displayNameFromRemoteUrl("git@github.com:org/app.git") == "app"

    # --------------------------------------------------------
    # Method: testIsEmptyDirectory
    # --------------------------------------------------------
    def testIsEmptyDirectory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "empty"
            empty.mkdir()
            assert GitService.isEmptyDirectory(empty) is True
            (empty / "f.txt").write_text("x\n", encoding="utf-8")
            assert GitService.isEmptyDirectory(empty) is False
            assert GitService.isEmptyDirectory(Path(tmp) / "missing") is False
