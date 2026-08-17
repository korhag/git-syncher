from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.core.changelog import ChangelogParser


# ------------------------------------------------------------
# Tests: ChangelogParser
# ------------------------------------------------------------
class TestChangelogParser:
    # --------------------------------------------------------
    # Method: testParseKeepAChangelog
    # --------------------------------------------------------
    def testParseKeepAChangelog(self) -> None:
        text = """# Changelog

## [Unreleased]

## [1.2.3] - 2026-08-17

### Added
- Feature

## [1.2.2] - 2026-07-01
"""
        assert ChangelogParser.parseVersionFromText(text) == "1.2.3"

    # --------------------------------------------------------
    # Method: testParseSimpleHeading
    # --------------------------------------------------------
    def testParseSimpleHeading(self) -> None:
        text = "## v2.0.0\n\n- stuff\n\n## v1.9.0\n"
        assert ChangelogParser.parseVersionFromText(text) == "2.0.0"

    # --------------------------------------------------------
    # Method: testParseMissing
    # --------------------------------------------------------
    def testParseMissing(self) -> None:
        assert ChangelogParser.parseVersionFromText("# No versions here") is None

    # --------------------------------------------------------
    # Method: testReadVersionFromFile
    # --------------------------------------------------------
    def testReadVersionFromFile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "CHANGELOG.md"
            path.write_text("## [0.4.1] - 2026-01-01\n", encoding="utf-8")
            assert ChangelogParser.readVersion(tmp) == "0.4.1"
            assert ChangelogParser.suggestCommitMessage(tmp) == "Release v0.4.1"

    # --------------------------------------------------------
    # Method: testCompareVersions
    # --------------------------------------------------------
    def testCompareVersions(self) -> None:
        assert ChangelogParser.compareVersions("1.2.0", "1.2.1") == -1
        assert ChangelogParser.compareVersions("2.0", "1.9.9") == 1
        assert ChangelogParser.compareVersions("v1.0.0", "1.0.0") == 0

    # --------------------------------------------------------
    # Method: testIsChangelogNewerThanTag
    # --------------------------------------------------------
    def testIsChangelogNewerThanTag(self) -> None:
        assert ChangelogParser.isChangelogNewerThanTag("1.1.0", "v1.0.0") is True
        assert ChangelogParser.isChangelogNewerThanTag("1.0.0", "v1.0.0") is False
        assert ChangelogParser.isChangelogNewerThanTag("1.0.0", "") is True
        assert ChangelogParser.isChangelogNewerThanTag(None, "v1.0.0") is False

    # --------------------------------------------------------
    # Method: testFindChangelogCaseVariants
    # --------------------------------------------------------
    def testFindChangelogCaseVariants(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "changelog.md"
            path.write_text("## 3.0.0\n", encoding="utf-8")
            found = ChangelogParser.findChangelogPath(tmp)
            assert found is not None
            # Windows filesystems are case-insensitive; accept any known name.
            assert found.name.lower() == "changelog.md"
            assert ChangelogParser.readVersion(tmp) == "3.0.0"
