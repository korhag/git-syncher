from __future__ import annotations

from pathlib import Path

from app.core.folder_picker import expandFolderPath, pickerHelpMessage


# ------------------------------------------------------------
# Tests: folder path typing and picker help
# ------------------------------------------------------------
class TestFolderPicker:
    # --------------------------------------------------------
    # Method: testExpandHomeAndQuotes
    # --------------------------------------------------------
    def testExpandHomeAndQuotes(self) -> None:
        expanded = expandFolderPath("~/Projects/demo")
        assert Path(expanded) == Path.home() / "Projects" / "demo"
        assert expandFolderPath('  "/tmp/repo"  ') == "/tmp/repo"
        assert expandFolderPath("") == ""

    # --------------------------------------------------------
    # Method: testPickerHelpMentionsTyping
    # --------------------------------------------------------
    def testPickerHelpMentionsTyping(self) -> None:
        message = pickerHelpMessage()
        assert "type" in message.lower()
        assert "path" in message.lower()
