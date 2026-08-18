from __future__ import annotations

import asyncio
from typing import Callable, Optional, TypeVar

import flet as ft


T = TypeVar("T")


# ------------------------------------------------------------
# Class: BusyOverlay
# Purpose: Full-page spinner while Git (or other) work runs off
#          the UI thread so clicks get immediate feedback.
# ------------------------------------------------------------
class BusyOverlay:
    # --------------------------------------------------------
    # Method: __init__
    # Purpose: Build a hidden overlay Stack child for the page.
    # --------------------------------------------------------
    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self._busy = False
        self._message = ft.Text(
            "Working…",
            size=14,
            color=ft.Colors.ON_SURFACE,
            text_align=ft.TextAlign.CENTER,
        )
        self._ring = ft.ProgressRing(width=36, height=36, stroke_width=3)
        self.control = ft.Container(
            visible=False,
            expand=True,
            bgcolor=ft.Colors.with_opacity(0.55, ft.Colors.BLACK),
            alignment=ft.Alignment.CENTER,
            content=ft.Container(
                padding=24,
                bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                border_radius=12,
                content=ft.Column(
                    [self._ring, self._message],
                    tight=True,
                    spacing=16,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ),
        )

    # --------------------------------------------------------
    # Property: busy
    # Purpose: Whether a background job is already running.
    # --------------------------------------------------------
    @property
    def busy(self) -> bool:
        return self._busy

    # --------------------------------------------------------
    # Method: show
    # Purpose: Display the overlay with a status message.
    # --------------------------------------------------------
    def show(self, message: str) -> None:
        self._busy = True
        self._message.value = message or "Working…"
        self.control.visible = True
        # #region agent log
        from app.core.debug_log import agentLog

        agentLog(
            "B",
            "busy.py:show",
            "busy_overlay_shown",
            {"message": message or ""},
        )
        # #endregion
        self.page.update()

    # --------------------------------------------------------
    # Method: hide
    # Purpose: Hide the overlay after work finishes.
    # --------------------------------------------------------
    def hide(self) -> None:
        self._busy = False
        self.control.visible = False
        self.page.update()

    # --------------------------------------------------------
    # Method: run
    # Purpose: Show overlay, run fn on a worker thread, then hide.
    #          Schedules via page.run_task so the spinner paints first.
    # Input: message, fn (sync callable), on_done(result|exc optional).
    # --------------------------------------------------------
    def run(
        self,
        message: str,
        fn: Callable[[], T],
        on_done: Optional[Callable[[Optional[T], Optional[BaseException]], None]] = None,
    ) -> bool:
        if self._busy:
            return False

        async def _task() -> None:
            self.show(message)
            result: Optional[T] = None
            error: Optional[BaseException] = None
            try:
                result = await asyncio.to_thread(fn)
            except BaseException as exc:  # noqa: BLE001 — surface to UI callback
                error = exc
            finally:
                self.hide()
            if on_done is not None:
                on_done(result, error)

        self.page.run_task(_task)
        return True

    # --------------------------------------------------------
    # Method: runOrSnack
    # Purpose: Like run; if already busy, show a brief snack.
    # --------------------------------------------------------
    def runOrSnack(
        self,
        message: str,
        fn: Callable[[], T],
        on_done: Optional[Callable[[Optional[T], Optional[BaseException]], None]] = None,
        busy_message: str = "Please wait…",
    ) -> bool:
        started = self.run(message, fn, on_done=on_done)
        if not started:
            from app.ui.dialogs import Dialogs

            Dialogs.showSnack(self.page, busy_message)
        return started
