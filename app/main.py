from __future__ import annotations

import flet as ft

from app.core.git_service import GitService
from app.core.instance_lock import (
    acquireAppLock,
    releaseAppLock,
    showAlreadyRunningAndExit,
)
from app.core.store import VaultStore
from app.ui.dashboard import DashboardView
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
        self._configurePage()
        page.on_close = self._onWindowClose
        self.showUnlock()

    # --------------------------------------------------------
    # Method: _configurePage
    # Purpose: Window chrome and theme defaults.
    # --------------------------------------------------------
    def _configurePage(self) -> None:
        self.page.title = "Git Syncher"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.window.width = 960
        self.page.window.height = 720
        self.page.window.min_width = 720
        self.page.window.min_height = 520
        self.page.padding = 0
        self.page.theme = ft.Theme(color_scheme_seed=ft.Colors.TEAL)

    # --------------------------------------------------------
    # Method: _onWindowClose
    # Purpose: Release the single-instance lock on exit.
    # --------------------------------------------------------
    def _onWindowClose(self, _e: ft.ControlEvent) -> None:
        releaseAppLock()

    # --------------------------------------------------------
    # Method: clear
    # Purpose: Remove all page controls before switching views.
    # --------------------------------------------------------
    def clear(self) -> None:
        self.page.controls.clear()
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
        self.page.add(view.build())
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
            on_open_project=self.showProjectDetail,
            on_lock=self.lockVault,
        )
        self.page.add(self.dashboard.build())
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
            project_id=project_id,
            on_back=self.showDashboard,
            dashboard=self.dashboard,
        )
        self.page.add(detail.build())
        self.page.update()

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
# Script entry: python -m app.main
# ------------------------------------------------------------
if __name__ == "__main__":
    if not acquireAppLock():
        showAlreadyRunningAndExit()
    try:
        ft.run(main)
    finally:
        releaseAppLock()
