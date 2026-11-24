from __future__ import annotations

from unittest.mock import MagicMock

from app.ui.layout import (
    dialogHeight,
    dialogWidth,
    parseXdpyinfoDimensions,
    parseXrandrCurrent,
    windowSizeForScreen,
)


# ------------------------------------------------------------
# Tests: layout helpers for small displays
# ------------------------------------------------------------
class TestLayout:
    # --------------------------------------------------------
    # Method: testParseXrandrCurrent
    # --------------------------------------------------------
    def testParseXrandrCurrent(self) -> None:
        text = (
            "Screen 0: minimum 320 x 200, current 800 x 480, "
            "maximum 16384 x 16384\n"
            "HDMI-1 connected primary 800x480+0+0\n"
        )
        assert parseXrandrCurrent(text) == (800, 480)

    # --------------------------------------------------------
    # Method: testParseXdpyinfoDimensions
    # --------------------------------------------------------
    def testParseXdpyinfoDimensions(self) -> None:
        text = "  dimensions:    1024x600 pixels (271x203 millimeters)\n"
        assert parseXdpyinfoDimensions(text) == (1024, 600)

    # --------------------------------------------------------
    # Method: testWindowFitsInsideSmallScreen
    # Purpose: Never request a window larger than the monitor,
    #          and never a min size larger than the usable area.
    # --------------------------------------------------------
    def testWindowFitsInsideSmallScreen(self) -> None:
        width, height, min_w, min_h, maximize = windowSizeForScreen(800, 480)
        assert width <= 800
        assert height <= 480
        assert min_w <= width
        assert min_h <= height
        assert maximize is True

    # --------------------------------------------------------
    # Method: testLaptopKeepsPreferredSize
    # --------------------------------------------------------
    def testLaptopKeepsPreferredSize(self) -> None:
        width, height, min_w, min_h, maximize = windowSizeForScreen(1920, 1080)
        assert width == 960
        assert height == 860
        assert min_w == 360
        assert min_h == 400
        assert maximize is False

    # --------------------------------------------------------
    # Method: testDialogsShrinkOnShortPage
    # --------------------------------------------------------
    def testDialogsShrinkOnShortPage(self) -> None:
        page = MagicMock()
        page.width = 800
        page.height = 480
        page.window.width = 800
        page.window.height = 480
        assert dialogHeight(page, preferred=420) < 420
        assert dialogHeight(page, preferred=420) <= 480

    # --------------------------------------------------------
    # Method: testDialogsShrinkOnNarrowPage
    # --------------------------------------------------------
    def testDialogsShrinkOnNarrowPage(self) -> None:
        page = MagicMock()
        page.width = 400
        page.height = 800
        page.window.width = 400
        page.window.height = 800
        assert dialogWidth(page, preferred=520) < 520
        assert dialogWidth(page, preferred=520) <= 400
