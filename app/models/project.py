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
    ahead: int = 0
    behind: int = 0
    dirty: bool = False
    changes: list[FileChange] = field(default_factory=list)
    last_tag: str = ""
    changelog_version: Optional[str] = None
    suggested_action: SuggestedAction = SuggestedAction.UNKNOWN
    error_message: str = ""
    remote_url: str = ""

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
