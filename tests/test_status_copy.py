from __future__ import annotations

from app.models.project import FileChange, FileChangeKind, ProjectStatus, SuggestedAction


# ------------------------------------------------------------
# Helper: _status
# Purpose: Build a ProjectStatus with common defaults for tests.
# ------------------------------------------------------------
def _status(**kwargs) -> ProjectStatus:
    defaults = {
        "project_id": "test",
        "is_repo": True,
        "path_exists": True,
        "branch": "master",
    }
    defaults.update(kwargs)
    return ProjectStatus(**defaults)


# ------------------------------------------------------------
# Tests: ProjectStatus.plainStatusLines
# ------------------------------------------------------------
class TestPlainStatusLines:
    # --------------------------------------------------------
    # Method: testDirtyOnly
    # --------------------------------------------------------
    def testDirtyOnly(self) -> None:
        status = _status(
            dirty=True,
            changes=[
                FileChange(path="a.py", kind=FileChangeKind.MODIFIED),
                FileChange(path="b.py", kind=FileChangeKind.MODIFIED),
            ],
        )
        lines = status.plainStatusLines()
        assert "Branch: master" in lines
        assert "2 files changed on this computer (not saved to Git yet)" in lines
        assert not any("commits" in line.lower() and "git has" in line.lower() for line in lines)

    # --------------------------------------------------------
    # Method: testDirtyWithBehindAlsoShowsGitGap
    # --------------------------------------------------------
    def testDirtyWithBehindAlsoShowsGitGap(self) -> None:
        status = _status(
            dirty=True,
            behind=3,
            changes=[FileChange(path="a.py", kind=FileChangeKind.MODIFIED)],
        )
        lines = status.plainStatusLines()
        assert "1 file changed on this computer (not saved to Git yet)" in lines
        assert "Git has 3 commits this computer does not have yet" in lines

    # --------------------------------------------------------
    # Method: testAheadOnly
    # --------------------------------------------------------
    def testAheadOnly(self) -> None:
        status = _status(ahead=2)
        lines = status.plainStatusLines()
        assert "This computer has 2 commits that Git does not have yet" in lines
        assert "in sync" not in " ".join(lines).lower()

    # --------------------------------------------------------
    # Method: testBehindOnly
    # --------------------------------------------------------
    def testBehindOnly(self) -> None:
        status = _status(behind=1)
        lines = status.plainStatusLines()
        assert "Git has 1 commit this computer does not have yet" in lines

    # --------------------------------------------------------
    # Method: testDiverged
    # --------------------------------------------------------
    def testDiverged(self) -> None:
        status = _status(ahead=1, behind=2)
        lines = status.plainStatusLines()
        assert "This computer and Git both have new commits — they differ" in lines

    # --------------------------------------------------------
    # Method: testSynced
    # --------------------------------------------------------
    def testSynced(self) -> None:
        status = _status()
        lines = status.plainStatusLines()
        assert "This computer and Git are in sync" in lines
        # Changelog version must not appear on status lines
        status.changelog_version = "0.1.17"
        status.last_tag = "v0.1.0"
        lines = status.plainStatusLines()
        assert not any("changelog" in line.lower() for line in lines)
        assert not any("0.1.17" in line for line in lines)
        assert not any("ahead of tag" in line.lower() for line in lines)

    # --------------------------------------------------------
    # Method: testMissingPathAndNotRepo
    # --------------------------------------------------------
    def testMissingPathAndNotRepo(self) -> None:
        missing = _status(path_exists=False, is_repo=False)
        assert missing.plainStatusLines() == ["Folder missing"]
        not_repo = _status(path_exists=True, is_repo=False)
        assert not_repo.plainStatusLines() == ["Not a Git repo"]

    # --------------------------------------------------------
    # Method: testSummaryLabelJoinsLines
    # --------------------------------------------------------
    def testSummaryLabelJoinsLines(self) -> None:
        status = _status(ahead=1)
        assert " · " in status.summaryLabel()
        assert "This computer has 1 commit" in status.summaryLabel()
