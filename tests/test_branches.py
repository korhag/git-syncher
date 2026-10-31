from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from app.core.git_service import BranchInfo, GitService
from app.models.project import ProjectConfig
from app.ui.project_detail import ProjectDetailView


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
# Purpose: git rev-parse a ref, or empty when it is missing.
# ------------------------------------------------------------
def _rev(cwd: Path, ref: str) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", ref],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


# ------------------------------------------------------------
# Helper: _show
# Purpose: Blob text of path at a branch in a repo, or empty if missing.
# ------------------------------------------------------------
def _show(cwd: Path, branch: str, file_path: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{branch}:{file_path}"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return ""
    return result.stdout


# ------------------------------------------------------------
# Helper: _identity
# Purpose: Local commit identity so tests can commit.
# ------------------------------------------------------------
def _identity(path: Path) -> None:
    _git(path, "config", "user.email", "t@example.com")
    _git(path, "config", "user.name", "Test")


# ------------------------------------------------------------
# Helper: _write
# ------------------------------------------------------------
def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ------------------------------------------------------------
# Helper: _project
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
# Helper: _diverged
# Purpose: main and feature both change file.txt after a shared base.
#          feature also adds only-feature.txt. main adds only-main.txt
#          and, when delete_on_feature is set, feature removes keep.txt
#          while main edits it.
# Output: (bare remote, clone)
# ------------------------------------------------------------
def _diverged(base: Path, delete_on_feature: bool = False) -> tuple[Path, Path]:
    bare = base / "remote.git"
    clone = base / "clone"
    _git(base, "init", "--bare", str(bare))

    seed = base / "seed"
    seed.mkdir()
    _git(seed, "init", "-b", "main")
    _identity(seed)
    _write(seed / "file.txt", "base\n")
    _write(seed / "keep.txt", "base keep\n")
    _git(seed, "add", ".")
    _git(seed, "commit", "-m", "base")
    _git(seed, "remote", "add", "origin", str(bare))
    _git(seed, "push", "-u", "origin", "main")
    _git(bare, "symbolic-ref", "HEAD", "refs/heads/main")

    _git(seed, "checkout", "-b", "feature")
    _write(seed / "file.txt", "winner\n")
    _write(seed / "only-feature.txt", "from feature\n")
    if delete_on_feature:
        _git(seed, "rm", "keep.txt")
    _git(seed, "add", ".")
    _git(seed, "commit", "-m", "feature tip")
    _git(seed, "push", "-u", "origin", "feature")

    _git(seed, "checkout", "main")
    _write(seed / "file.txt", "from main\n")
    _write(seed / "only-main.txt", "from main\n")
    _write(seed / "keep.txt", "edited on main\n")
    _git(seed, "add", ".")
    _git(seed, "commit", "-m", "main tip")
    _git(seed, "push", "origin", "main")

    _git(base, "clone", str(bare), str(clone))
    _identity(clone)
    return bare, clone


# ------------------------------------------------------------
# Tests: branch list
# ------------------------------------------------------------
class TestListBranches:
    # --------------------------------------------------------
    # Method: testDefaultCurrentAndAheadCounts
    # Purpose: Default branch, the checked-out branch, ahead counts,
    #          and no origin/HEAD row.
    # --------------------------------------------------------
    def testDefaultCurrentAndAheadCounts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bare, clone = _diverged(Path(tmp))
            service = GitService()
            project = _project(clone, bare)
            infos = service.listBranches(project)
            by_name = {info.name: info for info in infos}

            assert "HEAD" not in by_name
            assert "origin" not in by_name
            assert infos[0].name == "main"
            assert by_name["main"].is_default is True
            assert by_name["main"].is_current is True
            assert by_name["main"].on_git is True
            assert by_name["main"].ahead_of_default == 0
            assert by_name["main"].updated.startswith("Updated")

            assert by_name["feature"].on_git is True
            assert by_name["feature"].is_current is False
            assert by_name["feature"].ahead_of_default == 1

    # --------------------------------------------------------
    # Method: testCurrentLocalOnlyBranchIsIncluded
    # Purpose: A branch that exists only on this computer is listed
    #          when it is checked out, and hidden otherwise.
    # --------------------------------------------------------
    def testCurrentLocalOnlyBranchIsIncluded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bare, clone = _diverged(Path(tmp))
            service = GitService()
            project = _project(clone, bare)

            _git(clone, "checkout", "-b", "secret")
            _git(clone, "checkout", "main")
            hidden = {info.name for info in service.listBranches(project)}
            assert "secret" not in hidden

            _git(clone, "checkout", "secret")
            infos = service.listBranches(project)
            secret = next(info for info in infos if info.name == "secret")
            assert secret.on_git is False
            assert secret.is_current is True
            assert secret.git_newer == 0
            assert secret.local_unsent == 0
            assert any(info.name == "feature" and info.on_git for info in infos)

    # --------------------------------------------------------
    # Method: testCurrentBranchReportsNewerAndUnsent
    # Purpose: Commits Git has that this computer does not, and
    #          commits on this computer that Git does not.
    # --------------------------------------------------------
    def testCurrentBranchReportsNewerAndUnsent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            bare, clone = _diverged(base)
            other = base / "other"
            _git(base, "clone", str(bare), str(other))
            _identity(other)
            _write(other / "extra.txt", "from the other computer\n")
            _git(other, "add", ".")
            _git(other, "commit", "-m", "other tip")
            _git(other, "push", "origin", "main")

            _git(clone, "fetch", "origin")
            service = GitService()
            project = _project(clone, bare)
            infos = service.listBranches(project)
            main = next(info for info in infos if info.name == "main")
            feature = next(info for info in infos if info.name == "feature")
            assert main.is_current is True
            assert main.git_newer == 1
            assert main.local_unsent == 0
            assert feature.git_newer == 0
            assert feature.local_unsent == 0

            _write(clone / "mine.txt", "not sent\n")
            _git(clone, "add", ".")
            _git(clone, "commit", "-m", "local only")
            main = next(
                info for info in service.listBranches(project) if info.name == "main"
            )
            assert main.git_newer == 1
            assert main.local_unsent == 1


# ------------------------------------------------------------
# Tests: relative dates
# ------------------------------------------------------------
class TestRelativeUpdated:
    # --------------------------------------------------------
    # Method: testPhrases
    # --------------------------------------------------------
    def testPhrases(self) -> None:
        now = 1_700_000_000
        assert GitService.relativeUpdated(0, now=now) == ""
        assert GitService.relativeUpdated(now - 30, now=now) == "Updated just now"
        assert GitService.relativeUpdated(now - 3600, now=now) == "Updated 1 hour ago"
        assert GitService.relativeUpdated(now - 7200, now=now) == "Updated 2 hours ago"
        assert GitService.relativeUpdated(now - 90000, now=now) == "Updated yesterday"
        assert (
            GitService.relativeUpdated(now - 21 * 86400, now=now)
            == "Updated 3 weeks ago"
        )


# ------------------------------------------------------------
# Tests: wording under a branch card
# ------------------------------------------------------------
class TestBranchDetailLines:
    # --------------------------------------------------------
    # Method: testPlainLanguage
    # --------------------------------------------------------
    def testPlainLanguage(self) -> None:
        current = BranchInfo(
            name="main",
            on_git=True,
            is_current=True,
            is_default=True,
            updated="Updated 2 hours ago",
        )
        assert ProjectDetailView._branchDetailLines(current, "main") == [
            "Git default · on this computer now",
            "Updated 2 hours ago",
        ]

        feature = BranchInfo(
            name="feature-x",
            on_git=True,
            updated="Updated yesterday",
            ahead_of_default=3,
        )
        assert ProjectDetailView._branchDetailLines(feature, "main") == [
            "Updated yesterday · 3 changes not in main",
        ]

        done = BranchInfo(
            name="old-idea",
            on_git=True,
            updated="Updated 3 weeks ago",
            ahead_of_default=0,
        )
        assert ProjectDetailView._branchDetailLines(done, "main") == [
            "Updated 3 weeks ago · already in main",
        ]

        one = BranchInfo(name="feature", on_git=True, ahead_of_default=1)
        assert ProjectDetailView._branchDetailLines(one, "main") == [
            "1 change not in main",
        ]

        testing = BranchInfo(
            name="feat/forest-showroom",
            on_git=True,
            is_current=True,
            updated="Updated 2 hours ago",
            ahead_of_default=3,
            git_newer=1,
            local_unsent=2,
        )
        assert ProjectDetailView._branchDetailLines(testing, "main") == [
            "on this computer now",
            "Updated 2 hours ago · 3 changes not in main",
            "Git has 1 newer change",
            "2 changes not sent to Git yet",
        ]

        single = BranchInfo(
            name="feature",
            on_git=True,
            is_current=True,
            git_newer=1,
            local_unsent=1,
        )
        assert ProjectDetailView._branchDetailLines(single, "main") == [
            "on this computer now",
            "already in main",
            "Git has 1 newer change",
            "1 change not sent to Git yet",
        ]


# ------------------------------------------------------------
# Tests: make this computer match one branch
# ------------------------------------------------------------
class TestResetToNamedBranch:
    # --------------------------------------------------------
    # Method: testSwitchesFolderToFeature
    # --------------------------------------------------------
    def testSwitchesFolderToFeature(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bare, clone = _diverged(Path(tmp))
            _write(clone / "dirty.txt", "local only\n")
            service = GitService()
            project = _project(clone, bare)

            preview = service.previewPull(project, branch="feature")
            assert preview.outcome is None
            assert preview.remote_ref == "origin/feature"
            assert preview.would_lose_local is True

            outcome = service.resetToRemote(project, branch="feature")
            assert outcome.success is True, outcome.message or outcome.title
            assert service.detectBranch(clone) == "feature"
            assert (clone / "file.txt").read_text(encoding="utf-8") == "winner\n"
            assert not (clone / "dirty.txt").exists()
            assert not (clone / "only-main.txt").exists()
            assert project.default_branch == "feature"


# ------------------------------------------------------------
# Tests: make a branch the winner
# ------------------------------------------------------------
class TestMergeWinner:
    # --------------------------------------------------------
    # Method: testConflictingLineKeepsWinnerAndKeepsMainOnlyFile
    # --------------------------------------------------------
    def testConflictingLineKeepsWinnerAndKeepsMainOnlyFile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            bare, clone = _diverged(base)
            _git(clone, "checkout", "feature")
            service = GitService()
            project = _project(clone, bare, branch="feature")

            outcome = service.mergeWinner(project, "feature", delete_after=False)
            assert outcome.success is True, outcome.message or outcome.details or outcome.title

            text = (clone / "file.txt").read_text(encoding="utf-8")
            assert text == "winner\n"
            assert "<<<<<<<" not in text
            assert (clone / "only-main.txt").is_file()
            assert (clone / "only-feature.txt").is_file()
            assert service.detectBranch(clone) == "main"
            assert project.default_branch == "main"
            assert _show(bare, "main", "file.txt") == "winner\n"
            assert _rev(bare, "refs/heads/feature")
            assert _rev(clone, "refs/heads/feature")

    # --------------------------------------------------------
    # Method: testDeleteModifyConflictTakesWinnerDeletion
    # Purpose: Main edited keep.txt and feature deleted it.
    #          The winner's deletion lands on main without asking.
    # --------------------------------------------------------
    def testDeleteModifyConflictTakesWinnerDeletion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bare, clone = _diverged(Path(tmp), delete_on_feature=True)
            service = GitService()
            outcome = service.mergeWinner(
                _project(clone, bare),
                "feature",
                delete_after=False,
            )
            assert outcome.success is True, outcome.message or outcome.details or outcome.title
            assert not (clone / "keep.txt").exists()
            assert _show(bare, "main", "keep.txt") == ""
            assert (clone / "only-main.txt").is_file()
            assert service.detectBranch(clone) == "main"

    # --------------------------------------------------------
    # Method: testDeleteAfterRemovesBranch
    # --------------------------------------------------------
    def testDeleteAfterRemovesBranch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bare, clone = _diverged(Path(tmp))
            _git(clone, "checkout", "feature")
            service = GitService()
            outcome = service.mergeWinner(
                _project(clone, bare),
                "feature",
                delete_after=True,
            )
            assert outcome.success is True, outcome.message or outcome.title
            assert "deleted" in outcome.message
            assert _rev(bare, "refs/heads/feature") == ""
            assert _rev(clone, "refs/heads/feature") == ""
            assert service.detectBranch(clone) == "main"

    # --------------------------------------------------------
    # Method: testUnsavedFilesAreRefused
    # --------------------------------------------------------
    def testUnsavedFilesAreRefused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bare, clone = _diverged(Path(tmp))
            _write(clone / "notes.txt", "not committed\n")
            before = _rev(bare, "refs/heads/main")
            service = GitService()
            outcome = service.mergeWinner(_project(clone, bare), "feature")
            assert outcome.success is False
            assert outcome.title == "Unsaved files"
            assert (clone / "notes.txt").is_file()
            assert _rev(bare, "refs/heads/main") == before

    # --------------------------------------------------------
    # Method: testUnpushedWinnerCommitsAreRefused
    # Purpose: Commits that never reached Git must not be skipped.
    # --------------------------------------------------------
    def testUnpushedWinnerCommitsAreRefused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bare, clone = _diverged(Path(tmp))
            _git(clone, "checkout", "feature")
            _write(clone / "local-only.txt", "not pushed\n")
            _git(clone, "add", ".")
            _git(clone, "commit", "-m", "local only")
            service = GitService()
            outcome = service.mergeWinner(_project(clone, bare), "feature")
            assert outcome.success is False
            assert outcome.title == "Push this branch first"
            assert _show(bare, "main", "file.txt") == "from main\n"


# ------------------------------------------------------------
# Tests: commit unsaved files onto a new branch and send it
# ------------------------------------------------------------
class TestCommitToNewBranch:
    # --------------------------------------------------------
    # Method: testMovesUnsavedFilesAndPushes
    # Purpose: The new branch gets the files, Git's main stays put,
    #          and this computer is left on the new branch.
    # --------------------------------------------------------
    def testMovesUnsavedFilesAndPushes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bare, clone = _diverged(Path(tmp))
            _write(clone / "try.txt", "not sure\n")
            before_main = _rev(bare, "refs/heads/main")
            service = GitService()
            project = _project(clone, bare)

            outcome = service.commitToNewBranch(
                project,
                "try lighting",
                "try/new-lighting",
            )
            assert outcome.success is True, outcome.message or outcome.title
            assert "try/new-lighting" in outcome.title
            assert service.detectBranch(clone) == "try/new-lighting"
            assert project.default_branch == "try/new-lighting"
            assert _rev(bare, "refs/heads/main") == before_main
            assert _rev(bare, "refs/heads/try/new-lighting")
            assert _show(bare, "try/new-lighting", "try.txt") == "not sure\n"
            assert _show(clone, "main", "try.txt") == ""

    # --------------------------------------------------------
    # Method: testExistingOrInvalidNameChangesNothing
    # --------------------------------------------------------
    def testExistingOrInvalidNameChangesNothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bare, clone = _diverged(Path(tmp))
            _write(clone / "try.txt", "not sure\n")
            service = GitService()
            project = _project(clone, bare)
            before = _rev(clone, "HEAD")

            taken = service.commitToNewBranch(project, "nope", "feature")
            assert taken.success is False
            assert "already exists on Git" in taken.message
            assert service.detectBranch(clone) == "main"
            assert (clone / "try.txt").is_file()
            assert _rev(clone, "HEAD") == before
            assert _rev(bare, "refs/heads/feature")

            invalid = service.commitToNewBranch(project, "nope", "bad..name")
            assert invalid.success is False
            assert "not a valid branch name" in invalid.message
            assert service.detectBranch(clone) == "main"
            assert _rev(clone, "HEAD") == before

            assert service.validateNewBranchName(clone, "try/new-lighting") == ""

    # --------------------------------------------------------
    # Method: testNothingToCommitDeletesTheNewBranch
    # --------------------------------------------------------
    def testNothingToCommitDeletesTheNewBranch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bare, clone = _diverged(Path(tmp))
            service = GitService()
            project = _project(clone, bare)

            outcome = service.commitToNewBranch(project, "empty", "try/empty")
            assert outcome.success is True
            assert outcome.title == "Nothing to commit"
            assert service.detectBranch(clone) == "main"
            assert project.default_branch == "main"
            assert _rev(clone, "refs/heads/try/empty") == ""
            assert _rev(bare, "refs/heads/try/empty") == ""
