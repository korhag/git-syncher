from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.core.close_check import closeWarningMessage, unsyncedProjectNames
from app.main import GitSyncherApp
from app.models.project import ProjectConfig, ProjectStatus, SuggestedAction
from app.ui.busy import BusyOverlay


# ------------------------------------------------------------
# Helper: _project
# Purpose: Minimal ProjectConfig for close-check tests.
# ------------------------------------------------------------
def _project(project_id: str, name: str) -> ProjectConfig:
    return ProjectConfig(id=project_id, name=name, path=f"/tmp/{name}")


# ------------------------------------------------------------
# Helper: _status
# Purpose: Minimal ProjectStatus for close-check tests.
# ------------------------------------------------------------
def _status(project_id: str, **kwargs) -> ProjectStatus:
    defaults = {
        "project_id": project_id,
        "is_repo": True,
        "path_exists": True,
        "branch": "main",
    }
    defaults.update(kwargs)
    return ProjectStatus(**defaults)


# ------------------------------------------------------------
# Tests: unsyncedProjectNames / closeWarningMessage
# ------------------------------------------------------------
class TestCloseCheck:
    # --------------------------------------------------------
    # Method: testNamesOnlyUnsyncedRepos
    # --------------------------------------------------------
    def testNamesOnlyUnsyncedRepos(self) -> None:
        projects = [
            _project("a", "Alpha"),
            _project("b", "Beta"),
            _project("c", "Gamma"),
        ]
        statuses = {
            "a": _status("a", suggested_action=SuggestedAction.SYNCED),
            "b": _status("b", suggested_action=SuggestedAction.PUSH, ahead=1),
            "c": _status("c", is_repo=False, suggested_action=SuggestedAction.NOT_A_REPO),
        }
        assert unsyncedProjectNames(projects, statuses) == ["Beta"]

    # --------------------------------------------------------
    # Method: testMissingStatusIsSkipped
    # --------------------------------------------------------
    def testMissingStatusIsSkipped(self) -> None:
        projects = [_project("a", "Alpha")]
        assert unsyncedProjectNames(projects, {}) == []

    # --------------------------------------------------------
    # Method: testWarningMessageSingular
    # --------------------------------------------------------
    def testWarningMessageSingular(self) -> None:
        message = closeWarningMessage(["Alpha"])
        assert "1 repository is not in sync" in message
        assert "• Alpha" in message
        assert "Do you still want to close?" in message
        assert "Stay and sync" in message

    # --------------------------------------------------------
    # Method: testWarningMessagePluralAndTruncates
    # --------------------------------------------------------
    def testWarningMessagePluralAndTruncates(self) -> None:
        names = [f"Repo {i}" for i in range(10)]
        message = closeWarningMessage(names)
        assert "10 repositories are not in sync" in message
        assert "• Repo 0" in message
        assert "• Repo 7" in message
        assert "• Repo 8" not in message
        assert "and 2 more" in message


# ------------------------------------------------------------
# Tests: BusyOverlay.whenIdle
# ------------------------------------------------------------
class TestBusyWhenIdle:
    # --------------------------------------------------------
    # Method: testRunsImmediatelyWhenIdle
    # --------------------------------------------------------
    def testRunsImmediatelyWhenIdle(self) -> None:
        busy = BusyOverlay.__new__(BusyOverlay)
        busy._busy = False
        busy._idle_callbacks = []
        called: list[int] = []
        busy.whenIdle(lambda: called.append(1))
        assert called == [1]

    # --------------------------------------------------------
    # Method: testQueuesUntilFlush
    # --------------------------------------------------------
    def testQueuesUntilFlush(self) -> None:
        busy = BusyOverlay.__new__(BusyOverlay)
        busy._busy = True
        busy._idle_callbacks = []
        called: list[int] = []
        busy.whenIdle(lambda: called.append(1))
        assert called == []
        busy._flushIdle()
        assert called == [1]


# ------------------------------------------------------------
# Tests: GitSyncherApp close guard
# ------------------------------------------------------------
class TestCloseGuard:
    # --------------------------------------------------------
    # Method: _app
    # Purpose: Bare GitSyncherApp with mocked page/window.
    # --------------------------------------------------------
    @staticmethod
    def _app() -> GitSyncherApp:
        app = GitSyncherApp.__new__(GitSyncherApp)
        app.page = MagicMock()
        app.page.window.prevent_close = True
        app.store = MagicMock()
        app.store.projects = []
        app.dashboard = None
        app.busy = BusyOverlay.__new__(BusyOverlay)
        app.busy._busy = False
        app.busy._idle_callbacks = []
        app._close_check_in_progress = False
        app._close_prompt_open = False
        return app

    # --------------------------------------------------------
    # Method: testNoProjectsClosesImmediately
    # --------------------------------------------------------
    def testNoProjectsClosesImmediately(self) -> None:
        app = self._app()
        with patch.object(GitSyncherApp, "_destroyWindow") as destroy:
            app._beginCloseCheck()
            destroy.assert_called_once()

    # --------------------------------------------------------
    # Method: testUnsyncedShowsWarningAndStayCancels
    # --------------------------------------------------------
    def testUnsyncedShowsWarningAndStayCancels(self) -> None:
        app = self._app()
        project = _project("a", "Alpha")
        app.store.projects = [project]
        dashboard = MagicMock()
        dashboard.git.isGitAvailable.return_value = True
        dashboard.statuses = {
            "a": _status("a", suggested_action=SuggestedAction.PUSH, ahead=1),
        }

        def fake_refresh(on_finished=None):
            if on_finished is not None:
                on_finished(dashboard.statuses, None)
            return True

        dashboard.refreshAll.side_effect = fake_refresh
        app.dashboard = dashboard

        with (
            patch.object(GitSyncherApp, "_destroyWindow") as destroy,
            patch("app.main.Dialogs.showWarningChoice") as warning,
            patch("app.main.Dialogs.showSnack") as snack,
        ):
            app._beginCloseCheck()
            destroy.assert_not_called()
            warning.assert_called_once()
            kwargs = warning.call_args.kwargs
            assert kwargs["stay_label"] == "Stay and sync"
            assert kwargs["continue_label"] == "Close anyway"
            assert "Alpha" in kwargs["message"]
            kwargs["on_stay"]()
            destroy.assert_not_called()
            snack.assert_called_once()
            assert app.page.window.prevent_close is True
            assert app._close_prompt_open is False

    # --------------------------------------------------------
    # Method: testSyncedAfterScanCloses
    # --------------------------------------------------------
    def testSyncedAfterScanCloses(self) -> None:
        app = self._app()
        project = _project("a", "Alpha")
        app.store.projects = [project]
        dashboard = MagicMock()
        dashboard.git.isGitAvailable.return_value = True
        synced = {"a": _status("a", suggested_action=SuggestedAction.SYNCED)}
        dashboard.statuses = synced

        def fake_refresh(on_finished=None):
            if on_finished is not None:
                on_finished(synced, None)
            return True

        dashboard.refreshAll.side_effect = fake_refresh
        app.dashboard = dashboard

        with patch.object(GitSyncherApp, "_destroyWindow") as destroy:
            app._beginCloseCheck()
            destroy.assert_called_once()

    # --------------------------------------------------------
    # Method: testStayThenCloseAnywayDestroys
    # --------------------------------------------------------
    def testCloseAnywayDestroys(self) -> None:
        app = self._app()
        project = _project("a", "Alpha")
        app.store.projects = [project]
        dashboard = MagicMock()
        dashboard.git.isGitAvailable.return_value = True
        dashboard.statuses = {
            "a": _status("a", suggested_action=SuggestedAction.COMMIT, dirty=True),
        }

        def fake_refresh(on_finished=None):
            if on_finished is not None:
                on_finished(dashboard.statuses, None)
            return True

        dashboard.refreshAll.side_effect = fake_refresh
        app.dashboard = dashboard

        with (
            patch.object(GitSyncherApp, "_destroyWindow") as destroy,
            patch("app.main.Dialogs.showWarningChoice") as warning,
        ):
            app._beginCloseCheck()
            warning.call_args.kwargs["on_continue"]()
            destroy.assert_called_once()
