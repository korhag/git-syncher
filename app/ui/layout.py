from __future__ import annotations

import re
import subprocess
import sys
from typing import Optional

import flet as ft


PREFERRED_WINDOW_WIDTH = 960
PREFERRED_WINDOW_HEIGHT = 860
MIN_WINDOW_WIDTH = 360
MIN_WINDOW_HEIGHT = 400
TASKBAR_RESERVE = 64
WINDOW_MARGIN = 24
DIALOG_CHROME = 180
PAGE_GUTTER = 24


# ------------------------------------------------------------
# Function: parseXrandrCurrent
# Purpose: Read "current W x H" from `xrandr --current` output.
# ------------------------------------------------------------
def parseXrandrCurrent(text: str) -> Optional[tuple[int, int]]:
    match = re.search(r"current\s+(\d+)\s+x\s+(\d+)", text)
    if match:
        return int(match.group(1)), int(match.group(2))
    match = re.search(
        r"connected(?:\s+primary)?\s+(\d+)x(\d+)\+",
        text,
    )
    if match:
        return int(match.group(1)), int(match.group(2))
    return None


# ------------------------------------------------------------
# Function: parseXdpyinfoDimensions
# Purpose: Read "dimensions: WxH" from `xdpyinfo` output.
# ------------------------------------------------------------
def parseXdpyinfoDimensions(text: str) -> Optional[tuple[int, int]]:
    match = re.search(r"dimensions:\s+(\d+)x(\d+)", text)
    if match:
        return int(match.group(1)), int(match.group(2))
    return None


# ------------------------------------------------------------
# Function: windowSizeForScreen
# Purpose: Clamp preferred window size to the physical display.
# Output: width, height, min_width, min_height, maximize
# ------------------------------------------------------------
def windowSizeForScreen(
    screen_w: int,
    screen_h: int,
) -> tuple[int, int, int, int, bool]:
    usable_w = max(320, int(screen_w) - WINDOW_MARGIN)
    usable_h = max(320, int(screen_h) - TASKBAR_RESERVE)
    width = min(PREFERRED_WINDOW_WIDTH, usable_w)
    height = min(PREFERRED_WINDOW_HEIGHT, usable_h)
    min_width = min(MIN_WINDOW_WIDTH, usable_w)
    min_height = min(MIN_WINDOW_HEIGHT, usable_h)
    compact = screen_w < 900 or screen_h < 650
    return width, height, min_width, min_height, compact


# ------------------------------------------------------------
# Function: _availableWidth
# Purpose: Best-effort page/window width in logical pixels.
# ------------------------------------------------------------
def _availableWidth(page: ft.Page) -> float:
    for value in (page.width, getattr(page.window, "width", None)):
        if value:
            return float(value)
    return float(PREFERRED_WINDOW_WIDTH)


# ------------------------------------------------------------
# Function: _availableHeight
# Purpose: Best-effort page/window height in logical pixels.
# ------------------------------------------------------------
def _availableHeight(page: ft.Page) -> float:
    for value in (page.height, getattr(page.window, "height", None)):
        if value:
            return float(value)
    return float(PREFERRED_WINDOW_HEIGHT)


# ------------------------------------------------------------
# Function: contentWidth
# Purpose: Form column width that shrinks on a narrow window.
# ------------------------------------------------------------
def contentWidth(page: ft.Page, preferred: int = 360, gutter: int = 40) -> int:
    available = _availableWidth(page) - gutter
    return int(max(80, min(preferred, available)))


# ------------------------------------------------------------
# Function: dialogWidth
# Purpose: Modal width that stays inside the visible page.
# ------------------------------------------------------------
def dialogWidth(page: ft.Page, preferred: int = 520) -> int:
    available = _availableWidth(page) - PAGE_GUTTER
    return int(max(80, min(preferred, available)))


# ------------------------------------------------------------
# Function: dialogHeight
# Purpose: Modal body height that leaves room for title and buttons.
# ------------------------------------------------------------
def dialogHeight(page: ft.Page, preferred: int = 420) -> int:
    available = _availableHeight(page) - DIALOG_CHROME
    return int(max(80, min(preferred, available)))


# ------------------------------------------------------------
# Function: detectScreenSize
# Purpose: Physical display size, or None when it cannot be read.
# ------------------------------------------------------------
def detectScreenSize() -> Optional[tuple[int, int]]:
    if sys.platform == "win32":
        try:
            import ctypes

            user32 = ctypes.windll.user32
            return int(user32.GetSystemMetrics(0)), int(user32.GetSystemMetrics(1))
        except Exception:
            return None
    if sys.platform == "darwin":
        try:
            output = subprocess.check_output(
                [
                    "osascript",
                    "-e",
                    'tell application "Finder" to get bounds of window of desktop',
                ],
                text=True,
                timeout=2,
            )
            parts = [int(part.strip()) for part in output.replace(",", " ").split()]
            if len(parts) >= 4:
                return parts[2] - parts[0], parts[3] - parts[1]
        except Exception:
            return None
        return None
    try:
        output = subprocess.check_output(
            ["xrandr", "--current"],
            text=True,
            timeout=2,
        )
        size = parseXrandrCurrent(output)
        if size:
            return size
    except Exception:
        pass
    try:
        output = subprocess.check_output(
            ["xdpyinfo"],
            text=True,
            timeout=2,
        )
        return parseXdpyinfoDimensions(output)
    except Exception:
        return None


# ------------------------------------------------------------
# Function: fitWindowToScreen
# Purpose: Size (and maximize on compact displays) so the window
#          is not larger than the monitor.
# ------------------------------------------------------------
def fitWindowToScreen(page: ft.Page) -> None:
    page.window.resizable = True
    screen = detectScreenSize()
    if screen is None:
        page.window.width = PREFERRED_WINDOW_WIDTH
        page.window.height = PREFERRED_WINDOW_HEIGHT
        page.window.min_width = MIN_WINDOW_WIDTH
        page.window.min_height = MIN_WINDOW_HEIGHT
        # Wayland / missing xrandr: still fill the display instead of
        # opening a 960x860 window that hangs off a small monitor.
        if sys.platform.startswith("linux"):
            page.window.maximized = True
        return
    width, height, min_width, min_height, maximize = windowSizeForScreen(*screen)
    page.window.min_width = min_width
    page.window.min_height = min_height
    page.window.width = width
    page.window.height = height
    page.window.alignment = ft.Alignment.CENTER
    if maximize:
        page.window.maximized = True
