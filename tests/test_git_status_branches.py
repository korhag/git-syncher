from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from app.core.git_service import GitService
from app.models.project import ProjectConfig, SuggestedAction


# ------------------------------------------------------------
# Helper: _runGit
# Purpose: Run git in a directory; raise on failure.
# ------------------------------------------------------------
def _runGit(cwd: Path, *args: str) -> None:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed: {result.stderr or result.stdout}"
        )


# ------------------------------------------------------------
# Helper: _writeFile
# ------------------------------------------------------------
def _writeFile(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ------------------------------------------------------------
# Tests: default branch diverge must not report Synced
# ------------------------------------------------------------
class TestDefaultBranchDiverge:
    # --------------------------------------------------------
    # Method: testMasterMatchingOriginMasterButDefaultIsMain
    # Purpose: Laptop on master matching origin/master while
    #          origin/HEAD is main with different commits → Resolve.
    # --------------------------------------------------------
    def testMasterMatchingOriginMasterButDefaultIsMain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            bare = base / "remote.git"
            clone = base / "clone"
            _runGit(base, "init", "--bare", str(bare))

            seed = base / "seed"
            seed.mkdir()
            _runGit(seed, "init", "-b", "main")
            _runGit(seed, "config", "user.email", "test@example.com")
            _runGit(seed, "config", "user.name", "Test")
            _writeFile(seed / "Changelog.md", "## [2.2.1] - 2026-01-01\n")
            _runGit(seed, "add", ".")
            _runGit(seed, "commit", "-m", "main tip")
            _runGit(seed, "remote", "add", "origin", str(bare))
            _runGit(seed, "push", "-u", "origin", "main")
            _runGit(bare, "symbolic-ref", "HEAD", "refs/heads/main")

            # Divergent master history (different tip than main)
            _runGit(seed, "checkout", "-b", "master")
            _writeFile(seed / "Changelog.md", "## [2.4.1] - 2026-01-02\n")
            _runGit(seed, "add", ".")
            _runGit(seed, "commit", "-m", "master tip")
            _runGit(seed, "push", "-u", "origin", "master")

            _runGit(base, "clone", str(bare), str(clone))
            _runGit(clone, "checkout", "master")
            _runGit(clone, "config", "user.email", "test@example.com")
            _runGit(clone, "config", "user.name", "Test")

            service = GitService()
            project = ProjectConfig(
                id="p1",
                name="demo",
                path=str(clone),
                remote_url=str(bare),
                default_branch="master",
            )
            status = service.getStatus(project, fetch=False)

            assert status.branch == "master"
            assert status.remote_default_branch == "main"
            assert status.diverges_from_default is True
            assert status.ahead == 0
            assert status.behind == 0
            assert status.suggested_action == SuggestedAction.RESOLVE
            lines = status.plainStatusLines()
            assert any("default branch is main" in line for line in lines)
            assert any("not the same" in line for line in lines)

            # Match Git should prefer origin/main (default), not origin/master
            remote_ref = service._resolveOriginBranch(clone, project)
            assert remote_ref == "origin/main"

    # --------------------------------------------------------
    # Method: testOnDefaultBranchSynced
    # Purpose: Clean clone on main matching origin/main → Synced.
    # --------------------------------------------------------
    def testOnDefaultBranchSynced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            bare = base / "remote.git"
            clone = base / "clone"
            _runGit(base, "init", "--bare", str(bare))

            seed = base / "seed"
            seed.mkdir()
            _runGit(seed, "init", "-b", "main")
            _runGit(seed, "config", "user.email", "test@example.com")
            _runGit(seed, "config", "user.name", "Test")
            _writeFile(seed / "Changelog.md", "## [1.0.0] - 2026-01-01\n")
            _runGit(seed, "add", ".")
            _runGit(seed, "commit", "-m", "init")
            _runGit(seed, "remote", "add", "origin", str(bare))
            _runGit(seed, "push", "-u", "origin", "main")
            _runGit(bare, "symbolic-ref", "HEAD", "refs/heads/main")

            _runGit(base, "clone", str(bare), str(clone))

            service = GitService()
            project = ProjectConfig(
                id="p2",
                name="demo",
                path=str(clone),
                remote_url=str(bare),
                default_branch="main",
            )
            status = service.getStatus(project, fetch=False)
            assert status.branch == "main"
            assert status.remote_default_branch == "main"
            assert status.diverges_from_default is False
            assert status.suggested_action == SuggestedAction.SYNCED

    # --------------------------------------------------------
    # Method: testMissingUpstreamNotSynced
    # Purpose: Local-only branch with no origin/<branch> → Resolve.
    # --------------------------------------------------------
    def testMissingUpstreamNotSynced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            bare = base / "remote.git"
            clone = base / "clone"
            _runGit(base, "init", "--bare", str(bare))

            seed = base / "seed"
            seed.mkdir()
            _runGit(seed, "init", "-b", "main")
            _runGit(seed, "config", "user.email", "test@example.com")
            _runGit(seed, "config", "user.name", "Test")
            _writeFile(seed / "a.txt", "a\n")
            _runGit(seed, "add", ".")
            _runGit(seed, "commit", "-m", "init")
            _runGit(seed, "remote", "add", "origin", str(bare))
            _runGit(seed, "push", "-u", "origin", "main")

            _runGit(base, "clone", str(bare), str(clone))
            _runGit(clone, "config", "user.email", "test@example.com")
            _runGit(clone, "config", "user.name", "Test")
            _runGit(clone, "checkout", "-b", "local-only")

            service = GitService()
            project = ProjectConfig(
                id="p3",
                name="demo",
                path=str(clone),
                remote_url=str(bare),
                default_branch="local-only",
            )
            status = service.getStatus(project, fetch=False)
            assert status.upstream_missing is True
            assert status.suggested_action == SuggestedAction.RESOLVE


# ------------------------------------------------------------
# Tests: honor saved branch + dual force-push
# ------------------------------------------------------------
class TestHonorSavedBranchAndForcePush:
    # --------------------------------------------------------
    # Helper: _setupMainAndMaster
    # --------------------------------------------------------
    def _setupMainAndMaster(self, base: Path) -> tuple[Path, Path]:
        bare = base / "remote.git"
        clone = base / "clone"
        _runGit(base, "init", "--bare", str(bare))

        seed = base / "seed"
        seed.mkdir()
        _runGit(seed, "init", "-b", "main")
        _runGit(seed, "config", "user.email", "test@example.com")
        _runGit(seed, "config", "user.name", "Test")
        _writeFile(seed / "Changelog.md", "## [1.2.1] - 2026-01-01\n")
        _runGit(seed, "add", ".")
        _runGit(seed, "commit", "-m", "main tip")
        _runGit(seed, "remote", "add", "origin", str(bare))
        _runGit(seed, "push", "-u", "origin", "main")
        _runGit(bare, "symbolic-ref", "HEAD", "refs/heads/main")

        _runGit(seed, "checkout", "-b", "master")
        _writeFile(seed / "Changelog.md", "## [1.4.1] - 2026-01-02\n")
        _runGit(seed, "add", ".")
        _runGit(seed, "commit", "-m", "master tip")
        _runGit(seed, "push", "-u", "origin", "master")

        _runGit(base, "clone", str(bare), str(clone))
        _runGit(clone, "checkout", "master")
        _runGit(clone, "config", "user.email", "test@example.com")
        _runGit(clone, "config", "user.name", "Test")
        return bare, clone

    # --------------------------------------------------------
    # Method: testCheckoutSavedBranchSwitchesToMain
    # --------------------------------------------------------
    def testCheckoutSavedBranchSwitchesToMain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bare, clone = self._setupMainAndMaster(Path(tmp))
            service = GitService()
            project = ProjectConfig(
                id="p4",
                name="demo",
                path=str(clone),
                remote_url=str(bare),
                default_branch="main",
            )
            outcome = service.checkoutSavedBranch(project)
            assert outcome.success is True
            assert service.detectBranch(clone) == "main"

            # getStatus must not rewrite saved default_branch back to master
            project.default_branch = "main"
            status = service.getStatus(project, fetch=False)
            assert status.branch == "main"
            assert project.default_branch == "main"
            assert status.diverges_from_default is False
            assert status.suggested_action == SuggestedAction.SYNCED

    # --------------------------------------------------------
    # Method: testGetStatusDoesNotOverwriteDefaultBranch
    # --------------------------------------------------------
    def testGetStatusDoesNotOverwriteDefaultBranch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bare, clone = self._setupMainAndMaster(Path(tmp))
            service = GitService()
            project = ProjectConfig(
                id="p5",
                name="demo",
                path=str(clone),
                remote_url=str(bare),
                default_branch="main",
            )
            status = service.getStatus(project, fetch=False)
            assert status.branch == "master"
            assert project.default_branch == "main"

    # --------------------------------------------------------
    # Method: testForcePushAlsoUpdatesDefaultBranch
    # --------------------------------------------------------
    def testForcePushAlsoUpdatesDefaultBranch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bare, clone = self._setupMainAndMaster(Path(tmp))
            service = GitService()
            project = ProjectConfig(
                id="p6",
                name="demo",
                path=str(clone),
                remote_url=str(bare),
                default_branch="master",
            )
            outcome = service.push(project, force=True)
            assert outcome.success is True
            assert "master" in outcome.message
            assert "main" in outcome.message

            master_sha = subprocess.run(
                ["git", "rev-parse", "refs/heads/master"],
                cwd=bare,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            main_sha = subprocess.run(
                ["git", "rev-parse", "refs/heads/main"],
                cwd=bare,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            local_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=clone,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            assert master_sha == local_sha
            assert main_sha == local_sha

            # Fetch so origin/main matches and status can clear diverge
            _runGit(clone, "fetch", "origin")
            status = service.getStatus(project, fetch=False)
            assert status.diverges_from_default is False
            assert status.suggested_action == SuggestedAction.SYNCED
