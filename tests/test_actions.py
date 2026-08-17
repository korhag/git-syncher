from __future__ import annotations

from app.core.actions import ActionId, ActionMapper


# ------------------------------------------------------------
# Tests: ActionMapper
# ------------------------------------------------------------
class TestActionMapper:
    # --------------------------------------------------------
    # Method: testAuthFailure
    # --------------------------------------------------------
    def testAuthFailure(self) -> None:
        outcome = ActionMapper.mapError(
            "push",
            stderr="remote: Invalid username or password.\nAuthentication failed",
        )
        ids = [c.id for c in outcome.choices]
        assert ActionId.REENTER_PAT in ids
        assert outcome.success is False

    # --------------------------------------------------------
    # Method: testNonFastForwardPush
    # --------------------------------------------------------
    def testNonFastForwardPush(self) -> None:
        outcome = ActionMapper.mapError(
            "push",
            stderr="! [rejected] main -> main (non-fast-forward)\nerror: failed to push some refs",
        )
        ids = [c.id for c in outcome.choices]
        assert ActionId.PULL_FIRST in ids
        assert ActionId.OVERWRITE_REMOTE in ids
        overwrite = next(c for c in outcome.choices if c.id == ActionId.OVERWRITE_REMOTE)
        assert overwrite.destructive is True
        assert overwrite.requires_confirm is True

    # --------------------------------------------------------
    # Method: testPullLocalChanges
    # --------------------------------------------------------
    def testPullLocalChanges(self) -> None:
        outcome = ActionMapper.mapError(
            "pull",
            stderr="error: Your local changes to the following files would be overwritten by merge",
        )
        ids = [c.id for c in outcome.choices]
        assert ActionId.VIEW_DIFFS in ids
        assert ActionId.DISCARD_THEN_PULL in ids
        assert ActionId.STASH_THEN_PULL in ids

    # --------------------------------------------------------
    # Method: testNotARepo
    # --------------------------------------------------------
    def testNotARepo(self) -> None:
        outcome = ActionMapper.mapError(
            "status",
            stderr="fatal: not a git repository (or any of the parent directories): .git",
        )
        assert any(c.id == ActionId.INIT_REPO for c in outcome.choices)

    # --------------------------------------------------------
    # Method: testNetworkTimeout
    # --------------------------------------------------------
    def testNetworkTimeout(self) -> None:
        outcome = ActionMapper.mapError(
            "fetch",
            stderr="fatal: unable to access 'https://github.com/x/y.git/': Failed to connect: Timed out",
        )
        assert any(c.id == ActionId.RETRY for c in outcome.choices)

    # --------------------------------------------------------
    # Method: testMergeConflict
    # --------------------------------------------------------
    def testMergeConflict(self) -> None:
        outcome = ActionMapper.mapError(
            "pull",
            stderr="CONFLICT (content): Merge conflict in README.md\nAutomatic merge failed; fix conflicts",
        )
        assert any(c.id == ActionId.VIEW_DIFFS for c in outcome.choices)

    # --------------------------------------------------------
    # Method: testNoUpstream
    # --------------------------------------------------------
    def testNoUpstream(self) -> None:
        outcome = ActionMapper.mapError(
            "push",
            stderr="fatal: The current branch feature has no upstream branch.",
        )
        assert any(c.id == ActionId.FIRST_PUSH for c in outcome.choices)

    # --------------------------------------------------------
    # Method: testSuccessHelper
    # --------------------------------------------------------
    def testSuccessHelper(self) -> None:
        outcome = ActionMapper.success("Done", "all good")
        assert outcome.success is True
        assert outcome.choices == []

    # --------------------------------------------------------
    # Method: testGenericFallbackStillHasChoices
    # --------------------------------------------------------
    def testGenericFallbackStillHasChoices(self) -> None:
        outcome = ActionMapper.mapError("push", stderr="something completely unexpected")
        assert len(outcome.choices) >= 2
        assert any(c.id == ActionId.RETRY for c in outcome.choices)
        assert any(c.id == ActionId.CANCEL for c in outcome.choices)
