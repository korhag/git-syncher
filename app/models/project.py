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
    # Method: summaryLabel
    # Purpose: Short human-readable status for the card.
    # --------------------------------------------------------
    def summaryLabel(self) -> str:
        if not self.path_exists:
            return "Folder missing"
        if not self.is_repo:
            return "Not a Git repo"
        if self.error_message and self.suggested_action == SuggestedAction.UNKNOWN:
            return self.error_message
        parts: list[str] = []
        if self.branch:
            parts.append(self.branch)
        if self.dirty:
            count = len(self.changes)
            parts.append(f"{count} change{'s' if count != 1 else ''}")
        if self.ahead:
            parts.append(f"↑{self.ahead}")
        if self.behind:
            parts.append(f"↓{self.behind}")
        if self.changelog_version:
            parts.append(f"v{self.changelog_version}")
        if not parts:
            return "Clean"
        return " · ".join(parts)
