from __future__ import annotations

import uuid
from typing import Callable, Optional

import flet as ft

from app.core.actions import ActionChoice, ActionId, ActionOutcome
from app.core.git_service import GitService
from app.core.os_open import openFolderInExplorer, openRemoteInBrowser
from app.core.restart import restartApp
from app.core.store import VaultStore
from app.models.project import ProjectConfig, ProjectStatus, SuggestedAction
from app.ui.busy import BusyOverlay
from app.ui.dialogs import Dialogs


# Action chip colors / labels
_ACTION_META: dict[SuggestedAction, tuple[str, str]] = {
    SuggestedAction.SYNCED: ("Synced", ft.Colors.GREEN_400),
    SuggestedAction.COMMIT: ("Commit", ft.Colors.AMBER_400),
    SuggestedAction.PUSH: ("Push", ft.Colors.BLUE_400),
    SuggestedAction.PULL: ("Pull", ft.Colors.CYAN_400),
    SuggestedAction.MERGE: ("Merge", ft.Colors.ORANGE_400),
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
        busy: BusyOverlay,
        on_open_project: Callable[[str], None],
        on_lock: Callable[[], None],
    ) -> None:
        self.page = page
        self.store = store
        self.git = git
        self.busy = busy
        self.on_open_project = on_open_project
        self.on_lock = on_lock
        self.statuses: dict[str, ProjectStatus] = {}
        self.list_column = ft.Column(spacing=6, expand=True, scroll=ft.ScrollMode.AUTO)
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
                            icon=ft.Icons.RESTART_ALT,
                            tooltip="Restart Git Syncher",
                            on_click=lambda _e: self._confirmRestart(),
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
    # Method: _confirmRestart
    # Purpose: Confirm, then relaunch via run.bat / run.sh and exit.
    # --------------------------------------------------------
    def _confirmRestart(self) -> None:
        def do_restart() -> None:
            if not restartApp(self.page):
                Dialogs.showSnack(
                    self.page,
                    "Could not find run.bat / run.sh next to the app.",
                    error=True,
                )

        Dialogs.showYesNo(
            self.page,
            title="Restart Git Syncher?",
            message=(
                "This closes the app and starts it again "
                "(run.bat on Windows, run.sh on Linux/macOS)."
            ),
            confirm_label="Restart",
            on_confirm=do_restart,
        )

    # --------------------------------------------------------
    # Method: refreshAll
    # Purpose: Re-query Git status for every saved project.
    # --------------------------------------------------------
    def refreshAll(self) -> None:
        if not self.git.isGitAvailable():
            Dialogs.showSnack(self.page, "Git is not installed or not on PATH.", error=True)
            return

        def work() -> dict[str, ProjectStatus]:
            return self.git.refreshAll(self.store.projects, fetch=True)

        def done(
            result: Optional[dict[str, ProjectStatus]],
            error: Optional[BaseException],
        ) -> None:
            self.refresh_button.disabled = False
            if error is not None:
                self.status_text.value = "Refresh failed"
                Dialogs.showSnack(self.page, str(error), error=True)
                self._rebuildCards()
                self.page.update()
                return
            self.statuses = result or {}
            # Persist vault (e.g. remote URL detections); do not rewrite default_branch.
            try:
                self.store.save()
            except Exception:
                pass
            count = len(self.store.projects)
            self.status_text.value = f"Updated {count} project{'s' if count != 1 else ''}"
            self._rebuildCards()
            self.page.update()

        self.refresh_button.disabled = True
        self.status_text.value = "Refreshing…"
        self.page.update()
        if not self.busy.runOrSnack("Refreshing…", work, on_done=done):
            self.refresh_button.disabled = False
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
    # Purpose: Compact two-line project row using horizontal space.
    # --------------------------------------------------------
    def _buildCard(
        self,
        project: ProjectConfig,
        status: Optional[ProjectStatus],
    ) -> ft.Control:
        action = status.suggested_action if status else SuggestedAction.UNKNOWN
        label, color = _ACTION_META.get(action, ("Check", ft.Colors.GREY_400))

        branch_name = ""
        status_sentence = "Not refreshed yet"
        compare_lines: list[str] = []
        if status:
            compare_lines = status.dashboardCompareLines()
            lines = status.plainStatusLines()
            body_lines: list[str] = []
            for line in lines:
                if line.startswith("Branch: "):
                    branch_name = line[len("Branch: ") :].strip()
                else:
                    body_lines.append(line)
            if status.branch and not branch_name:
                branch_name = status.branch
            status_sentence = " · ".join(body_lines) if body_lines else status.summaryLabel()

        def open_detail(_e: ft.ControlEvent, pid: str = project.id) -> None:
            self.on_open_project(pid)

        def quick_action(_e: ft.ControlEvent, pid: str = project.id) -> None:
            if action == SuggestedAction.MERGE:
                self.openMergeDialog(pid)
            else:
                self.on_open_project(pid)

        def open_folder(_e: ft.ControlEvent, folder: str = project.path) -> None:
            if not openFolderInExplorer(folder):
                Dialogs.showSnack(
                    self.page,
                    "Could not open folder. Check that the path still exists.",
                    error=True,
                )

        remote = ""
        if status and status.remote_url:
            remote = status.remote_url
        elif project.remote_url:
            remote = project.remote_url

        globe_branch = (
            branch_name
            or (status.branch if status else "")
            or project.default_branch
            or ""
        )

        def open_remote(
            _e: ft.ControlEvent,
            url: str = remote,
            branch: str = globe_branch,
        ) -> None:
            if not openRemoteInBrowser(url, branch=branch):
                Dialogs.showSnack(
                    self.page,
                    "No remote URL set — open project settings and add the repo URL.",
                    error=True,
                )

        def edit_project(_e: ft.ControlEvent, proj: ProjectConfig = project) -> None:
            self.openAddProjectDialog(existing=proj)

        def remove_project(_e: ft.ControlEvent, proj: ProjectConfig = project) -> None:
            self._confirmRemoveProject(proj)

        title_row_controls: list[ft.Control] = [
            ft.Text(project.name, size=15, weight=ft.FontWeight.W_600),
        ]
        if branch_name:
            title_row_controls.append(
                ft.Container(
                    content=ft.Text(branch_name, size=11, color=ft.Colors.ON_SURFACE_VARIANT),
                    padding=ft.Padding.symmetric(horizontal=8, vertical=2),
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                    border_radius=10,
                )
            )
        title_row_controls.append(ft.Container(expand=True))
        title_row_controls.extend(
            [
                ft.IconButton(
                    icon=ft.Icons.FOLDER_OPEN,
                    tooltip="Open folder in Explorer",
                    icon_size=18,
                    style=ft.ButtonStyle(padding=4),
                    on_click=open_folder,
                ),
                ft.IconButton(
                    icon=ft.Icons.PUBLIC,
                    tooltip="Open Git repo in browser",
                    icon_size=18,
                    style=ft.ButtonStyle(padding=4),
                    on_click=open_remote,
                    disabled=not bool(remote),
                ),
                ft.IconButton(
                    icon=ft.Icons.EDIT_OUTLINED,
                    tooltip="Edit project",
                    icon_size=18,
                    style=ft.ButtonStyle(padding=4),
                    on_click=edit_project,
                ),
                ft.IconButton(
                    icon=ft.Icons.DELETE_OUTLINE,
                    tooltip="Remove from Syncher",
                    icon_size=18,
                    icon_color=ft.Colors.RED_400,
                    style=ft.ButtonStyle(padding=4),
                    on_click=remove_project,
                ),
                ft.Container(
                    content=ft.Text(label, size=12, weight=ft.FontWeight.BOLD, color=color),
                    padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                    border=ft.Border.all(1, color),
                    border_radius=16,
                    on_click=quick_action,
                ),
                ft.Icon(ft.Icons.CHEVRON_RIGHT, size=18),
            ]
        )

        if compare_lines:
            status_block: ft.Control = ft.Column(
                [
                    ft.Text(
                        line,
                        size=12,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                        text_align=ft.TextAlign.RIGHT,
                    )
                    for line in compare_lines
                ],
                spacing=0,
                tight=True,
                expand=True,
                horizontal_alignment=ft.CrossAxisAlignment.END,
            )
        else:
            status_block = ft.Text(
                status_sentence,
                size=12,
                max_lines=1,
                overflow=ft.TextOverflow.ELLIPSIS,
                expand=True,
                text_align=ft.TextAlign.RIGHT,
            )

        return ft.Card(
            content=ft.Container(
                padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                ink=True,
                on_click=open_detail,
                content=ft.Column(
                    [
                        ft.Row(
                            title_row_controls,
                            spacing=8,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Row(
                            [
                                ft.Text(
                                    project.path,
                                    size=11,
                                    color=ft.Colors.ON_SURFACE_VARIANT,
                                    max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                    expand=True,
                                ),
                                status_block,
                            ],
                            spacing=12,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                    ],
                    spacing=2,
                    tight=True,
                ),
            )
        )

    # --------------------------------------------------------
    # Method: _confirmRemoveProject
    # Purpose: Confirm, then drop a Syncher entry (not disk files).
    # --------------------------------------------------------
    def _confirmRemoveProject(self, project: ProjectConfig) -> None:
        def confirm() -> None:
            self.store.removeProject(project.id)
            self.statuses.pop(project.id, None)
            Dialogs.showSnack(self.page, "Project removed from Syncher")
            self._rebuildCards()
            self.page.update()

        Dialogs.showYesNo(
            self.page,
            title="Remove project?",
            message=(
                f"Remove “{project.name}” from Git Syncher?\n"
                "This does not delete files on disk — only the Syncher entry and stored PAT."
            ),
            confirm_label="Remove",
            on_confirm=confirm,
        )

    # --------------------------------------------------------
    # Method: openMergeDialog
    # Purpose: Pick merge direction (bring Git vs send to Git).
    # --------------------------------------------------------
    def openMergeDialog(self, project_id: str) -> None:
        project = next((p for p in self.store.projects if p.id == project_id), None)
        if not project:
            return
        status = self.statuses.get(project_id)
        if status is None:
            status = ProjectStatus(project_id=project_id, is_repo=True, path_exists=True)
            status.branch = self.git.detectBranch(project.path)
            status.remote_default_branch = self.git.detectRemoteDefaultBranch(project.path)
            if (
                status.branch
                and status.remote_default_branch
                and status.branch != status.remote_default_branch
            ):
                status.diverges_from_default = True
        current = status.branch or self.git.detectBranch(project.path)
        compared = status.comparedGitBranch() or (
            self.git.detectRemoteDefaultBranch(project.path) or current
        )
        if not status.branch and current:
            status.branch = current
        explain = status.mergeExplain()

        outcome = ActionOutcome(
            title="Merge",
            message=explain["body"],
            choices=[
                ActionChoice(
                    ActionId.MERGE_BRING_REMOTE,
                    explain["bring_label"],
                    description=explain["bring_description"],
                ),
                ActionChoice(
                    ActionId.MERGE_SEND_TO_REMOTE,
                    explain["send_label"],
                    description=explain["send_description"],
                ),
                ActionChoice(
                    ActionId.MATCH_REMOTE,
                    "Make this computer match Git",
                    description=explain["match_description"],
                    destructive=True,
                    requires_confirm=True,
                ),
                ActionChoice(
                    ActionId.OVERWRITE_REMOTE,
                    "Overwrite remote",
                    description=explain["overwrite_description"],
                    destructive=True,
                    requires_confirm=True,
                ),
                ActionChoice(ActionId.CANCEL, "Cancel"),
            ],
        )

        def on_choice(action_id: ActionId) -> None:
            self._dispatchMergeChoice(project, compared, action_id, explain)

        Dialogs.showChoice(self.page, outcome, on_choice)

    # --------------------------------------------------------
    # Method: _dispatchMergeChoice
    # Purpose: Run merge / destructive resolve from the dashboard dialog.
    # --------------------------------------------------------
    def _dispatchMergeChoice(
        self,
        project: ProjectConfig,
        compared: str,
        action_id: ActionId,
        explain: Optional[dict[str, str]] = None,
    ) -> None:
        if action_id == ActionId.CANCEL:
            return

        current = self.git.detectBranch(project.path) or "…"
        text = explain or {}

        if action_id == ActionId.MERGE_BRING_REMOTE:
            Dialogs.showConfirm(
                self.page,
                title=text.get("bring_label", "Merge Git → this computer?"),
                message=text.get(
                    "bring_confirm",
                    f"Merge Git {compared} into this computer’s {current}.",
                ),
                confirm_label="Merge",
                on_confirm=lambda: self._runMergeBring(project, compared),
            )
            return

        if action_id == ActionId.MERGE_SEND_TO_REMOTE:
            Dialogs.showConfirm(
                self.page,
                title=text.get("send_label", "Merge this computer → Git?"),
                message=text.get(
                    "send_confirm",
                    f"Merge {current} into Git {compared}, then push.",
                ),
                confirm_label="Merge and push",
                on_confirm=lambda: self._runMergeSend(project, compared),
            )
            return

        if action_id == ActionId.MATCH_REMOTE:
            Dialogs.showConfirm(
                self.page,
                title="Make this computer match Git?",
                message=text.get(
                    "match_description",
                    "This deletes local commits and uncommitted files on this computer. "
                    "Git online is not changed.",
                ),
                confirm_label="Match Git",
                on_confirm=lambda: self._runMatchRemote(project),
            )
            return

        if action_id == ActionId.OVERWRITE_REMOTE:
            Dialogs.showConfirm(
                self.page,
                title="Overwrite remote?",
                message=text.get(
                    "overwrite_description",
                    "This force-pushes your local branch and can erase commits on the remote. "
                    "Only continue if you are sure.",
                ),
                confirm_label="Overwrite remote",
                on_confirm=lambda: self._runOverwriteRemote(project),
            )
            return

    def _runMergeBring(self, project: ProjectConfig, compared: str) -> None:
        def work() -> ActionOutcome:
            return self.git.mergeBringRemote(project, compared)

        def done(
            outcome: Optional[ActionOutcome],
            error: Optional[BaseException],
        ) -> None:
            if error is not None:
                Dialogs.showSnack(self.page, str(error), error=True)
                return
            assert outcome is not None
            if outcome.success:
                Dialogs.showSnack(
                    self.page,
                    outcome.title + (f" — {outcome.message}" if outcome.message else ""),
                )
                self.refreshAll()
                return
            Dialogs.showChoice(
                self.page,
                outcome,
                lambda aid: self._onMergeFailureChoice(project, aid),
            )
            self.refreshAll()

        self.busy.runOrSnack("Merging…", work, on_done=done)

    def _runMergeSend(self, project: ProjectConfig, compared: str) -> None:
        def work() -> ActionOutcome:
            return self.git.mergeSendToRemote(project, compared)

        def done(
            outcome: Optional[ActionOutcome],
            error: Optional[BaseException],
        ) -> None:
            if error is not None:
                Dialogs.showSnack(self.page, str(error), error=True)
                return
            assert outcome is not None
            if outcome.success:
                Dialogs.showSnack(
                    self.page,
                    outcome.title + (f" — {outcome.message}" if outcome.message else ""),
                )
                try:
                    self.store.save()
                except Exception:
                    pass
                self.refreshAll()
                return
            Dialogs.showChoice(
                self.page,
                outcome,
                lambda aid: self._onMergeFailureChoice(project, aid),
            )
            self.refreshAll()

        self.busy.runOrSnack("Merging and pushing…", work, on_done=done)

    def _runMatchRemote(self, project: ProjectConfig) -> None:
        def work() -> ActionOutcome:
            return self.git.resetToRemote(project)

        def done(
            outcome: Optional[ActionOutcome],
            error: Optional[BaseException],
        ) -> None:
            if error is not None:
                Dialogs.showSnack(self.page, str(error), error=True)
                return
            assert outcome is not None
            if outcome.success:
                Dialogs.showSnack(self.page, outcome.title)
                try:
                    self.store.save()
                except Exception:
                    pass
                self.refreshAll()
                return
            Dialogs.showSnack(self.page, outcome.message or outcome.title, error=True)

        self.busy.runOrSnack("Matching Git…", work, on_done=done)

    def _runOverwriteRemote(self, project: ProjectConfig) -> None:
        def work() -> ActionOutcome:
            return self.git.push(project, force=True)

        def done(
            outcome: Optional[ActionOutcome],
            error: Optional[BaseException],
        ) -> None:
            if error is not None:
                Dialogs.showSnack(self.page, str(error), error=True)
                return
            assert outcome is not None
            if outcome.success:
                Dialogs.showSnack(
                    self.page,
                    outcome.title + (f" — {outcome.message}" if outcome.message else ""),
                )
                self.refreshAll()
                return
            Dialogs.showSnack(self.page, outcome.message or outcome.title, error=True)

        self.busy.runOrSnack("Overwriting remote…", work, on_done=done)

    def _onMergeFailureChoice(self, project: ProjectConfig, action_id: ActionId) -> None:
        if action_id == ActionId.VIEW_DIFFS:
            self.on_open_project(project.id)
            return
        if action_id == ActionId.CANCEL:
            return
        if action_id == ActionId.OPEN_SETTINGS:
            self.openAddProjectDialog(existing=project)
            return
        if action_id == ActionId.RETRY:
            self.openMergeDialog(project.id)
            return

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
        initial_branch = (existing.default_branch if existing else "") or ""
        branch_options: list[ft.DropdownOption] = []
        if initial_branch:
            branch_options.append(
                ft.DropdownOption(key=initial_branch, text=initial_branch)
            )
        branch_field = ft.Dropdown(
            label="Default branch",
            hint_text="Click refresh to load branches from Git",
            value=initial_branch or None,
            options=branch_options,
            editable=True,
            expand=True,
        )
        init_checkbox = ft.Checkbox(
            label="Initialize Git if folder is not a repository",
            value=False,
            visible=not editing,
        )
        error_text = ft.Text("", color=ft.Colors.RED_400, size=12)

        def ensure_branch_option(name: str) -> None:
            name = (name or "").strip()
            if not name:
                return
            existing_keys = {
                (opt.key or opt.text or "")
                for opt in (branch_field.options or [])
            }
            if name not in existing_keys:
                branch_field.options = list(branch_field.options or []) + [
                    ft.DropdownOption(key=name, text=name)
                ]
            branch_field.value = name

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
                        ensure_branch_option(branch)
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

        def refresh_branches(_e: ft.ControlEvent) -> None:
            path = (path_field.value or "").strip()
            remote = (remote_field.value or "").strip()
            if not path:
                error_text.value = "Choose a folder first."
                self.page.update()
                return
            if not remote:
                error_text.value = "Enter a remote URL first."
                self.page.update()
                return

            temp = ProjectConfig(
                id="temp-branch-list",
                name="temp",
                path=path,
                remote_url=remote,
                username=(user_field.value or "").strip(),
                email=(email_field.value or "").strip(),
                pat=(pat_field.value or "").strip(),
            )

            def work() -> tuple[list[str], str, str]:
                return self.git.listRemoteBranches(temp)

            def done(
                result: Optional[tuple[list[str], str, str]],
                error: Optional[BaseException],
            ) -> None:
                if error is not None:
                    error_text.value = str(error)
                    self.page.update()
                    return
                assert result is not None
                branches, remote_default, err = result
                if err:
                    error_text.value = err
                    self.page.update()
                    return
                if not branches:
                    error_text.value = "No branches found on that remote."
                    self.page.update()
                    return

                branch_field.options = [
                    ft.DropdownOption(key=name, text=name) for name in branches
                ]
                current = (branch_field.value or "").strip()
                if current and current in branches:
                    branch_field.value = current
                elif remote_default and remote_default in branches:
                    branch_field.value = remote_default
                else:
                    branch_field.value = branches[0]
                error_text.value = ""
                self.page.update()

            error_text.value = "Loading branches from Git…"
            self.page.update()
            self.busy.runOrSnack("Loading branches…", work, on_done=done)

        def close() -> None:
            self.page.pop_dialog()

        save_button = ft.FilledButton("Save")

        def save(_e: ft.ControlEvent) -> None:
            if self.busy.busy:
                Dialogs.showSnack(self.page, "Please wait…")
                return
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
            branch_value = (branch_field.value or "").strip()
            if not branch_value:
                error_text.value = "Pick a default branch (click refresh to load from Git)."
                self.page.update()
                return

            dup = self.store.findDuplicate(
                path,
                branch_value,
                exclude_id=existing.id if existing else None,
            )
            if dup is not None:
                error_text.value = (
                    f"This folder is already tracked for branch {branch_value}."
                )
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
            project.default_branch = branch_value
            should_init = bool(init_checkbox.value)

            def work() -> tuple[Optional[ActionOutcome], Optional[str]]:
                """Return (switch_outcome_or_None, error_message_or_None)."""
                if not self.git.isRepo(path):
                    if should_init:
                        outcome = self.git.initRepo(path)
                        if not outcome.success:
                            return None, outcome.message or outcome.title
                    else:
                        return None, (
                            "Folder is not a Git repo. Check 'Initialize Git' "
                            "or pick another folder."
                        )

                if project.remote_url:
                    remote_outcome = self.git.setRemote(path, project.remote_url)
                    if not remote_outcome.success:
                        return None, remote_outcome.message or remote_outcome.title

                self.git.applyLocalIdentity(path, project.username, project.email)
                switch = self.git.checkoutSavedBranch(project)
                if editing:
                    self.store.updateProject(project)
                else:
                    self.store.addProject(project)
                return switch, None

            def done(
                result: Optional[tuple[Optional[ActionOutcome], Optional[str]]],
                error: Optional[BaseException],
            ) -> None:
                save_button.disabled = False
                if error is not None:
                    error_text.value = str(error)
                    self.page.update()
                    return
                assert result is not None
                switch, err_msg = result
                if err_msg:
                    error_text.value = err_msg
                    self.page.update()
                    return
                assert switch is not None
                if not switch.success:
                    # Still saved the picked branch; tell the user why checkout failed.
                    error_text.value = switch.message or switch.title
                    self.page.update()
                    self.refreshAll()
                    return

                close()
                if switch.message and switch.title.startswith("Switched"):
                    Dialogs.showSnack(self.page, switch.title)
                else:
                    Dialogs.showSnack(self.page, "Project saved")
                self.refreshAll()

            save_button.disabled = True
            error_text.value = ""
            self.page.update()
            if not self.busy.runOrSnack("Saving project…", work, on_done=done):
                save_button.disabled = False
                self.page.update()

        save_button.on_click = save

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
                        ft.Row(
                            [
                                branch_field,
                                ft.IconButton(
                                    icon=ft.Icons.REFRESH,
                                    tooltip="Load branches from Git",
                                    on_click=refresh_branches,
                                ),
                            ]
                        ),
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
                save_button,
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.show_dialog(dialog)
