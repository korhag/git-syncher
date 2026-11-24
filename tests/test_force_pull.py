from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from app.core.actions import ActionId
from app.core.git_service import GitService
from app.models.project import ProjectConfig


# ------------------------------------------------------------
# Helper: _git
# Purpose: Run git in a directory; raise on failure.
# ------------------------------------------------------------
def _git(cwd: Path, *args: str) -> None:
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
# Helper: _rev
# Purpose: git rev-parse a ref.
# ------------------------------------------------------------
def _rev(cwd: Path, ref: str) -> str:
    result = subprocess.run(
        ["git", "rev-parse", ref],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)
    return result.stdout.strip()


# ------------------------------------------------------------
# Helper: _identity
# Purpose: Local commit identity so tests can commit.
# ------------------------------------------------------------
def _identity(path: Path) -> None:
    _git(path, "config", "user.email", "t@example.com")
    _git(path, "config", "user.name", "Test")


# ------------------------------------------------------------
# Helper: _project
# Purpose: ProjectConfig pointing at a local repo and its remote.
# ------------------------------------------------------------
def _project(local: Path, remote: Path, branch: str = "main") -> ProjectConfig:
    return ProjectConfig(
        id="p1",
        name="Demo",
        path=str(local),
        remote_url=str(remote),
        default_branch=branch,
    )


# ------------------------------------------------------------
# Tests: Pull replaces this folder with Git
# ------------------------------------------------------------
class TestForcePull:
    # --------------------------------------------------------
    # Method: testLocalMainWithUntrackedFilesTakesRemoteMaster
    # Purpose: A mistaken local main (no commits, untracked files)
    #          becomes the remote master branch.
    # --------------------------------------------------------
    def testLocalMainWithUntrackedFilesTakesRemoteMaster(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            bare = base / "remote.git"
            seed = base / "seed"
            local = base / "local"
            _git(base, "init", "--bare", str(bare))
            seed.mkdir()
            _git(seed, "init", "-b", "master")
            _identity(seed)
            (seed / "README").write_text("from git\n", encoding="utf-8")
            _git(seed, "add", "README")
            _git(seed, "commit", "-m", "origin")
            _git(seed, "remote", "add", "origin", str(bare))
            _git(seed, "push", "-u", "origin", "master")
            _git(bare, "symbolic-ref", "HEAD", "refs/heads/master")

            local.mkdir()
            _git(local, "init", "-b", "main")
            _git(local, "remote", "add", "origin", str(bare))
            (local / "README").write_text("junk\n", encoding="utf-8")
            (local / "extra.txt").write_text("only local\n", encoding="utf-8")

            service = GitService()
            project = _project(local, bare, "main")
            preview = service.previewPull(project)
            assert preview.outcome is None, preview.outcome
            assert preview.would_lose_local is True
            assert preview.remote_ref == "origin/master"

            outcome = service.pull(project)
            assert outcome.success is True, outcome.message or outcome.title
            assert service.detectBranch(local) == "master"
            assert project.default_branch == "master"
            assert (local / "README").read_text(encoding="utf-8") == "from git\n"
            assert not (local / "extra.txt").exists()
            assert _rev(local, "HEAD") == _rev(bare, "master")

    # --------------------------------------------------------
    # Method: testDivergedHistoryIsReplaced
    # Purpose: Local-only commits are dropped; folder matches Git.
    # --------------------------------------------------------
    def testDivergedHistoryIsReplaced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            bare = base / "remote.git"
            seed = base / "seed"
            local = base / "local"
            _git(base, "init", "--bare", str(bare))
            seed.mkdir()
            _git(seed, "init", "-b", "main")
            _identity(seed)
            (seed / "shared.txt").write_text("base\n", encoding="utf-8")
            _git(seed, "add", "shared.txt")
            _git(seed, "commit", "-m", "base")
            _git(seed, "remote", "add", "origin", str(bare))
            _git(seed, "push", "-u", "origin", "main")
            _git(bare, "symbolic-ref", "HEAD", "refs/heads/main")

            _git(base, "clone", str(bare), str(local))
            _identity(local)
            (local / "shared.txt").write_text("local edit\n", encoding="utf-8")
            _git(local, "commit", "-am", "local only")

            (seed / "shared.txt").write_text("from git\n", encoding="utf-8")
            _git(seed, "commit", "-am", "remote only")
            _git(seed, "push", "origin", "main")

            service = GitService()
            project = _project(local, bare, "main")
            preview = service.previewPull(project)
            assert preview.outcome is None
            assert preview.would_lose_local is True

            outcome = service.pull(project)
            assert outcome.success is True, outcome.message or outcome.title
            assert (local / "shared.txt").read_text(encoding="utf-8") == "from git\n"
            assert _rev(local, "HEAD") == _rev(bare, "main")

    # --------------------------------------------------------
    # Method: testUnrelatedHistoriesTakeRemote
    # Purpose: A local init with its own commit is replaced by Git.
    # --------------------------------------------------------
    def testUnrelatedHistoriesTakeRemote(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            bare = base / "remote.git"
            seed = base / "seed"
            local = base / "local"
            _git(base, "init", "--bare", str(bare))
            seed.mkdir()
            _git(seed, "init", "-b", "master")
            _identity(seed)
            (seed / "remote.txt").write_text("from git\n", encoding="utf-8")
            _git(seed, "add", "remote.txt")
            _git(seed, "commit", "-m", "remote root")
            _git(seed, "remote", "add", "origin", str(bare))
            _git(seed, "push", "-u", "origin", "master")
            _git(bare, "symbolic-ref", "HEAD", "refs/heads/master")

            local.mkdir()
            _git(local, "init", "-b", "main")
            _identity(local)
            (local / "local.txt").write_text("local root\n", encoding="utf-8")
            _git(local, "add", "local.txt")
            _git(local, "commit", "-m", "local root")
            _git(local, "remote", "add", "origin", str(bare))

            service = GitService()
            project = _project(local, bare, "main")
            preview = service.previewPull(project)
            assert preview.outcome is None, preview.outcome
            assert preview.would_lose_local is True
            assert preview.remote_ref == "origin/master"

            outcome = service.pull(project)
            assert outcome.success is True, outcome.message or outcome.title
            assert service.detectBranch(local) == "master"
            assert project.default_branch == "master"
            assert not (local / "local.txt").exists()
            assert (local / "remote.txt").read_text(encoding="utf-8") == "from git\n"
            assert _rev(local, "HEAD") == _rev(bare, "master")

    # --------------------------------------------------------
    # Method: testCleanFastForwardReportsNoLoss
    # Purpose: A clean folder that is only behind Git needs no confirm.
    # --------------------------------------------------------
    def testCleanFastForwardReportsNoLoss(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            bare = base / "remote.git"
            seed = base / "seed"
            local = base / "local"
            _git(base, "init", "--bare", str(bare))
            seed.mkdir()
            _git(seed, "init", "-b", "main")
            _identity(seed)
            (seed / "file.txt").write_text("one\n", encoding="utf-8")
            _git(seed, "add", "file.txt")
            _git(seed, "commit", "-m", "one")
            _git(seed, "remote", "add", "origin", str(bare))
            _git(seed, "push", "-u", "origin", "main")
            _git(bare, "symbolic-ref", "HEAD", "refs/heads/main")

            _git(base, "clone", str(bare), str(local))
            (seed / "file.txt").write_text("two\n", encoding="utf-8")
            _git(seed, "commit", "-am", "two")
            _git(seed, "push", "origin", "main")

            service = GitService()
            project = _project(local, bare, "main")
            preview = service.previewPull(project)
            assert preview.outcome is None
            assert preview.would_lose_local is False
            assert preview.remote_ref == "origin/main"

            outcome = service.pull(project)
            assert outcome.success is True, outcome.message or outcome.title
            assert (local / "file.txt").read_text(encoding="utf-8") == "two\n"
            assert _rev(local, "HEAD") == _rev(bare, "main")
            assert service.detectBranch(local) == "main"

    # --------------------------------------------------------
    # Method: testEmptyRemoteOffersFirstPush
    # Purpose: Nothing on Git means Pull cannot replace this folder.
    # --------------------------------------------------------
    def testEmptyRemoteOffersFirstPush(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            bare = base / "remote.git"
            local = base / "local"
            _git(base, "init", "--bare", str(bare))
            local.mkdir()
            _git(local, "init", "-b", "main")
            _identity(local)
            (local / "file.txt").write_text("local\n", encoding="utf-8")
            _git(local, "add", "file.txt")
            _git(local, "commit", "-m", "local")
            _git(local, "remote", "add", "origin", str(bare))

            service = GitService()
            project = _project(local, bare, "main")
            preview = service.previewPull(project)
            assert preview.outcome is not None
            assert preview.outcome.success is False
            assert preview.outcome.title == "Remote branch not found"
            ids = [choice.id for choice in preview.outcome.choices]
            assert ActionId.FIRST_PUSH in ids

            outcome = service.pull(project)
            assert outcome.success is False
            assert outcome.title == "Remote branch not found"
            assert ActionId.FIRST_PUSH in [choice.id for choice in outcome.choices]
            assert (local / "file.txt").read_text(encoding="utf-8") == "local\n"
