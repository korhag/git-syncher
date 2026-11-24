from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional, TextIO


# ------------------------------------------------------------
# Function: defaultLockPath
# Purpose: Lock file next to the vault under data/.
# ------------------------------------------------------------
def defaultLockPath() -> Path:
    root = Path(__file__).resolve().parents[2]
    return root / "data" / "git-syncher.lock"


# ------------------------------------------------------------
# Class: InstanceLock
# Purpose: Exclusive process lock so only one Git Syncher runs.
# ------------------------------------------------------------
class InstanceLock:
    # --------------------------------------------------------
    # Method: __init__
    # Purpose: Bind to a lock file path (defaults to data/).
    # --------------------------------------------------------
    def __init__(self, lock_path: Optional[Path] = None) -> None:
        self.lock_path = lock_path or defaultLockPath()
        self._handle: Optional[TextIO] = None

    # --------------------------------------------------------
    # Method: tryAcquire
    # Purpose: Non-blocking exclusive lock; write PID on success.
    # Output: bool - True if this process now holds the lock.
    # --------------------------------------------------------
    def tryAcquire(self) -> bool:
        if self._handle is not None:
            return True

        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        # Open read/write, create if missing; keep open for lock lifetime.
        handle = open(self.lock_path, "a+", encoding="utf-8")
        try:
            if not self._lockHandle(handle):
                handle.close()
                return False
            handle.seek(0)
            handle.truncate()
            handle.write(f"{os.getpid()}\n")
            handle.flush()
            self._handle = handle
            return True
        except Exception:
            try:
                handle.close()
            except OSError:
                pass
            return False

    # --------------------------------------------------------
    # Method: release
    # Purpose: Unlock and close; delete lock file when possible.
    # --------------------------------------------------------
    def release(self) -> None:
        handle = self._handle
        self._handle = None
        if handle is None:
            return
        try:
            self._unlockHandle(handle)
        except OSError:
            pass
        try:
            handle.close()
        except OSError:
            pass
        try:
            if self.lock_path.is_file():
                self.lock_path.unlink()
        except OSError:
            pass

    # --------------------------------------------------------
    # Method: isHeld
    # Purpose: Whether this instance currently holds the lock.
    # --------------------------------------------------------
    def isHeld(self) -> bool:
        return self._handle is not None

    # --------------------------------------------------------
    # Method: _lockHandle
    # Purpose: Platform exclusive non-blocking lock on open file.
    # --------------------------------------------------------
    @staticmethod
    def _lockHandle(handle: TextIO) -> bool:
        fd = handle.fileno()
        if os.name == "nt":
            import msvcrt

            try:
                # Lock one byte from start; LK_NBLCK = non-blocking.
                handle.seek(0)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                return True
            except OSError:
                return False
        import fcntl

        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    # --------------------------------------------------------
    # Method: _unlockHandle
    # Purpose: Release platform lock on open file.
    # --------------------------------------------------------
    @staticmethod
    def _unlockHandle(handle: TextIO) -> None:
        fd = handle.fileno()
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            return
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_UN)


# Module-level lock held by the running app (restart must release it).
_APP_LOCK: Optional[InstanceLock] = None


# ------------------------------------------------------------
# Function: getAppLock
# Purpose: Shared InstanceLock for this process.
# ------------------------------------------------------------
def getAppLock() -> InstanceLock:
    global _APP_LOCK
    if _APP_LOCK is None:
        _APP_LOCK = InstanceLock()
    return _APP_LOCK


# ------------------------------------------------------------
# Function: acquireAppLock
# Purpose: Try to become the single running instance.
# ------------------------------------------------------------
def acquireAppLock() -> bool:
    return getAppLock().tryAcquire()


# ------------------------------------------------------------
# Function: releaseAppLock
# Purpose: Drop the process lock (e.g. before restart).
# ------------------------------------------------------------
def releaseAppLock() -> None:
    getAppLock().release()


# ------------------------------------------------------------
# Function: showAlreadyRunningAndExit
# Purpose: Exit immediately if another Git Syncher already holds the lock.
#          Must not call ft.run() — a second Flet window freezes the first.
# ------------------------------------------------------------
def showAlreadyRunningAndExit() -> None:
    # Do not start a second Flet window — that freezes the instance that
    # already holds the lock (pythonw UI + python.exe "Already running").
    try:
        print(
            "Git Syncher is already running. Close that window first.",
            file=sys.stderr,
        )
    except Exception:
        pass
    os._exit(0)
