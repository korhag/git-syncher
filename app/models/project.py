from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Optional


# ------------------------------------------------------------
# Enum: SuggestedAction
# Purpose: High-level next step shown on project cards.
# ------------------------------------------------------------
class SuggestedAction(str, Enum):
    SYNCED = "synced"
    COMMIT = "commit"
    PUSH = "push"
    PULL = "pull"
    MERGE = "merge"
    RESOLVE = "resolve"
    UNKNOWN = "unknown"
    NOT_A_REPO = "not_a_repo"
    MISSING_PATH = "missing_path"


# ------------------------------------------------------------
# Enum: FileChangeKind
# Purpose: Classification of a changed file in the working tree.
# ------------------------------------------------------------
class FileChangeKind(str, Enum):
    MODIFIED = "modified"
    ADDED = "added"
    DELETED = "deleted"
    RENAMED = "renamed"
    UNTRACKED = "untracked"
    CONFLICT = "conflict"
    UNKNOWN = "unknown"


# ------------------------------------------------------------
# Class: FileChange
# Purpose: Represents one changed file in a Git working tree.
# ------------------------------------------------------------
@dataclass
class FileChange:
    path: str
    kind: FileChangeKind = FileChangeKind.UNKNOWN
    staged: bool = False

    # --------------------------------------------------------
    # Method: toDict
    # Purpose: Serialize to a plain dictionary.
    # --------------------------------------------------------
    def toDict(self) -> dict[str, Any]:
        return {"path": self.path, "kind": self.kind.value, "staged": self.staged}

    # --------------------------------------------------------
    # Method: fromDict
    # Purpose: Build a FileChange from a dictionary.
    # --------------------------------------------------------
    @classmethod
    def fromDict(cls, data: dict[str, Any]) -> "FileChange":
        kind_raw = data.get("kind", "unknown")
        try:
            kind = FileChangeKind(kind_raw)
        except ValueError:
            kind = FileChangeKind.UNKNOWN
        return cls(
            path=data.get("path", ""),
            kind=kind,
            staged=bool(data.get("staged", False)),
        )


# ------------------------------------------------------------
# Class: ProjectConfig
# Purpose: Per-project settings stored in the encrypted vault.
# ------------------------------------------------------------
@dataclass
class ProjectConfig:
    id: str
    name: str
    path: str
    remote_url: str = ""
    username: str = ""
    email: str = ""
    pat: str = ""
    default_branch: str = "main"

    # --------------------------------------------------------
    # Method: toDict
    # Purpose: Serialize for vault storage.
    # --------------------------------------------------------
    def toDict(self) -> dict[str, Any]:
        return asdict(self)

    # --------------------------------------------------------
    # Method: fromDict
    # Purpose: Restore from vault JSON.
    # --------------------------------------------------------
    @classmethod
    def fromDict(cls, data: dict[str, Any]) -> "ProjectConfig":
        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name", "")),
            path=str(data.get("path", "")),
            remote_url=str(data.get("remote_url", "")),
            username=str(data.get("username", "")),
            email=str(data.get("email", "")),
            pat=str(data.get("pat", "")),
            default_branch=str(data.get("default_branch", "main")),
        )


# ------------------------------------------------------------
# Class: ProjectStatus
# Purpose: Live Git status snapshot for a project (not persisted).
# ------------------------------------------------------------
@dataclass
class ProjectStatus:
    project_id: str
    is_repo: bool = False
    path_exists: bool = True
    branch: str = ""
    remote_default_branch: str = ""
    diverges_from_default: bool = False
    upstream_missing: bool = False
    ahead: int = 0
    behind: int = 0
    dirty: bool = False
    changes: list[FileChange] = field(default_factory=list)
    last_tag: str = ""
    changelog_version: Optional[str] = None
    git_changelog_version: Optional[str] = None
    suggested_action: SuggestedAction = SuggestedAction.UNKNOWN
    error_message: str = ""
    remote_url: str = ""

    # --------------------------------------------------------
    # Method: versionSummaryLines
    # Purpose: Labeled This computer / Git commit / Git tag lines.
    # --------------------------------------------------------
    def versionSummaryLines(self) -> list[str]:
        from app.core.changelog import ChangelogParser

        if not (
            self.changelog_version or self.git_changelog_version or self.last_tag
        ):
            next_version = ChangelogParser.suggestNextVersionFromTag(self.last_tag)
            return [
                "This computer: none (no version in Changelog.md)",
                "Git (latest commit): none",
                f"Git tag: none · suggested next: v{next_version}",
            ]

        local_label = (
            f"v{self.changelog_version}"
            if self.changelog_version
            else "none (no version in Changelog.md)"
        )
        git_label = (
            f"v{self.git_changelog_version}"
            if self.git_changelog_version
            else "none (no Changelog on that commit, or remote not fetched)"
        )
        tag_label = self.last_tag if self.last_tag else "none"
        # Show Git's default branch when this computer is on a different line of history.
        git_branch = self.branch or "…"
        if self.diverges_from_default and self.remote_default_branch:
            git_branch = self.remote_default_branch
        match_note = ""
        if self.changelog_version and self.git_changelog_version:
            cmp = ChangelogParser.compareVersions(
                self.changelog_version,
                self.git_changelog_version,
            )
            if cmp == 0:
                match_note = " · local and Git match"
            else:
                match_note = " · local and Git differ"

        return [
            f"This computer: {local_label}",
            f"Git (latest commit on origin/{git_branch}): {git_label}",
            f"Git tag: {tag_label}{match_note}",
        ]

    # --------------------------------------------------------
    # Method: comparedGitBranch
    # Purpose: Remote branch name status is comparing against.
    # --------------------------------------------------------
    def comparedGitBranch(self) -> str:
        if self.diverges_from_default and self.remote_default_branch:
            return self.remote_default_branch
        return self.branch or ""

    # --------------------------------------------------------
    # Method: dashboardCompareLines
    # Purpose: Two short lines for the main-page card when local ≠ Git.
    # Output: list[str] with two lines, or empty when not needed.
    # --------------------------------------------------------
    def dashboardCompareLines(self) -> list[str]:
        if not self.path_exists or not self.is_repo:
            return []
        needs = (
            self.diverges_from_default
            or self.upstream_missing
            or bool(self.ahead and self.behind)
            or self.suggested_action
            in (SuggestedAction.MERGE, SuggestedAction.RESOLVE)
        )
        if not needs:
            return []

        local_branch = self.branch or "…"
        git_branch = self.comparedGitBranch() or "…"
        local_ver = f" · v{self.changelog_version}" if self.changelog_version else ""
        git_ver = (
            f" · v{self.git_changelog_version}" if self.git_changelog_version else ""
        )
        return [
            f"This computer: {local_branch}{local_ver}",
            f"Git: {git_branch}{git_ver}",
        ]

    # --------------------------------------------------------
    # Method: _changelogKeepHint
    # Purpose: Say how Changelog.md (the v… number) is chosen after merge.
    # --------------------------------------------------------
    @staticmethod
    def _changelogKeepHint(local_ver: str, git_ver: str) -> str:
        if local_ver == git_ver:
            return f"Changelog stays {local_ver} (same on both sides)."
        if local_ver == "unknown" or git_ver == "unknown":
            return (
                "Changelog version is whichever Changelog.md you keep "
                "if that file differs."
            )
        return (
            f"Changelog is whichever Changelog.md you keep: "
            f"this computer’s file → {local_ver}; Git’s file → {git_ver}."
        )

    # --------------------------------------------------------
    # Method: mergeExplain
    # Purpose: Now / direction / After copy for merge dialogs, including
    #          branch + Changelog version after merge and after push.
    # Output: dict with body, labels, confirms, destructive blurbs.
    # --------------------------------------------------------
    def mergeExplain(self) -> dict[str, str]:
        local = self.branch or "…"
        git = self.comparedGitBranch() or "…"
        local_ver = (
            f"v{self.changelog_version}" if self.changelog_version else "unknown"
        )
        git_ver = (
            f"v{self.git_changelog_version}"
            if self.git_changelog_version
            else "unknown"
        )
        git_role = (
            "website default"
            if self.diverges_from_default and self.remote_default_branch
            else "remote"
        )
        keep_hint = self._changelogKeepHint(local_ver, git_ver)
        card_note = (
            f"The card’s Git line shows {git} ({git_role}), not {local}."
            if local != git
            else f"The card’s Git line shows {git}."
        )

        body = (
            f"Now\n"
            f"This computer: branch {local} · {local_ver}\n"
            f"Git ({git_role}): branch {git} · {git_ver}\n"
            f"\n"
            f"These v… numbers come from Changelog.md on each branch. "
            f"A merge combines commits; it does not pick the higher version. "
            f"If the same file differs, you pick per file. Neither side auto-wins.\n"
            f"\n"
            f"① Merge Git {git} → this computer (stay on {local})\n"
            f"Merges Git {git} ({git_ver}) into this computer’s {local} ({local_ver}).\n"
            f"After Merge (before Push):\n"
            f"  This computer {local}: both histories. {keep_hint}\n"
            f"  Git {git}: still {git_ver} (website unchanged).\n"
            f"After you Push {local}:\n"
            f"  GitHub {local}: same as this computer.\n"
            f"  GitHub {git}: still {git_ver}.\n"
            f"  {card_note} It can still say Git: {git} · {git_ver}.\n"
            f"\n"
            f"② Merge this computer {local} → Git {git} (then push)\n"
            f"Merges this computer’s {local} ({local_ver}) into Git {git} ({git_ver}), "
            f"then pushes {git}. This folder returns to {local}.\n"
            f"After:\n"
            f"  GitHub {git}: both histories, pushed. {keep_hint}\n"
            f"  This computer: back on {local} · still {local_ver}.\n"
            f"  Card: This computer {local} · {local_ver} / Git {git} · "
            f"(same Changelog you kept).\n"
            f"\n"
            f"Make this computer match Git (not a merge)\n"
            f"After: this computer becomes Git’s {git} · {git_ver}. "
            f"Git online unchanged.\n"
            f"\n"
            f"Overwrite remote (not a merge)\n"
            f"After: GitHub {local}"
            + (f" and GitHub {git}" if local != git else "")
            + f" become this computer’s history · {local_ver}. No combine."
        )

        bring_label = f"① Merge Git {git} → this computer (stay on {local})"
        bring_confirm = (
            f"Merges: Git {git} ({git_ver}) into this computer’s {local} ({local_ver}).\n"
            f"\n"
            f"After Merge (before Push):\n"
            f"  This computer {local}: both histories. {keep_hint}\n"
            f"  Git {git}: still {git_ver}.\n"
            f"\n"
            f"After you Push {local}:\n"
            f"  GitHub {local}: same as this computer.\n"
            f"  GitHub {git}: still {git_ver}.\n"
            f"  {card_note}"
        )
        send_label = f"② Merge this computer {local} → Git {git} (then push)"
        send_confirm = (
            f"Merges: this computer’s {local} ({local_ver}) into Git {git} ({git_ver}), "
            f"then pushes {git}.\n"
            f"\n"
            f"After:\n"
            f"  GitHub {git}: both histories, pushed. {keep_hint}\n"
            f"  This computer: back on {local} · still {local_ver}.\n"
            f"  Card: This computer {local} · {local_ver} / Git {git} · "
            f"(same Changelog you kept)."
        )

        match_description = (
            f"Destructive: throw away this computer’s {local}; take Git {git} "
            f"({git_ver}). No combine.\n"
            f"After: this computer {git} · {git_ver}. Git online still {git} · {git_ver}."
        )
        overwrite_description = (
            f"Destructive: replace Git with this computer’s {local} ({local_ver}). "
            f"No combine.\n"
            f"After: GitHub {local}"
            + (f" and GitHub {git} (website default)" if local != git else "")
            + f": {local_ver}. This computer stays on {local} · {local_ver}."
        )

        return {
            "body": body,
            "bring_label": bring_label,
            "bring_description": bring_confirm,
            "bring_confirm": bring_confirm,
            "send_label": send_label,
            "send_description": send_confirm,
            "send_confirm": send_confirm,
            "match_description": match_description,
            "overwrite_description": overwrite_description,
            "local_branch": local,
            "git_branch": git,
        }

    # --------------------------------------------------------
    # Method: plainStatusLines
    # Purpose: Plain-English lines: this computer vs Git (remote).
    #          Changelog / tags are NOT included here.
    # Output: list[str] - one or two short sentences for the UI.
    # --------------------------------------------------------
    def plainStatusLines(self) -> list[str]:
        if not self.path_exists:
            return ["Folder missing"]
        if not self.is_repo:
            return ["Not a Git repo"]
        if self.error_message and self.suggested_action == SuggestedAction.UNKNOWN:
            return [self.error_message]

        lines: list[str] = []
        if self.branch:
            lines.append(f"Branch: {self.branch}")

        if self.diverges_from_default and self.remote_default_branch:
            lines.append(
                f"This computer is on {self.branch}. "
                f"Git’s default branch is {self.remote_default_branch}. "
                "They are not the same."
            )
            if self.dirty:
                count = len(self.changes)
                noun = "file" if count == 1 else "files"
                lines.append(
                    f"{count} {noun} changed on this computer (not saved to Git yet)"
                )
            return lines

        if self.upstream_missing:
            lines.append(
                f"No origin/{self.branch or '…'} on Git — "
                "this computer’s branch is not on the remote (or was not fetched)."
            )
            return lines

        if self.dirty:
            count = len(self.changes)
            noun = "file" if count == 1 else "files"
            lines.append(
                f"{count} {noun} changed on this computer (not saved to Git yet)"
            )
            git_gap = self._gitGapSentence()
            if git_gap:
                lines.append(git_gap)
            return lines

        git_gap = self._gitGapSentence()
        if git_gap:
            lines.append(git_gap)
            return lines

        lines.append("This computer and Git are in sync")
        return lines

    # --------------------------------------------------------
    # Method: _gitGapSentence
    # Purpose: Describe ahead/behind vs remote in plain words.
    # Output: Optional[str] - None when local and remote match.
    # --------------------------------------------------------
    def _gitGapSentence(self) -> Optional[str]:
        if self.ahead and self.behind:
            return "This computer and Git both have new commits — they differ"
        if self.ahead:
            noun = "commit" if self.ahead == 1 else "commits"
            return (
                f"This computer has {self.ahead} {noun} that Git does not have yet"
            )
        if self.behind:
            noun = "commit" if self.behind == 1 else "commits"
            return (
                f"Git has {self.behind} {noun} this computer does not have yet"
            )
        return None

    # --------------------------------------------------------
    # Method: summaryLabel
    # Purpose: Single-line status (joins plainStatusLines).
    # --------------------------------------------------------
    def summaryLabel(self) -> str:
        return " · ".join(self.plainStatusLines())
