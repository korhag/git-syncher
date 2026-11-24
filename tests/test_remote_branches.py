from __future__ import annotations

from app.core.git_service import GitService


# ------------------------------------------------------------
# Tests: GitService.parseLsRemoteHeads
# ------------------------------------------------------------
class TestParseLsRemoteHeads:
    # --------------------------------------------------------
    # Method: testParsesHeadsIgnoresTags
    # --------------------------------------------------------
    def testParsesHeadsIgnoresTags(self) -> None:
        stdout = (
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\trefs/heads/main\n"
            "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\trefs/heads/master\n"
            "cccccccccccccccccccccccccccccccccccccccc\trefs/tags/v1.0.0\n"
            "dddddddddddddddddddddddddddddddddddddddd\trefs/heads/feature/foo\n"
        )
        assert GitService.parseLsRemoteHeads(stdout) == [
            "main",
            "master",
            "feature/foo",
        ]

    # --------------------------------------------------------
    # Method: testEmptyAndJunk
    # --------------------------------------------------------
    def testEmptyAndJunk(self) -> None:
        assert GitService.parseLsRemoteHeads("") == []
        assert GitService.parseLsRemoteHeads("not a ref line\n") == []

    # --------------------------------------------------------
    # Method: testDedupes
    # --------------------------------------------------------
    def testDedupes(self) -> None:
        stdout = (
            "aaa\trefs/heads/main\n"
            "bbb\trefs/heads/main\n"
        )
        assert GitService.parseLsRemoteHeads(stdout) == ["main"]
