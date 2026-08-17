from __future__ import annotations

import re
from pathlib import Path
from typing import Optional


# Keep a Changelog style: ## [1.2.3] - 2026-08-17
_RE_BRACKET = re.compile(
    r"^##\s*\[(?P<version>v?\d+(?:\.\d+){1,3}[^\]]*)\]",
    re.MULTILINE | re.IGNORECASE,
)
# Simple headings: ## v1.2.3 or ## 1.2.3
_RE_SIMPLE = re.compile(
    r"^##\s+(?P<version>v?\d+(?:\.\d+){1,3})\b",
    re.MULTILINE | re.IGNORECASE,
)

_CHANGELOG_NAMES = ("CHANGELOG.md", "Changelog.md", "changelog.md")

# Public alias for other modules (git show origin/branch:...)
CHANGELOG_FILENAMES = _CHANGELOG_NAMES


# ------------------------------------------------------------
# Class: ChangelogParser
# Purpose: Find Changelog.md and extract the newest version.
# ------------------------------------------------------------
class ChangelogParser:
    # --------------------------------------------------------
    # Method: findChangelogPath
    # Purpose: Locate a changelog file under a project root.
    # --------------------------------------------------------
    @staticmethod
    def findChangelogPath(project_path: str | Path) -> Optional[Path]:
        root = Path(project_path)
        for name in _CHANGELOG_NAMES:
            candidate = root / name
            if candidate.is_file():
                return candidate
        return None

    # --------------------------------------------------------
    # Method: parseVersionFromText
    # Purpose: Extract the first (newest) version from markdown.
    # Input: text (str) - Changelog markdown content.
    # Output: Optional[str] - Version without leading 'v', or None.
    # --------------------------------------------------------
    @staticmethod
    def parseVersionFromText(text: str) -> Optional[str]:
        for pattern in (_RE_BRACKET, _RE_SIMPLE):
            match = pattern.search(text)
            if match:
                return ChangelogParser.normalizeVersion(match.group("version"))
        return None

    # --------------------------------------------------------
    # Method: readVersion
    # Purpose: Read changelog from disk and return newest version.
    # --------------------------------------------------------
    @classmethod
    def readVersion(cls, project_path: str | Path) -> Optional[str]:
        path = cls.findChangelogPath(project_path)
        if path is None:
            return None
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        return cls.parseVersionFromText(text)

    # --------------------------------------------------------
    # Method: suggestCommitMessage
    # Purpose: Prefer Changelog version; else bump the latest Git tag.
    # --------------------------------------------------------
    @classmethod
    def suggestCommitMessage(
        cls,
        project_path: str | Path,
        last_tag: str = "",
    ) -> Optional[str]:
        version = cls.readVersion(project_path)
        if version:
            return f"Release v{version}"
        next_version = cls.suggestNextVersionFromTag(last_tag)
        if next_version:
            if last_tag:
                return f"Release v{next_version}"
            return f"Release v{next_version}"
        return None

    # --------------------------------------------------------
    # Method: hasProperChangelog
    # Purpose: True when a changelog file exists and has a version.
    # --------------------------------------------------------
    @classmethod
    def hasProperChangelog(cls, project_path: str | Path) -> bool:
        return cls.readVersion(project_path) is not None

    # --------------------------------------------------------
    # Method: suggestNextVersionFromTag
    # Purpose: One patch higher than the latest Git tag (or 0.1.0).
    # --------------------------------------------------------
    @classmethod
    def suggestNextVersionFromTag(cls, last_tag: str = "") -> str:
        if not last_tag or not last_tag.strip():
            return "0.1.0"
        current = cls.normalizeVersion(last_tag)
        return cls.bumpPatchVersion(current)

    # --------------------------------------------------------
    # Method: bumpPatchVersion
    # Purpose: Increase the last numeric segment by one (1.2.3 -> 1.2.4).
    # --------------------------------------------------------
    @classmethod
    def bumpPatchVersion(cls, version: str) -> str:
        normalized = cls.normalizeVersion(version)
        core = re.split(r"[^\d.]", normalized, maxsplit=1)[0]
        parts = [int(p) if p.isdigit() else 0 for p in core.split(".") if p != ""]
        if not parts:
            return "0.1.0"
        while len(parts) < 3:
            parts.append(0)
        parts[-1] += 1
        return ".".join(str(p) for p in parts)

    # --------------------------------------------------------
    # Method: normalizeVersion
    # Purpose: Strip leading 'v' and whitespace for comparisons.
    # --------------------------------------------------------
    @staticmethod
    def normalizeVersion(version: str) -> str:
        cleaned = version.strip()
        if cleaned.lower().startswith("v"):
            cleaned = cleaned[1:]
        return cleaned

    # --------------------------------------------------------
    # Method: compareVersions
    # Purpose: Compare two dotted versions.
    # Output: -1 if a < b, 0 if equal, 1 if a > b.
    # --------------------------------------------------------
    @staticmethod
    def compareVersions(version_a: str, version_b: str) -> int:
        def parts(value: str) -> list[int]:
            normalized = ChangelogParser.normalizeVersion(value)
            # Drop pre-release / build suffixes for a simple numeric compare.
            core = re.split(r"[^\d.]", normalized, maxsplit=1)[0]
            numbers: list[int] = []
            for chunk in core.split("."):
                if chunk.isdigit():
                    numbers.append(int(chunk))
                else:
                    break
            return numbers or [0]

        a_parts = parts(version_a)
        b_parts = parts(version_b)
        length = max(len(a_parts), len(b_parts))
        a_parts += [0] * (length - len(a_parts))
        b_parts += [0] * (length - len(b_parts))
        if a_parts < b_parts:
            return -1
        if a_parts > b_parts:
            return 1
        return 0

    # --------------------------------------------------------
    # Method: isChangelogNewerThanTag
    # Purpose: True when changelog version is ahead of last git tag.
    # --------------------------------------------------------
    @classmethod
    def isChangelogNewerThanTag(
        cls,
        changelog_version: Optional[str],
        last_tag: str,
    ) -> bool:
        if not changelog_version:
            return False
        if not last_tag:
            return True
        tag_version = cls.normalizeVersion(last_tag)
        return cls.compareVersions(changelog_version, tag_version) > 0
