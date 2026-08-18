from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from app.core import restart as restart_mod


# ------------------------------------------------------------
# Tests: restartApp
# ------------------------------------------------------------
class TestRestartApp:
    # --------------------------------------------------------
    # Method: testMissingLauncherReturnsFalse
    # Purpose: No venv python → False, no exit.
    # --------------------------------------------------------
    def testMissingLauncherReturnsFalse(self) -> None:
        fake_root = Path("/tmp/no-such-git-syncher-root")
        with (
            patch.object(restart_mod, "projectRoot", return_value=fake_root),
            patch.object(restart_mod, "releaseAppLock") as release_mock,
            patch.object(restart_mod.subprocess, "Popen") as popen_mock,
            patch.object(restart_mod, "_scheduleHardExit") as schedule_mock,
            patch.object(restart_mod.os, "_exit") as exit_mock,
        ):
            assert restart_mod.restartApp() is False
            release_mock.assert_not_called()
            popen_mock.assert_not_called()
            schedule_mock.assert_not_called()
            exit_mock.assert_not_called()

    # --------------------------------------------------------
    # Method: testSpawnPythonwHideAndScheduleExit
    # Purpose: Prefer pythonw; no CREATE_NO_WINDOW; hide + schedule.
    # --------------------------------------------------------
    def testSpawnPythonwHideAndScheduleExit(self, tmp_path: Path) -> None:
        if restart_mod.os.name == "nt":
            python_path = tmp_path / ".venv" / "Scripts" / "pythonw.exe"
        else:
            python_path = tmp_path / ".venv" / "bin" / "python"
        python_path.parent.mkdir(parents=True)
        python_path.write_text("", encoding="utf-8")
        page = MagicMock()

        with (
            patch.object(restart_mod, "projectRoot", return_value=tmp_path),
            patch.object(restart_mod, "releaseAppLock") as release_mock,
            patch.object(restart_mod.subprocess, "Popen") as popen_mock,
            patch.object(restart_mod, "_scheduleHardExit") as schedule_mock,
        ):
            assert restart_mod.restartApp(page) is True

            release_mock.assert_called_once()
            popen_mock.assert_called_once()
            args, kwargs = popen_mock.call_args
            cmd = args[0]
            assert cmd[0] == str(python_path)
            assert "-m" in cmd and "app.main" in cmd
            if restart_mod.os.name == "nt":
                flags = kwargs.get("creationflags", 0)
                assert flags & 0x08000000 == 0  # CREATE_NO_WINDOW
                assert flags & restart_mod._CREATE_NEW_PROCESS_GROUP
            schedule_mock.assert_called_once()
            assert page.window.visible is False
            page.update.assert_called_once()
            page.window.destroy.assert_not_called()
            page.window.close.assert_not_called()

    # --------------------------------------------------------
    # Method: testFallbackToPythonExe
    # Purpose: When pythonw missing, use python.exe.
    # --------------------------------------------------------
    def testFallbackToPythonExe(self, tmp_path: Path) -> None:
        if restart_mod.os.name != "nt":
            python_path = tmp_path / ".venv" / "bin" / "python"
            python_path.parent.mkdir(parents=True)
            python_path.write_text("", encoding="utf-8")
        else:
            python_path = tmp_path / ".venv" / "Scripts" / "python.exe"
            python_path.parent.mkdir(parents=True)
            python_path.write_text("", encoding="utf-8")

        with (
            patch.object(restart_mod, "projectRoot", return_value=tmp_path),
            patch.object(restart_mod, "releaseAppLock"),
            patch.object(restart_mod.subprocess, "Popen") as popen_mock,
            patch.object(restart_mod, "_scheduleHardExit"),
        ):
            assert restart_mod.restartApp() is True
            popen_mock.assert_called_once()
            cmd = popen_mock.call_args[0][0]
            assert cmd[0] == str(python_path)
            if restart_mod.os.name == "nt":
                flags = popen_mock.call_args[1].get("creationflags", 0)
                assert flags & 0x08000000 == 0  # CREATE_NO_WINDOW

    # --------------------------------------------------------
    # Method: testScheduleHardExitCallsOsExit
    # Purpose: Daemon path eventually calls os._exit(0).
    # --------------------------------------------------------
    def testScheduleHardExitCallsOsExit(self) -> None:
        with (
            patch.object(restart_mod.time, "sleep") as sleep_mock,
            patch.object(restart_mod.os, "_exit") as exit_mock,
            patch.object(restart_mod.threading, "Thread") as thread_mock,
        ):
            def run_immediate(target=None, daemon=None):
                mock = MagicMock()
                mock.start = lambda: target()
                return mock

            thread_mock.side_effect = run_immediate
            restart_mod._scheduleHardExit(delay_seconds=1.0)
            sleep_mock.assert_called_once_with(1.0)
            exit_mock.assert_called_once_with(0)

    # --------------------------------------------------------
    # Method: testRunBatAloneNotUsed
    # Purpose: run.bat alone is not enough to restart (need venv).
    # --------------------------------------------------------
    def testRunBatAloneNotUsed(self, tmp_path: Path) -> None:
        if restart_mod.os.name != "nt":
            return
        (tmp_path / "run.bat").write_text("@echo off\n", encoding="utf-8")
        with (
            patch.object(restart_mod, "projectRoot", return_value=tmp_path),
            patch.object(restart_mod.subprocess, "Popen") as popen_mock,
            patch.object(restart_mod, "_scheduleHardExit") as schedule_mock,
        ):
            assert restart_mod.restartApp() is False
            popen_mock.assert_not_called()
            schedule_mock.assert_not_called()
