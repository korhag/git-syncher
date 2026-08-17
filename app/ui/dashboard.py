from __future__ import annotations

import uuid
from typing import Callable, Optional

import flet as ft

from app.core.changelog import ChangelogParser
from app.core.git_service import GitService
from app.core.store import VaultStore
from app.models.project import ProjectConfig, ProjectStatus, SuggestedAction
from app.ui.dialogs import Dialogs


# Action chip colors / labels
_ACTION_META: dict[SuggestedAction, tuple[str, str]] = {
    SuggestedAction.SYNCED: ("Synced", ft.Colors.GREEN_400),
    SuggestedAction.COMMIT: ("Commit", ft.Colors.AMBER_400),
    SuggestedAction.PUSH: ("Push", ft.Colors.BLUE_400),
    SuggestedAction.PULL: ("Pull", ft.Colors.CYAN_400),
    SuggestedAction.RESOLVE: ("Resolve", ft.Colors.ORANGE_400),
    SuggestedAction.NOT_A_REPO: ("Init Git", ft.Colors.GREY_400),
    SuggestedAction.MISSING_PATH: ("Missing", ft.Colors.RED_400),
    SuggestedAction.UNKNOWN: ("Check", ft.Colors.GREY_400),
}


# ------------------------------------------------------------
# Class: DashboardView
# Purpose: Project cards, Refresh all, and Add project entry.
# ------------------------------------------------------------
class DashboardView:
    # --------------------------------------------------------
    # Method: __init__
    # Purpose: Wire store, git service, and navigation callbacks.
    # --------------------------------------------------------
    def __init__(
        self,
        page: ft.Page,
        store: VaultStore,
        git: GitService,
        on_open_project: Callable[[str], None],
        on_lock: Callable[[], None],
    ) -> None:
        self.page = page
        self.store = store
        self.git = git
        self.on_open_project = on_open_project
        self.on_lock = on_lock
        self.statuses: dict[str, ProjectStatus] = {}
        self.list_column = ft.Column(spacing=12, expand=True, scroll=ft.ScrollMode.AUTO)
        self.refreshing = False
        self.status_text = ft.Text("", size=12, color=ft.Colors.ON_SURFACE_VARIANT)
        self.refresh_button = ft.FilledButton(
            "Refresh",
            icon=ft.Icons.REFRESH,
            on_click=lambda _e: self.refreshAll(),
        )

    # --------------------------------------------------------
    # Method: build
    # Purpose: Construct the dashboard layout.
    # --------------------------------------------------------
    def build(self) -> ft.Control:
        header = ft.Row(
            [
                ft.Row(
                    [
                        ft.Icon(ft.Icons.SYNC, color=ft.Colors.PRIMARY),
                        ft.Text("Git Syncher", size=22, weight=ft.FontWeight.BOLD),
                    ],
                    spacing=8,
                ),
                ft.Row(
                    [
                        self.status_text,
                        self.refresh_button,
                        ft.OutlinedButton(
                            "Add project",
                            icon=ft.Icons.ADD,
                            on_click=lambda _e: self.openAddProjectDialog(),
                        ),
                        ft.IconButton(
                            icon=ft.Icons.LOCK,
                            tooltip="Lock vault",
                            on_click=lambda _e: self.on_lock(),
                        ),
                    ],
                    spacing=8,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        self._rebuildCards()
        return ft.Container(
            expand=True,
            padding=20,
            content=ft.Column(
                [
                    header,
                    ft.Divider(),
                    self.list_column,
                ],
                expand=True,
            ),
        )

    # --------------------------------------------------------
    # Method: refreshAll
    # Purpose: Re-query Git status for every saved project.
    # --------------------------------------------------------
    def refreshAll(self) -> None:
        if self.refreshing:
            return
        if not self.git.isGitAvailable():
            Dialogs.showSnack(self.page, "Git is not installed or not on PATH.", error=True)
            return
        self.refreshing = True
        self.refresh_button.disabled = True
        self.status_text.value = "Refreshing…"
        self.page.update()

        try:
            self.statuses = self.git.refreshAll(self.store.projects, fetch=True)
            count = len(self.store.projects)
            self.status_text.value = f"Updated {count} project{'s' if count != 1 else ''}"
        except Exception as exc:  # noqa: BLE001
            self.status_text.value = "Refresh failed"
            Dialogs.showSnack(self.page, str(exc), error=True)
        finally:
            self.refreshing = False
            self.refresh_button.disabled = False
            self._rebuildCards()
            self.page.update()

    # --------------------------------------------------------
    # Method: _rebuildCards
    # Purpose: Render project cards from store + statuses.
    # --------------------------------------------------------
    def _rebuildCards(self) -> None:
        self.list_column.controls.clear()
        if not self.store.projects:
            self.list_column.controls.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Icon(ft.Icons.FOLDER_OFF_OUTLINED, size=48, color=ft.Colors.OUTLINE),
                            ft.Text("No projects yet", size=18, weight=ft.FontWeight.W_500),
                            ft.Text(
                                "Add a folder to start tracking Git status in one place.",
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                            ft.FilledButton(
                                "Add project",
                                icon=ft.Icons.ADD,
                                on_click=lambda _e: self.openAddProjectDialog(),
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=10,
                    ),
                    alignment=ft.Alignment.CENTER,
                    padding=40,
                )
            )
            return

        for project in self.store.projects:
            status = self.statuses.get(project.id)
            self.list_column.controls.append(self._buildCard(project, status))

    # --------------------------------------------------------
    # Method: _buildCard
    # Purpose: One project summary card with suggested action.
    # --------------------------------------------------------
    def _buildCard(
        self,
        project: ProjectConfig,
        status: Optional[ProjectStatus],
    ) -> ft.Control:
        action = status.suggested_action if status else SuggestedAction.UNKNOWN
        label, color = _ACTION_META.get(action, ("Check", ft.Colors.GREY_400))
        summary = status.summaryLabel() if status else "Not refreshed yet"
        extra = ""
        if status and ChangelogParser.isChangelogNewerThanTag(
            status.changelog_version, status.last_tag
        ):
            extra = f" · Changelog v{status.changelog_version} ahead of tag"

        def open_detail(_e: ft.ControlEvent, pid: str = project.id) -> None:
            self.on_open_project(pid)

        def quick_action(_e: ft.ControlEvent, pid: str = project.id) -> None:
            self.on_open_project(pid)

        return ft.Card(
            content=ft.Container(
                padding=16,
                ink=True,
                on_click=open_detail,
                content=ft.Row(
                    [
                        ft.Column(
                            [
                                ft.Text(project.name, size=16, weight=ft.FontWeight.W_600),
                                ft.Text(
                                    project.path,
                                    size=12,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                    max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                ),
                                ft.Text(summary + extra, size=13),
                            ],
                            expand=True,
                            spacing=4,
                            alignment=ft.MainAxisAlignment.CENTER,
                        ),
                        ft.Container(
                            content=ft.Text(label, weight=ft.FontWeight.BOLD, color=color),
                            padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                            border=ft.Border.all(1, color),
                            border_radius=20,
                            on_click=quick_action,
                        ),
                        ft.Icon(ft.Icons.CHEVRON_RIGHT),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
            )
        )

    # --------------------------------------------------------
    # Method: openAddProjectDialog
    # Purpose: Folder picker + Git settings form.
    # --------------------------------------------------------
    def openAddProjectDialog(self, existing: Optional[ProjectConfig] = None) -> None:
        editing = existing is not None
        name_field = ft.TextField(label="Display name", value=existing.name if existing else "")
        path_field = ft.TextField(
            label="Folder path",
            value=existing.path if existing else "",
            read_only=True,
            expand=True,
        )
        remote_field = ft.TextField(
            label="Remote URL (HTTPS)",
            value=existing.remote_url if existing else "",
        )
        user_field = ft.TextField(
            label="Git username",
            value=existing.username if existing else "",
        )
        email_field = ft.TextField(
            label="Git email",
            value=existing.email if existing else "",
        )
        pat_field = ft.TextField(
            label="Personal Access Token (PAT)",
            value=existing.pat if existing else "",
            password=True,
            can_reveal_password=True,
        )
        branch_field = ft.TextField(
            label="Default branch",
            value=existing.default_branch if existing else "main",
        )
        init_checkbox = ft.Checkbox(
            label="Initialize Git if folder is not a repository",
            value=False,
            visible=not editing,
        )
        error_text = ft.Text("", color=ft.Colors.RED_400, size=12)

        def pick_folder(_e: ft.ControlEvent) -> None:
            async def pick() -> None:
                picker = ft.FilePicker()
                self.page.services.append(picker)
                try:
                    selected = await picker.get_directory_path(
                        dialog_title="Select project folder"
                    )
                finally:
                    if picker in self.page.services:
                        self.page.services.remove(picker)

                if not selected:
                    return

                path_field.value = selected
                if not name_field.value:
                    name_field.value = selected.replace("\\", "/").rstrip("/").split("/")[-1]
                if self.git.isRepo(selected):
                    remote_field.value = self.git.detectRemoteUrl(selected) or remote_field.value
                    branch = self.git.detectBranch(selected)
                    if branch:
                        branch_field.value = branch
                    uname, uemail = self.git.detectLocalUser(selected)
                    if uname and not user_field.value:
                        user_field.value = uname
                    if uemail and not email_field.value:
                        email_field.value = uemail
                    init_checkbox.value = False
                    init_checkbox.visible = False
                else:
                    init_checkbox.visible = True
                self.page.update()

            self.page.run_task(pick)

        def close() -> None:
            self.page.pop_dialog()

        def save(_e: ft.ControlEvent) -> None:
            path = (path_field.value or "").strip()
            name = (name_field.value or "").strip()
            if not path:
                error_text.value = "Choose a folder."
                self.page.update()
                return
            if not name:
                error_text.value = "Enter a display name."
                self.page.update()
                return

            project = existing or ProjectConfig(
                id=str(uuid.uuid4()),
                name=name,
                path=path,
            )
            project.name = name
            project.path = path
            project.remote_url = (remote_field.value or "").strip()
            project.username = (user_field.value or "").strip()
            project.email = (email_field.value or "").strip()
            project.pat = (pat_field.value or "").strip()
            project.default_branch = (branch_field.value or "main").strip() or "main"

            try:
                if not self.git.isRepo(path):
                    if init_checkbox.value:
                        outcome = self.git.initRepo(path)
                        if not outcome.success:
                            error_text.value = outcome.message
                            self.page.update()
                            return
                    else:
                        error_text.value = (
                            "Folder is not a Git repo. Check 'Initialize Git' "
                            "or pick another folder."
                        )
                        self.page.update()
                        return

                if project.remote_url:
                    remote_outcome = self.git.setRemote(path, project.remote_url)
                    if not remote_outcome.success:
                        error_text.value = remote_outcome.message
                        self.page.update()
                        return

                self.git.applyLocalIdentity(path, project.username, project.email)

                if editing:
                    self.store.updateProject(project)
                else:
                    self.store.addProject(project)

                close()
                Dialogs.showSnack(self.page, "Project saved")
                self.refreshAll()
            except Exception as exc:  # noqa: BLE001
                error_text.value = str(exc)
                self.page.update()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Edit project" if editing else "Add project"),
            content=ft.Container(
                width=480,
                content=ft.Column(
                    [
                        name_field,
                        ft.Row(
                            [
                                path_field,
                                ft.IconButton(
                                    icon=ft.Icons.FOLDER_OPEN,
                                    tooltip="Browse",
                                    on_click=pick_folder,
                                    disabled=editing,
                                ),
                            ]
                        ),
                        remote_field,
                        user_field,
                        email_field,
                        pat_field,
                        branch_field,
                        init_checkbox,
                        error_text,
                    ],
                    tight=True,
                    scroll=ft.ScrollMode.AUTO,
                    height=420,
                ),
            ),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _e: close()),
                ft.FilledButton("Save", on_click=save),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.show_dialog(dialog)
