from __future__ import annotations

import flet as ft

from app.core.close_check import closeWarningMessage, unsyncedProjectNames
from app.core.git_service import GitService
from app.core.instance_lock import (
    acquireAppLock,
    releaseAppLock,
    showAlreadyRunningAndExit,
)
from app.core.store import VaultStore
from app.models.project import ProjectStatus
from app.ui.busy import BusyOverlay
from app.ui.dashboard import DashboardView
from app.ui.dialogs import Dialogs
from app.ui.layout import fitWindowToScreen
from app.ui.project_detail import ProjectDetailView
from app.ui.unlock import UnlockView


# ------------------------------------------------------------
# Class: GitSyncherApp
# Purpose: Top-level window routing between unlock, dashboard,
#          and project detail screens.
# ------------------------------------------------------------
class GitSyncherApp:
    # --------------------------------------------------------
    # Method: __init__
    # Purpose: Create shared store and git service instances.
    # --------------------------------------------------------
    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self.store = VaultStore()
        self.git = GitService()
        self.dashboard: DashboardView | None = None
        self.busy = BusyOverlay(page)
        self.root_content = ft.Container(expand=True)
        self._close_check_in_progress = False
        self._close_prompt_open = False
        self._configurePage()
        page.on_close = self._onWindowClose
        page.window.on_event = self._onWindowEvent
        page.add(
            ft.Stack(
                [
                    self.root_content,
                    self.busy.control,
                ],
                expand=True,
            )
        )
        self.showUnlock()

    # --------------------------------------------------------
    # Method: _configurePage
    # Purpose: Window chrome and theme defaults.
    # --------------------------------------------------------
    def _configurePage(self) -> None:
        self.page.title = "Git Syncher"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.padding = 0
        self.page.theme = ft.Theme(color_scheme_seed=ft.Colors.TEAL)
        self.page.window.prevent_close = True
        fitWindowToScreen(self.page)

    # --------------------------------------------------------
    # Method: _onWindowClose
    # Purpose: Release the single-instance lock on exit.
    # --------------------------------------------------------
    def _onWindowClose(self, _e: ft.ControlEvent) -> None:
        releaseAppLock()

    # --------------------------------------------------------
    # Method: _onWindowEvent
    # Purpose: Intercept the close button, scan once more, and
    #          warn when repositories are still unsynced.
    # --------------------------------------------------------
    def _onWindowEvent(self, e: ft.WindowEvent) -> None:
        event_type = getattr(e, "type", None)
        type_value = getattr(event_type, "value", event_type)
        if type_value not in (ft.WindowEventType.CLOSE, "close"):
            return
        if self._close_prompt_open or self._close_check_in_progress:
            return
        self._beginCloseCheck()

    # --------------------------------------------------------
    # Method: _beginCloseCheck
    # Purpose: Wait for Git work to finish, refresh, then warn
    #          or close.
    # --------------------------------------------------------
    def _beginCloseCheck(self) -> None:
        self._close_check_in_progress = True
        self.busy.whenIdle(self._scanThenConfirmClose)

    # --------------------------------------------------------
    # Method: _scanThenConfirmClose
    # Purpose: One last refresh, then close or show a warning.
    # --------------------------------------------------------
    def _scanThenConfirmClose(self) -> None:
        dashboard = self.dashboard
        if dashboard is None or not self.store.projects:
            self._destroyWindow()
            return

        def after_scan(
            result: dict[str, ProjectStatus] | None,
            _error: BaseException | None,
        ) -> None:
            statuses = result if result is not None else dashboard.statuses
            names = unsyncedProjectNames(self.store.projects, statuses)
            if not names:
                self._destroyWindow()
                return
            self._showUnsyncedCloseWarning(names)

        if dashboard.git.isGitAvailable():
            started = dashboard.refreshAll(on_finished=after_scan)
            if started:
                return
            self.busy.whenIdle(self._scanThenConfirmClose)
            return
        after_scan(dashboard.statuses, None)

    # --------------------------------------------------------
    # Method: _showUnsyncedCloseWarning
    # Purpose: Warning notification: close anyway or stay to sync.
    # --------------------------------------------------------
    def _showUnsyncedCloseWarning(self, names: list[str]) -> None:
        self._close_check_in_progress = False
        self._close_prompt_open = True

        def stay() -> None:
            self._close_prompt_open = False
            Dialogs.showSnack(
                self.page,
                "Close cancelled — you can keep syncing.",
            )

        def close_anyway() -> None:
            self._close_prompt_open = False
            self._destroyWindow()

        Dialogs.showWarningChoice(
            self.page,
            title="Unsynced repositories",
            message=closeWarningMessage(names),
            stay_label="Stay and sync",
            continue_label="Close anyway",
            on_stay=stay,
            on_continue=close_anyway,
        )
        self.page.update()

    # --------------------------------------------------------
    # Method: _destroyWindow
    # Purpose: Allow native close and destroy the window.
    # --------------------------------------------------------
    def _destroyWindow(self) -> None:
        self._close_check_in_progress = False
        self._close_prompt_open = False
        self.page.window.prevent_close = False
        try:
            self.page.update()
        except Exception:
            pass
        releaseAppLock()

        async def destroy() -> None:
            await self.page.window.destroy()

        self.page.run_task(destroy)

    # --------------------------------------------------------
    # Method: clear
    # Purpose: Remove view content before switching screens.
    # --------------------------------------------------------
    def clear(self) -> None:
        self.root_content.content = None
        # Close any open dialogs when switching screens.
        while self.page.pop_dialog() is not None:
            pass

    # --------------------------------------------------------
    # Method: showUnlock
    # Purpose: Show create / unlock vault screen.
    # --------------------------------------------------------
    def showUnlock(self) -> None:
        self.clear()
        view = UnlockView(
            page=self.page,
            store=self.store,
            on_unlocked=self.showDashboard,
            git_available=self.git.isGitAvailable(),
            git_version=self.git.gitVersion(),
        )
        self.root_content.content = view.build()
        self.page.update()

    # --------------------------------------------------------
    # Method: showDashboard
    # Purpose: Main project list after vault unlock.
    # --------------------------------------------------------
    def showDashboard(self) -> None:
        self.clear()
        self.dashboard = DashboardView(
            page=self.page,
            store=self.store,
            git=self.git,
            busy=self.busy,
            on_open_project=self.showProjectDetail,
            on_lock=self.lockVault,
        )
        self.root_content.content = self.dashboard.build()
        self.page.update()
        # Auto-refresh once after unlock so cards are not empty.
        if self.store.projects:
            self.dashboard.refreshAll()

    # --------------------------------------------------------
    # Method: showProjectDetail
    # Purpose: Open detail screen for one project id.
    # --------------------------------------------------------
    def showProjectDetail(self, project_id: str) -> None:
        if self.dashboard is None:
            self.showDashboard()
        assert self.dashboard is not None
        self.clear()
        detail = ProjectDetailView(
            page=self.page,
            store=self.store,
            git=self.git,
            busy=self.busy,
            project_id=project_id,
            on_back=self.showDashboard,
            dashboard=self.dashboard,
        )
        self.root_content.content = detail.build()
        self.page.update()
        # Status fetch runs after the layout paints (see ProjectDetailView).
        detail.reloadAsync(silent=True)

    # --------------------------------------------------------
    # Method: lockVault
    # Purpose: Clear secrets from memory and return to unlock.
    # --------------------------------------------------------
    def lockVault(self) -> None:
        self.store.lock()
        self.dashboard = None
        self.showUnlock()


# ------------------------------------------------------------
# Function: main
# Purpose: Flet entrypoint (lock already held by __main__).
# ------------------------------------------------------------
def main(page: ft.Page) -> None:
    GitSyncherApp(page)


# ------------------------------------------------------------
# Function: runApp
# Purpose: Start Flet with ft.run (0.80+). Fail clearly if the
#          venv still has Flet 0.28 from Python 3.9.
# ------------------------------------------------------------
def runApp(target) -> None:
    if not callable(getattr(ft, "run", None)):
        flet_ver = getattr(getattr(ft, "version", None), "version", None) or "unknown"
        raise SystemExit(
            "Git Syncher needs Flet 0.80 or newer "
            f"(this venv has {flet_ver}, which has no ft.run).\n"
            "Python 3.11+ is required. Recreate the virtual environment:\n"
            "  rm -rf .venv && ./install.sh"
        )
    ft.run(target)


# ------------------------------------------------------------
# Script entry: python -m app.main
# ------------------------------------------------------------
if __name__ == "__main__":
    if not acquireAppLock():
        showAlreadyRunningAndExit()
    try:
        runApp(main)
    finally:
        releaseAppLock()
