from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from app.core.git_service import GitService
from app.models.project import ProjectConfig, SuggestedAction


# ------------------------------------------------------------
# Tests: empty-remote / default branch helpers
# ------------------------------------------------------------
class TestSuggestBranchNames:
    # --------------------------------------------------------
    # Method: testNoPathOffersOnlyMain
    # --------------------------------------------------------
    def testNoPathOffersOnlyMain(self) -> None:
        git = GitService()
        names = git.suggestBranchNames()
        assert names == ["main"]
        assert "master" not in names

    # --------------------------------------------------------
    # Method: testResolvePrefersExplicit
    # --------------------------------------------------------
    def testResolvePrefersExplicit(self) -> None:
        git = GitService()
        assert git.resolveBranchForSave(".", "develop") == "develop"
        resolved = git.resolveBranchForSave("")
        assert resolved == "main"

    # --------------------------------------------------------
    # Method: testExistingRepoListsOnlyRealLocalBranches
    # --------------------------------------------------------
    def testExistingRepoListsOnlyRealLocalBranches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / "repo"
            local.mkdir()
            TestCheckoutEmptyRemote._git(local, "init", "-b", "develop")
            TestCheckoutEmptyRemote._git(local, "config", "user.email", "t@example.com")
            TestCheckoutEmptyRemote._git(local, "config", "user.name", "Test")
            (local / "a.txt").write_text("a\n", encoding="utf-8")
            TestCheckoutEmptyRemote._git(local, "add", "a.txt")
            TestCheckoutEmptyRemote._git(local, "commit", "-m", "init")
            git = GitService()
            names = git.suggestBranchNames(local)
            assert names == ["develop"]
            assert "main" not in names
            assert "master" not in names

    # --------------------------------------------------------
    # Method: testUnbornRepoOffersOnlyMain
    # --------------------------------------------------------
    def testUnbornRepoOffersOnlyMain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / "repo"
            local.mkdir()
            TestCheckoutEmptyRemote._git(local, "init", "-b", "master")
            git = GitService()
            assert git.detectBranch(local) == "master"
            assert git.listLocalBranches(local) == []
            assert git.suggestBranchNames(local) == ["main"]


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

    # --------------------------------------------------------
    # Method: testRenamesUnbornMasterWithUntrackedFiles
    # --------------------------------------------------------
    def testRenamesUnbornMasterWithUntrackedFiles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / "local"
            bare = Path(tmp) / "remote.git"
            local.mkdir()
            self._git(local, "init", "-b", "master")
            self._git(local, "config", "user.email", "t@example.com")
            self._git(local, "config", "user.name", "Test")
            (local / "README.md").write_text("hi\n", encoding="utf-8")
            self._git(Path(tmp), "init", "--bare", str(bare))
            self._git(local, "remote", "add", "origin", str(bare))

            git = GitService()
            project = ProjectConfig(
                id="p-unborn",
                name="Demo",
                path=str(local),
                remote_url=str(bare),
                default_branch="main",
            )
            outcome = git.checkoutSavedBranch(project)
            assert outcome.success, outcome.message or outcome.title
            assert git.detectBranch(local) == "main"
            assert (local / "README.md").is_file()


# ------------------------------------------------------------
# Tests: empty remote status + first push
# ------------------------------------------------------------
class TestEmptyRemoteFirstPush:
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
    # Method: _setupEmptyRemote
    # Purpose: Local repo with origin pointing at a bare empty remote.
    # --------------------------------------------------------
    def _setupEmptyRemote(self, tmp: str, *, commit: bool) -> tuple[Path, Path, ProjectConfig]:
        local = Path(tmp) / "local"
        bare = Path(tmp) / "remote.git"
        local.mkdir()
        self._git(local, "init", "-b", "master")
        self._git(local, "config", "user.email", "t@example.com")
        self._git(local, "config", "user.name", "Test")
        (local / "README.md").write_text("hello\n", encoding="utf-8")
        if commit:
            self._git(local, "add", "README.md")
            self._git(local, "commit", "-m", "init")
        self._git(Path(tmp), "init", "--bare", str(bare))
        self._git(local, "remote", "add", "origin", str(bare))
        project = ProjectConfig(
            id="empty1",
            name="Empty",
            path=str(local),
            remote_url=str(bare),
            default_branch="master",
            username="Test",
            email="t@example.com",
        )
        return local, bare, project

    # --------------------------------------------------------
    # Method: testUntrackedFilesSuggestCommitNotResolve
    # --------------------------------------------------------
    def testUntrackedFilesSuggestCommitNotResolve(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _local, _bare, project = self._setupEmptyRemote(tmp, commit=False)
            git = GitService()
            status = git.getStatus(project, fetch=True)
            assert status.remote_empty is True
            assert status.has_local_commits is False
            assert status.dirty is True
            assert status.upstream_missing is True
            assert status.suggested_action == SuggestedAction.COMMIT
            lines = " ".join(status.plainStatusLines())
            assert "Git has no commits yet" in lines
            assert "Commit" in lines
            compare = status.dashboardCompareLines()
            assert compare[1] == "Git: empty (no branches yet)"

    # --------------------------------------------------------
    # Method: testLocalCommitSuggestsPush
    # --------------------------------------------------------
    def testLocalCommitSuggestsPush(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _local, _bare, project = self._setupEmptyRemote(tmp, commit=True)
            git = GitService()
            status = git.getStatus(project, fetch=True)
            assert status.remote_empty is True
            assert status.has_local_commits is True
            assert status.dirty is False
            assert status.suggested_action == SuggestedAction.PUSH
            lines = " ".join(status.plainStatusLines())
            assert "Push will create it" in lines

    # --------------------------------------------------------
    # Method: testFirstPushCreatesRemoteBranch
    # --------------------------------------------------------
    def testFirstPushCreatesRemoteBranch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            local, bare, project = self._setupEmptyRemote(tmp, commit=True)
            git = GitService()
            outcome = git.push(project, set_upstream=True)
            assert outcome.success is True, outcome.message or outcome.title
            heads = subprocess.run(
                ["git", "show-ref", "--heads"],
                cwd=bare,
                capture_output=True,
                text=True,
                check=False,
            )
            assert "refs/heads/master" in heads.stdout
            status = git.getStatus(project, fetch=True)
            assert status.remote_empty is False
            assert status.suggested_action == SuggestedAction.SYNCED

    # --------------------------------------------------------
    # Method: testForcePushOnEmptyRemoteSucceeds
    # --------------------------------------------------------
    def testForcePushOnEmptyRemoteSucceeds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _local, bare, project = self._setupEmptyRemote(tmp, commit=True)
            git = GitService()
            outcome = git.push(project, force=True)
            assert outcome.success is True, outcome.message or outcome.title
            heads = subprocess.run(
                ["git", "show-ref", "--heads"],
                cwd=bare,
                capture_output=True,
                text=True,
                check=False,
            )
            assert "refs/heads/master" in heads.stdout

    # --------------------------------------------------------
    # Method: testResetToRemoteOffersFirstPush
    # --------------------------------------------------------
    def testResetToRemoteOffersFirstPush(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _local, _bare, project = self._setupEmptyRemote(tmp, commit=True)
            git = GitService()
            outcome = git.resetToRemote(project)
            assert outcome.success is False
            assert "no branches yet" in outcome.message.lower()
            ids = [choice.id.value for choice in outcome.choices]
            assert "first_push" in ids

    # --------------------------------------------------------
    # Method: testUnbornThenCommitPushesMain
    # --------------------------------------------------------
    def testUnbornThenCommitPushesMain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            local, bare, project = self._setupEmptyRemote(tmp, commit=False)
            project.default_branch = "main"
            git = GitService()
            switch = git.checkoutSavedBranch(project)
            assert switch.success, switch.message or switch.title
            assert git.detectBranch(local) == "main"
            status = git.getStatus(project, fetch=True)
            assert status.suggested_action == SuggestedAction.COMMIT
            commit = git.commit(project, "initial")
            assert commit.success, commit.message or commit.title
            status = git.getStatus(project, fetch=True)
            assert status.suggested_action == SuggestedAction.PUSH
            push = git.push(project, set_upstream=True)
            assert push.success, push.message or push.title
            heads = subprocess.run(
                ["git", "show-ref", "--heads"],
                cwd=bare,
                capture_output=True,
                text=True,
                check=False,
            )
            assert "refs/heads/main" in heads.stdout
            status = git.getStatus(project, fetch=True)
            assert status.suggested_action == SuggestedAction.SYNCED

    # --------------------------------------------------------
    # Method: testInitRepoUsesSelectedBranch
    # --------------------------------------------------------
    def testInitRepoUsesSelectedBranch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "fresh"
            git = GitService()
            outcome = git.initRepo(folder, "main")
            assert outcome.success
            assert git.detectBranch(folder) == "main"
            assert git.suggestBranchNames(folder) == ["main"]

    # --------------------------------------------------------
    # Method: testFailedFetchDoesNotTrustStaleOriginRefs
    # --------------------------------------------------------
    def testFailedFetchDoesNotTrustStaleOriginRefs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            local, bare, project = self._setupEmptyRemote(tmp, commit=True)
            git = GitService()
            pushed = git.push(project, set_upstream=True)
            assert pushed.success
            empty = Path(tmp) / "empty.git"
            self._git(Path(tmp), "init", "--bare", str(empty))
            sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=local,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            self._git(local, "update-ref", "refs/remotes/origin/master", sha)
            self._git(
                local,
                "remote",
                "set-url",
                "origin",
                "https://127.0.0.1:1/nope.git",
            )
            project.remote_url = str(empty)
            status = git.getStatus(project, fetch=True)
            assert status.remote_empty is True
            assert status.suggested_action == SuggestedAction.PUSH
