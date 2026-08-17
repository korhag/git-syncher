from __future__ import annotations

import tempfile
from pathlib import Path

from app.core.instance_lock import InstanceLock


# ------------------------------------------------------------
# Tests: InstanceLock
# ------------------------------------------------------------
class TestInstanceLock:
    # --------------------------------------------------------
    # Method: testSecondAcquireFailsWhileHeld
    # --------------------------------------------------------
    def testSecondAcquireFailsWhileHeld(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / "git-syncher.lock"
            first = InstanceLock(lock_path=lock_path)
            second = InstanceLock(lock_path=lock_path)

            assert first.tryAcquire() is True
            assert second.tryAcquire() is False

            first.release()
            assert second.tryAcquire() is True
            second.release()

    # --------------------------------------------------------
    # Method: testReleaseAllowsReacquire
    # --------------------------------------------------------
    def testReleaseAllowsReacquire(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / "git-syncher.lock"
            lock = InstanceLock(lock_path=lock_path)
            assert lock.tryAcquire() is True
            lock.release()
            assert lock.isHeld() is False
            assert lock.tryAcquire() is True
            lock.release()
