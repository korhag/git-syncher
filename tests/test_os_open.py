from __future__ import annotations

from app.core.os_open import remoteUrlToBrowserUrl


# ------------------------------------------------------------
# Tests: remoteUrlToBrowserUrl
# ------------------------------------------------------------
class TestRemoteUrlToBrowserUrl:
    # --------------------------------------------------------
    # Method: testHttps
    # --------------------------------------------------------
    def testHttps(self) -> None:
        assert (
            remoteUrlToBrowserUrl("https://github.com/org/repo.git")
            == "https://github.com/org/repo"
        )

    # --------------------------------------------------------
    # Method: testSshScpStyle
    # --------------------------------------------------------
    def testSshScpStyle(self) -> None:
        assert (
            remoteUrlToBrowserUrl("git@github.com:org/repo.git")
            == "https://github.com/org/repo"
        )

    # --------------------------------------------------------
    # Method: testSshUri
    # --------------------------------------------------------
    def testSshUri(self) -> None:
        assert (
            remoteUrlToBrowserUrl("ssh://git@gitlab.com/group/repo.git")
            == "https://gitlab.com/group/repo"
        )

    # --------------------------------------------------------
    # Method: testEmpty
    # --------------------------------------------------------
    def testEmpty(self) -> None:
        assert remoteUrlToBrowserUrl("") is None
        assert remoteUrlToBrowserUrl("not-a-url") is None

    # --------------------------------------------------------
    # Method: testTreeBranch
    # --------------------------------------------------------
    def testTreeBranch(self) -> None:
        assert (
            remoteUrlToBrowserUrl("https://github.com/org/repo.git", branch="master")
            == "https://github.com/org/repo/tree/master"
        )
        assert (
            remoteUrlToBrowserUrl("git@github.com:org/repo.git", branch="main")
            == "https://github.com/org/repo/tree/main"
        )

    # --------------------------------------------------------
    # Method: testTreeBranchWithSlash
    # --------------------------------------------------------
    def testTreeBranchWithSlash(self) -> None:
        assert (
            remoteUrlToBrowserUrl(
                "https://github.com/org/repo.git",
                branch="feature/foo",
            )
            == "https://github.com/org/repo/tree/feature/foo"
        )
