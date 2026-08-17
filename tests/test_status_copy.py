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
    # Method: testDivergesFromDefault
    # --------------------------------------------------------
    def testDivergesFromDefault(self) -> None:
        status = _status(
            branch="master",
            remote_default_branch="main",
            diverges_from_default=True,
            suggested_action=SuggestedAction.MERGE,
            changelog_version="1.4.1",
            git_changelog_version="1.2.1",
        )
        lines = status.plainStatusLines()
        assert any("This computer is on master" in line for line in lines)
        assert any("default branch is main" in line for line in lines)
        assert any("not the same" in line for line in lines)
        assert not any("in sync" in line.lower() for line in lines)

        compare = status.dashboardCompareLines()
        assert compare == [
            "This computer: master · v1.4.1",
            "Git: main · v1.2.1",
        ]

    # --------------------------------------------------------
    # Method: testMergeExplain
    # --------------------------------------------------------
    def testMergeExplain(self) -> None:
        status = _status(
            branch="master",
            remote_default_branch="main",
            diverges_from_default=True,
            changelog_version="1.4.1",
            git_changelog_version="1.2.1",
        )
        explain = status.mergeExplain()
        assert "v1.4.1" in explain["body"]
        assert "v1.2.1" in explain["body"]
        assert "branch master" in explain["body"]
        assert "branch main" in explain["body"]
        assert "Neither side auto-wins" in explain["body"]
        assert "Changelog.md" in explain["body"]
        assert "After Merge (before Push)" in explain["body"]
        assert "After you Push master" in explain["body"]
        assert "GitHub main: still v1.2.1" in explain["body"]
        assert "this computer’s file → v1.4.1" in explain["body"]
        assert "GitHub main: both histories, pushed" in explain["body"]
        assert "into" in explain["bring_description"]
        assert "stay on master" in explain["bring_label"]
        assert "GitHub master: same as this computer" in explain["bring_confirm"]
        assert "pushes main" in explain["send_description"]
        assert "then push" in explain["send_label"]
        assert "back on master" in explain["send_confirm"]
        assert "this computer main · v1.2.1" in explain["match_description"]
        assert "v1.4.1" in explain["overwrite_description"]
        assert "GitHub main (website default)" in explain["overwrite_description"]

    # --------------------------------------------------------
    # Method: testUpstreamMissing
    # --------------------------------------------------------
    def testUpstreamMissing(self) -> None:
        status = _status(
            branch="feature",
            upstream_missing=True,
            suggested_action=SuggestedAction.RESOLVE,
        )
        lines = status.plainStatusLines()
        assert any("No origin/feature" in line for line in lines)

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


# ------------------------------------------------------------
# Tests: ProjectStatus.versionSummaryLines
# ------------------------------------------------------------
class TestVersionSummaryLines:
    # --------------------------------------------------------
    # Method: testLocalAndGitVersionsLabeled
    # --------------------------------------------------------
    def testLocalAndGitVersionsLabeled(self) -> None:
        status = _status(
            branch="main",
            changelog_version="0.27.1",
            git_changelog_version="0.26.0",
            last_tag="v0.26.0",
        )
        lines = status.versionSummaryLines()
        assert lines[0] == "This computer: v0.27.1"
        assert "Git (latest commit on origin/main): v0.26.0" in lines[1]
        assert "Git tag: v0.26.0" in lines[2]
        assert "local and Git differ" in lines[2]

    # --------------------------------------------------------
    # Method: testVersionsMatch
    # --------------------------------------------------------
    def testVersionsMatch(self) -> None:
        status = _status(
            branch="main",
            changelog_version="1.0.0",
            git_changelog_version="1.0.0",
            last_tag="v1.0.0",
        )
        lines = status.versionSummaryLines()
        assert "local and Git match" in lines[2]

    # --------------------------------------------------------
    # Method: testDivergesShowsDefaultBranchInGitLine
    # --------------------------------------------------------
    def testDivergesShowsDefaultBranchInGitLine(self) -> None:
        status = _status(
            branch="master",
            remote_default_branch="main",
            diverges_from_default=True,
            changelog_version="2.4.1",
            git_changelog_version="2.2.1",
            last_tag="v2.2.1",
        )
        lines = status.versionSummaryLines()
        assert "Git (latest commit on origin/main): v2.2.1" in lines[1]

    # --------------------------------------------------------
    # Method: testMissingGitChangelog
    # --------------------------------------------------------
    def testMissingGitChangelog(self) -> None:
        status = _status(
            branch="main",
            changelog_version="0.27.1",
            git_changelog_version=None,
            last_tag="",
        )
        lines = status.versionSummaryLines()
        assert "This computer: v0.27.1" in lines[0]
        assert "none" in lines[1].lower()
