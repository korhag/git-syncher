from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from app.core.git_service import GitService
from app.models.project import (
    FileChangeKind,
    ProjectConfig,
    VsGitPresence,
)


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
# Tests: GitService name-status parsing
# ------------------------------------------------------------
class TestParseNameStatus:
    # --------------------------------------------------------
    # Method: testTabSeparatedLetters
    # --------------------------------------------------------
    def testTabSeparatedLetters(self) -> None:
        rows = GitService.parseNameStatusLines(
            "A\tlocal-only.txt\n"
            "D\tremote-only.txt\n"
            "M\tshared.txt\n"
        )
        assert rows == [
            ("A", "local-only.txt"),
            ("D", "remote-only.txt"),
            ("M", "shared.txt"),
        ]

    # --------------------------------------------------------
    # Method: testSpaceSeparatedAndSkipsBlank
    # --------------------------------------------------------
    def testSpaceSeparatedAndSkipsBlank(self) -> None:
        rows = GitService.parseNameStatusLines("A assets/i18n/strings.csv\n\nM Cargo.toml\n")
        assert rows == [
            ("A", "assets/i18n/strings.csv"),
            ("M", "Cargo.toml"),
        ]


# ------------------------------------------------------------
# Tests: GitService.presenceFromNameStatus
# ------------------------------------------------------------
class TestPresenceFromNameStatus:
    # --------------------------------------------------------
    # Method: testLetters
    # --------------------------------------------------------
    def testLetters(self) -> None:
        assert GitService.presenceFromNameStatus("A") == VsGitPresence.ONLY_LOCAL
        assert GitService.presenceFromNameStatus("D") == VsGitPresence.ONLY_GIT
        assert GitService.presenceFromNameStatus("M") == VsGitPresence.BOTH_DIFFER
        assert GitService.presenceFromNameStatus("U") == VsGitPresence.BOTH_DIFFER
        assert GitService.presenceFromNameStatus("") is None


# ------------------------------------------------------------
# Tests: listVsGitFiles against a real origin
# ------------------------------------------------------------
class TestListVsGitFiles:
    # --------------------------------------------------------
    # Method: testOnlyLocalOnlyGitAndBoth
    # Purpose: Untracked local file, deleted-vs-origin file, and
    #          a modified shared file classify into the three groups.
    # --------------------------------------------------------
    def testOnlyLocalOnlyGitAndBoth(self) -> None:
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
            _writeFile(seed / "shared.txt", "origin version\n")
            _writeFile(seed / "remote_only.txt", "on git only\n")
            _runGit(seed, "add", ".")
            _runGit(seed, "commit", "-m", "origin tip")
            _runGit(seed, "remote", "add", "origin", str(bare))
            _runGit(seed, "push", "-u", "origin", "main")
            _runGit(bare, "symbolic-ref", "HEAD", "refs/heads/main")

            _runGit(base, "clone", str(bare), str(clone))
            _writeFile(clone / "shared.txt", "local version\n")
            (clone / "remote_only.txt").unlink()
            _writeFile(clone / "local_only.txt", "not on git\n")

            service = GitService()
            project = ProjectConfig(
                id="vs-git",
                name="demo",
                path=str(clone),
                remote_url=str(bare),
                default_branch="main",
            )
            status = service.getStatus(project, fetch=False)
            by_path = {item.path: item for item in status.vs_git_files}

            assert by_path["local_only.txt"].presence == VsGitPresence.ONLY_LOCAL
            assert by_path["local_only.txt"].kind == FileChangeKind.UNTRACKED
            assert by_path["remote_only.txt"].presence == VsGitPresence.ONLY_GIT
            assert by_path["shared.txt"].presence == VsGitPresence.BOTH_DIFFER
            assert by_path["shared.txt"].kind == FileChangeKind.MODIFIED
            assert status.pathsToCopy(VsGitPresence.ONLY_LOCAL) == ["local_only.txt"]
