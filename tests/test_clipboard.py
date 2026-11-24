from __future__ import annotations

from app.ui.dialogs import Dialogs


# ------------------------------------------------------------
# Class: _FakePage
# Purpose: Minimal page stand-in for clipboard helper tests.
# ------------------------------------------------------------
class _FakePage:
    def __init__(self, with_set_clipboard: bool = False) -> None:
        self.services: list[object] = []
        self.dialogs: list[object] = []
        self.copied: str | None = None
        self.width = 800
        self.height = 600
        self.window = type("Window", (), {"width": 800, "height": 600})()
        if with_set_clipboard:
            self.set_clipboard = self._setClipboard

    def _setClipboard(self, text: str) -> None:
        self.copied = text

    def update(self) -> None:
        return None

    def show_dialog(self, dialog: object) -> None:
        self.dialogs.append(dialog)

    def pop_dialog(self) -> None:
        return None


# ------------------------------------------------------------
# Tests: Dialogs.copyText
# ------------------------------------------------------------
class TestCopyText:
    # --------------------------------------------------------
    # Method: testOldSetClipboard
    # Purpose: Use page.set_clipboard when Flet still has it.
    # --------------------------------------------------------
    def testOldSetClipboard(self) -> None:
        page = _FakePage(with_set_clipboard=True)
        Dialogs.copyText(page, "a.py\nb.py", "Copied 2 paths")
        assert page.copied == "a.py\nb.py"
        assert page.dialogs

    # --------------------------------------------------------
    # Method: testFallbackWithoutRunTask
    # Purpose: No crash and a selectable dialog when async clipboard
    #          cannot be scheduled.
    # --------------------------------------------------------
    def testFallbackWithoutRunTask(self) -> None:
        page = _FakePage()
        Dialogs.copyText(page, "local-only.txt", "Copied 1 path")
        assert page.dialogs
        assert page.copied is None
