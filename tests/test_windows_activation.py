from __future__ import annotations

import queue
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.core import windows_activation as activation


@pytest.mark.skipif(sys.platform != "win32", reason="Windows kernel events")
def testDuplicateLaunchBeforeWindowReady(tmp_path: Path) -> None:
    lock = tmp_path / "application.lock"
    primary = activation.WindowsActivation(lock)
    primary.start()
    scheduled = queue.Queue()
    raised = Mock()

    async def to_front() -> None:
        raised()

    window = SimpleNamespace(minimized=True, visible=False, focused=False, to_front=to_front)
    page = SimpleNamespace(
        window=window,
        update=Mock(),
        run_task=lambda handler, *args: scheduled.put((handler, args)),
    )
    try:
        # A second process signals while the first is still starting Flet.
        completed = subprocess.run(
            [
                sys.executable, "-c",
                "import sys; from pathlib import Path; "
                "from app.core.windows_activation import requestActivation; "
                "sys.exit(not all(requestActivation(Path(sys.argv[1])) for _ in range(2)))",
                str(lock),
            ],
            timeout=10,
            check=False,
        )
        assert completed.returncode == 0
        primary.attach(page)
        handler, args = scheduled.get(timeout=3)
        # The fake window's native operation returns immediately.
        with pytest.raises(StopIteration):
            handler(*args).send(None)
        raised.assert_called_once()
        assert (window.minimized, window.visible, window.focused) == (False, True, True)
    finally:
        primary.close()
    page.update.assert_called_once()
    assert scheduled.empty()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows kernel events")
def testSimultaneousLaunchRetriesAndCloseReleasesEvent(tmp_path: Path, monkeypatch) -> None:
    lock = tmp_path / "application.lock"
    primary = activation.WindowsActivation(lock)
    # The primary acquired the app lock but has yet to create the event.
    monkeypatch.setattr(activation.time, "sleep", lambda _: primary.start())
    try:
        assert activation.requestActivation(lock)
    finally:
        primary.close()
    times = iter([0.0, 3.0])
    monkeypatch.setattr(activation.time, "monotonic", lambda: next(times))
    assert not activation.requestActivation(lock)


def testNonWindowsDoesNotRequestNativeActivation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    lock = tmp_path / "application.lock"
    primary = activation.WindowsActivation(lock)
    primary.start()
    page = Mock()
    primary.attach(page)
    assert not activation.requestActivation(lock)
    primary.close()
    page.run_task.assert_not_called()
