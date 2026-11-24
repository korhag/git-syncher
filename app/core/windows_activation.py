from __future__ import annotations

import ctypes
import hashlib
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import flet as ft

if sys.platform == "win32":
    from ctypes import wintypes

    _kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel.CreateEventW.argtypes = [
        wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR
    ]
    _kernel.CreateEventW.restype = wintypes.HANDLE
    _kernel.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    _kernel.OpenEventW.restype = wintypes.HANDLE
    _kernel.SetEvent.argtypes = [wintypes.HANDLE]
    _kernel.SetEvent.restype = wintypes.BOOL
    _kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    _kernel.WaitForSingleObject.restype = wintypes.DWORD
    _kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel.CloseHandle.restype = wintypes.BOOL

_EVENT_MODIFY_STATE = 0x0002
_ERROR_FILE_NOT_FOUND = 2
_INFINITE = 0xFFFFFFFF
_logger = logging.getLogger(__name__)


def _eventName(lock_path: Path) -> str:
    path = os.path.normcase(str(lock_path.resolve()))
    digest = hashlib.sha256(os.fsencode(path)).hexdigest()
    return "Local\\GitSyncher.Activate." + digest


def requestActivation(lock_path: Path) -> bool:
    """Ask this checkout's existing window to come forward in this session."""
    if sys.platform != "win32":
        return False
    name = _eventName(lock_path)
    deadline = time.monotonic() + 2
    while True:
        handle = _kernel.OpenEventW(_EVENT_MODIFY_STATE, False, name)
        if handle:
            try:
                return bool(_kernel.SetEvent(handle))
            finally:
                _kernel.CloseHandle(handle)
        # A simultaneous launch can lose the lock before the winner creates
        # its event. Retry only that transient case.
        missing = ctypes.get_last_error() == _ERROR_FILE_NOT_FOUND
        if not missing or time.monotonic() >= deadline:
            return False
        time.sleep(0.05)


class WindowsActivation:
    """Keep launch requests pending until the primary Flet page is ready."""

    def __init__(self, lock_path: Path) -> None:
        self._name = _eventName(lock_path)
        self._handle = None
        self._thread: threading.Thread | None = None
        self._page: ft.Page | None = None
        self._stopping = False

    def start(self) -> None:
        if sys.platform == "win32" and self._handle is None:
            self._stopping = False
            self._handle = _kernel.CreateEventW(None, False, False, self._name)
            if not self._handle:
                _logger.warning(
                    "Could not enable window activation: %s",
                    ctypes.WinError(ctypes.get_last_error()),
                )

    def attach(self, page: ft.Page) -> None:
        self._page = page
        if self._handle and self._thread is None:
            self._thread = threading.Thread(
                target=self._listen, name="Git Syncher activation", daemon=True
            )
            self._thread.start()

    def _listen(self) -> None:
        while _kernel.WaitForSingleObject(self._handle, _INFINITE) == 0:
            if self._stopping:
                return
            page = self._page
            if page is not None:
                try:
                    page.run_task(self._restore, page)
                except RuntimeError:
                    # A launch can arrive while Flet is tearing down its session.
                    continue

    async def _restore(self, page: ft.Page) -> None:
        if self._stopping or page is not self._page:
            return
        page.window.minimized = False
        page.window.visible = True
        page.window.focused = True
        page.update()
        await page.window.to_front()

    def close(self) -> None:
        if self._handle:
            self._stopping = True
            if self._thread is not None:
                _kernel.SetEvent(self._handle)
                self._thread.join()
                self._thread = None
            _kernel.CloseHandle(self._handle)
            self._handle = None
        self._page = None
