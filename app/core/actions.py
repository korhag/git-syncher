from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ------------------------------------------------------------
# Enum: ActionId
# Purpose: Identifiers for guided recovery choices in the UI.
# ------------------------------------------------------------
class ActionId(str, Enum):
    RETRY = "retry"
    REENTER_PAT = "reenter_pat"
    OPEN_SETTINGS = "open_settings"
    VIEW_DIFFS = "view_diffs"
    DISCARD_THEN_PULL = "discard_then_pull"
    STASH_THEN_PULL = "stash_then_pull"
    PULL_FIRST = "pull_first"
    PULL_CURRENT_BRANCH = "pull_current_branch"
    OVERWRITE_REMOTE = "overwrite_remote"
    INIT_REPO = "init_repo"
    SET_REMOTE = "set_remote"
    FIRST_PUSH = "first_push"
    KEEP_LOCAL = "keep_local"
    TAKE_REMOTE = "take_remote"
    COMPARE_FILE = "compare_file"
    CANCEL = "cancel"


# ------------------------------------------------------------
# Class: ActionChoice
# Purpose: One button option presented when Git needs guidance.
# ------------------------------------------------------------
@dataclass
class ActionChoice:
    id: ActionId
    label: str
    description: str = ""
    destructive: bool = False
    requires_confirm: bool = False


# ------------------------------------------------------------
# Class: ActionOutcome
# Purpose: Structured result mapped from a Git failure / state.
# ------------------------------------------------------------
@dataclass
class ActionOutcome:
    title: str
    message: str
    choices: list[ActionChoice] = field(default_factory=list)
    details: str = ""
    success: bool = False


# ------------------------------------------------------------
# Class: ActionMapper
# Purpose: Turn Git stderr / exit codes into user-facing choices
#          instead of dead-end error dumps.
# ------------------------------------------------------------
class ActionMapper:
    # --------------------------------------------------------
    # Method: mapError
    # Purpose: Inspect Git output and return recovery options.
    # Input: operation, stderr, stdout, returncode; optional branch context
    # Output: ActionOutcome
    # --------------------------------------------------------
    @classmethod
    def mapError(
        cls,
        operation: str,
        stderr: str = "",
        stdout: str = "",
        returncode: int = 1,
        local_branch: str = "",
        requested_branch: str = "",
    ) -> ActionOutcome:
        combined = f"{stderr}\n{stdout}".lower()
        details = (stderr or stdout or "").strip()

        if cls._isAuthFailure(combined):
            return ActionOutcome(
                title="Authentication failed",
                message="Git could not authenticate with the remote. Update your PAT or project settings.",
                choices=[
                    ActionChoice(ActionId.REENTER_PAT, "Re-enter PAT"),
                    ActionChoice(ActionId.OPEN_SETTINGS, "Open project settings"),
                    ActionChoice(ActionId.CANCEL, "Cancel"),
                ],
                details=details,
            )

        if cls._isNetworkIssue(combined):
            return ActionOutcome(
                title="Network problem",
                message="Could not reach the remote. Check your connection and try again.",
                choices=[
                    ActionChoice(ActionId.RETRY, "Retry"),
                    ActionChoice(ActionId.CANCEL, "Cancel"),
                ],
                details=details,
            )

        if cls._isMissingRemoteRef(combined):
            return cls._missingRemoteRefOutcome(
                details=details,
                local_branch=local_branch,
                requested_branch=requested_branch or cls._parseMissingRemoteRef(stderr or stdout),
            )

        if operation in ("pull", "fetch") and cls._isDivergedOrBehind(combined):
            return ActionOutcome(
                title="Local and remote differ",
                message="Your branch has local changes or has diverged from the remote. Choose how to continue.",
                choices=[
                    ActionChoice(ActionId.VIEW_DIFFS, "View diffs"),
                    ActionChoice(
                        ActionId.STASH_THEN_PULL,
                        "Stash then pull",
                        description="Temporarily save local changes, pull, then you can re-apply.",
                    ),
                    ActionChoice(
                        ActionId.DISCARD_THEN_PULL,
                        "Discard local then pull",
                        description="Throw away uncommitted local changes, then pull.",
                        destructive=True,
                        requires_confirm=True,
                    ),
                    ActionChoice(ActionId.CANCEL, "Cancel"),
                ],
                details=details,
            )

        if operation == "push" and cls._isNonFastForward(combined):
            return ActionOutcome(
                title="Push rejected",
                message="Remote has commits you do not have. Pull first, or overwrite the remote (destructive).",
                choices=[
                    ActionChoice(ActionId.PULL_FIRST, "Pull first"),
                    ActionChoice(
                        ActionId.OVERWRITE_REMOTE,
                        "Overwrite remote",
                        description="Force-push your local branch. This can erase remote commits.",
                        destructive=True,
                        requires_confirm=True,
                    ),
                    ActionChoice(ActionId.CANCEL, "Cancel"),
                ],
                details=details,
            )

        if cls._isNotARepo(combined):
            return ActionOutcome(
                title="Not a Git repository",
                message="This folder is not a Git repo yet. You can initialize one.",
                choices=[
                    ActionChoice(ActionId.INIT_REPO, "Initialize Git"),
                    ActionChoice(ActionId.CANCEL, "Cancel"),
                ],
                details=details,
            )

        if cls._isNoRemote(combined) or ("remote" in combined and "does not exist" in combined):
            return ActionOutcome(
                title="No remote configured",
                message="Set a remote URL, then try again.",
                choices=[
                    ActionChoice(ActionId.SET_REMOTE, "Set remote"),
                    ActionChoice(ActionId.OPEN_SETTINGS, "Open project settings"),
                    ActionChoice(ActionId.CANCEL, "Cancel"),
                ],
                details=details,
            )

        if cls._isUnrelatedHistories(combined):
            return ActionOutcome(
                title="Unrelated histories",
                message="Local and remote histories do not share a common ancestor.",
                choices=[
                    ActionChoice(
                        ActionId.OVERWRITE_REMOTE,
                        "Overwrite remote (force push)",
                        destructive=True,
                        requires_confirm=True,
                    ),
                    ActionChoice(ActionId.OPEN_SETTINGS, "Open project settings"),
                    ActionChoice(ActionId.CANCEL, "Cancel"),
                ],
                details=details,
            )

        if cls._isMergeConflict(combined):
            return ActionOutcome(
                title="Merge conflict",
                message="Some files conflict. Compare them and keep local or take remote for each file.",
                choices=[
                    ActionChoice(ActionId.VIEW_DIFFS, "View conflicting files"),
                    ActionChoice(ActionId.CANCEL, "Cancel"),
                ],
                details=details,
            )

        if operation == "push" and cls._isNoUpstream(combined):
            return ActionOutcome(
                title="No upstream branch",
                message="This branch has never been pushed. Create it on the remote?",
                choices=[
                    ActionChoice(ActionId.FIRST_PUSH, "Push and set upstream"),
                    ActionChoice(ActionId.CANCEL, "Cancel"),
                ],
                details=details,
            )

        # Generic fallback — still offer Retry / Cancel, details expandable.
        op_label = operation or "operation"
        return ActionOutcome(
            title=f"Git {op_label} needs attention",
            message="Something went wrong. You can retry or cancel and inspect details.",
            choices=[
                ActionChoice(ActionId.RETRY, "Retry"),
                ActionChoice(ActionId.OPEN_SETTINGS, "Open project settings"),
                ActionChoice(ActionId.CANCEL, "Cancel"),
            ],
            details=details or f"Exit code {returncode}",
        )

    # --------------------------------------------------------
    # Method: _missingRemoteRefOutcome
    # Purpose: Plain next-step dialog when a remote branch name is wrong.
    # --------------------------------------------------------
    @classmethod
    def _missingRemoteRefOutcome(
        cls,
        details: str,
        local_branch: str = "",
        requested_branch: str = "",
    ) -> ActionOutcome:
        on_computer = local_branch or "this branch"
        missing = requested_branch or "that name"
        if local_branch and requested_branch and local_branch != requested_branch:
            message = (
                f"This computer is on {local_branch}. "
                f"Git does not have a branch named {requested_branch}. "
                f"Next: get updates for {local_branch} (the branch you are on)."
            )
            pull_label = f"Pull {local_branch}"
        elif local_branch:
            message = (
                f"This computer is on {local_branch}. "
                f"Git does not have a branch named {missing} yet. "
                f"Next: pull {local_branch}, or send this branch to Git."
            )
            pull_label = f"Pull {local_branch}"
        else:
            message = (
                f"Git does not have a branch named {missing}. "
                "Next: open settings to fix the branch name, or send this branch to Git."
            )
            pull_label = "Pull current branch"

        return ActionOutcome(
            title="Remote branch not found",
            message=message,
            choices=[
                ActionChoice(
                    ActionId.PULL_CURRENT_BRANCH,
                    pull_label,
                    description=f"Get updates for {on_computer} from Git.",
                ),
                ActionChoice(
                    ActionId.FIRST_PUSH,
                    "Send this branch to Git",
                    description="Create this branch on the remote (first push).",
                ),
                ActionChoice(ActionId.OPEN_SETTINGS, "Open project settings"),
                ActionChoice(ActionId.CANCEL, "Cancel"),
            ],
            details=details,
        )

    # --------------------------------------------------------
    # Method: success
    # Purpose: Build a simple success outcome.
    # --------------------------------------------------------
    @staticmethod
    def success(title: str, message: str = "") -> ActionOutcome:
        return ActionOutcome(title=title, message=message, success=True, choices=[])

    # --------------------------------------------------------
    # Helpers for classifying stderr text
    # --------------------------------------------------------
    @staticmethod
    def _isAuthFailure(text: str) -> bool:
        markers = (
            "authentication failed",
            "could not read username",
            "invalid credentials",
            "401",
            "403",
            "access denied",
            "permission denied",
            "terminal prompts disabled",
            "support for password authentication was removed",
        )
        return any(marker in text for marker in markers)

    @staticmethod
    def _isNetworkIssue(text: str) -> bool:
        markers = (
            "could not resolve host",
            "failed to connect",
            "timed out",
            "network is unreachable",
            "connection refused",
            "ssl",
            "unable to access",
        )
        return any(marker in text for marker in markers)

    @staticmethod
    def _isDivergedOrBehind(text: str) -> bool:
        markers = (
            "your local changes",
            "would be overwritten",
            "need to specify how to reconcile",
            "divergent branches",
            "must be resolved",
            "cannot pull with rebase",
        )
        return any(marker in text for marker in markers)

    @staticmethod
    def _isNonFastForward(text: str) -> bool:
        markers = (
            "non-fast-forward",
            "fetch first",
            "updates were rejected",
            "failed to push some refs",
        )
        return any(marker in text for marker in markers)

    @staticmethod
    def _isNotARepo(text: str) -> bool:
        return "not a git repository" in text

    @staticmethod
    def _isNoRemote(text: str) -> bool:
        markers = (
            "no remote",
            "does not appear to be a git repository",
            "repository not found",
        )
        return any(marker in text for marker in markers)

    @staticmethod
    def _isUnrelatedHistories(text: str) -> bool:
        return "unrelated histories" in text

    @staticmethod
    def _isMergeConflict(text: str) -> bool:
        markers = (
            "merge conflict",
            "conflict",
            "fix conflicts",
            "you have unmerged paths",
        )
        return any(marker in text for marker in markers)

    @staticmethod
    def _isNoUpstream(text: str) -> bool:
        markers = (
            "has no upstream",
            "no upstream branch",
            "set the remote as upstream",
        )
        return any(marker in text for marker in markers)

    @staticmethod
    def _isMissingRemoteRef(text: str) -> bool:
        markers = (
            "couldn't find remote ref",
            "could not find remote ref",
            "no such ref",
            "does not exist in the remote",
        )
        return any(marker in text for marker in markers)

    # --------------------------------------------------------
    # Method: _parseMissingRemoteRef
    # Purpose: Extract the missing branch name from Git stderr.
    # --------------------------------------------------------
    @staticmethod
    def _parseMissingRemoteRef(text: str) -> str:
        match = re.search(
            r"(?:couldn't|could not) find remote ref\s+(\S+)",
            text,
            re.IGNORECASE,
        )
        if match:
            return match.group(1).strip()
        match = re.search(r"no such ref[:\s]+(\S+)", text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return ""
