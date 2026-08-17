from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from app.core.actions import ActionChoice, ActionId, ActionOutcome
from app.core.changelog import ChangelogParser
from app.core.git_service import GitService
from app.core.os_open import openFolderInExplorer, openRemoteInBrowser
from app.core.store import VaultStore
from app.models.project import FileChangeKind, ProjectConfig, ProjectStatus, SuggestedAction
from app.ui.dashboard import DashboardView, _ACTION_META
from app.ui.dialogs import Dialogs


# ------------------------------------------------------------
# Class: ProjectDetailView
# Purpose: Per-project actions — commit, pull, push, file diffs,
#          discard, and guided recovery when Git fails.
# ------------------------------------------------------------
class ProjectDetailView:
    # --------------------------------------------------------
    # Method: __init__
    # Purpose: Bind project context and navigation.
    # --------------------------------------------------------
    def __init__(
        self,
        page: ft.Page,
        store: VaultStore,
        git: GitService,
        project_id: str,
        on_back: Callable[[], None],
        dashboard: DashboardView,
    ) -> None:
        self.page = page
        self.store = store
        self.git = git
        self.project_id = project_id
        self.on_back = on_back
        self.dashboard = dashboard
        self.status: Optional[ProjectStatus] = None
        self.body = ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, spacing=12)
        self.header_status = ft.Column(spacing=2, tight=True)

    # --------------------------------------------------------
    # Property: project
    # Purpose: Current ProjectConfig or None if removed.
    # --------------------------------------------------------
    @property
    def project(self) -> Optional[ProjectConfig]:
        return self.store.getProject(self.project_id)

    # --------------------------------------------------------
    # Method: build
    # Purpose: Construct detail layout and load status.
    # --------------------------------------------------------
    def build(self) -> ft.Control:
        project = self.project
        title = project.name if project else "Project"

        toolbar = ft.Row(
            [
                ft.IconButton(icon=ft.Icons.ARROW_BACK, tooltip="Back", on_click=lambda _e: self.on_back()),
                ft.Text(title, size=22, weight=ft.FontWeight.BOLD, expand=True),
                ft.IconButton(
                    icon=ft.Icons.FOLDER_OPEN,
                    tooltip="Open folder in Explorer",
                    on_click=lambda _e: self._openProjectFolder(),
                ),
                ft.IconButton(
                    icon=ft.Icons.PUBLIC,
                    tooltip="Open Git repo in browser",
                    on_click=lambda _e: self._openProjectRemote(),
                ),
                ft.IconButton(
                    icon=ft.Icons.SETTINGS,
                    tooltip="Project settings",
                    on_click=lambda _e: self._editSettings(),
                ),
                ft.IconButton(
                    icon=ft.Icons.DELETE_OUTLINE,
                    tooltip="Remove from Syncher",
                    icon_color=ft.Colors.RED_400,
                    on_click=lambda _e: self._removeProject(),
                ),
            ]
        )

        actions = ft.Row(
            [
                ft.FilledButton("Refresh", icon=ft.Icons.REFRESH, on_click=lambda _e: self.reload()),
                ft.OutlinedButton("Commit", icon=ft.Icons.COMMIT, on_click=lambda _e: self.doCommit()),
                ft.OutlinedButton("Pull", icon=ft.Icons.DOWNLOAD, on_click=lambda _e: self.doPull()),
                ft.OutlinedButton("Push", icon=ft.Icons.UPLOAD, on_click=lambda _e: self.doPush()),
            ],
            wrap=True,
            spacing=8,
        )

        self.reload(silent=True)
        return ft.Container(
            expand=True,
            padding=20,
            content=ft.Column(
                [
                    toolbar,
                    self.header_status,
                    actions,
                    ft.Divider(),
                    self.body,
                ],
                expand=True,
            ),
        )

    # --------------------------------------------------------
    # Method: reload
    # Purpose: Refresh this project's Git status and file list.
    # --------------------------------------------------------
    def reload(self, silent: bool = False) -> None:
        project = self.project
        if project is None:
            Dialogs.showSnack(self.page, "Project no longer exists.", error=True)
            self.on_back()
            return
        self.status = self.git.getStatus(project, fetch=True)
        self.dashboard.statuses[project.id] = self.status
        self._renderBody()
        if not silent:
            Dialogs.showSnack(self.page, "Status updated")
        self.page.update()

    # --------------------------------------------------------
    # Method: _renderBody
    # Purpose: Fill body with summary + changed files.
    # --------------------------------------------------------
    def _renderBody(self) -> None:
        self.body.controls.clear()
        project = self.project
        status = self.status
        if project is None or status is None:
            self.body.controls.append(ft.Text("No data"))
            return

        action = status.suggested_action
        label, color = _ACTION_META.get(action, ("Check", ft.Colors.GREY_400))
        self.header_status.controls = [
            ft.Text(line, size=13, color=ft.Colors.ON_SURFACE_VARIANT)
            for line in status.plainStatusLines()
        ]

        suggestion_row = ft.Container(
            padding=12,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            border_radius=8,
            content=ft.Row(
                [
                    ft.Column(
                        [
                            ft.Text("Suggested next step", size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                            ft.Text(label, size=18, weight=ft.FontWeight.BOLD, color=color),
                            ft.Text(self._suggestionHint(status), size=13),
                        ],
                        expand=True,
                        spacing=2,
                    ),
                    ft.FilledButton(
                        label,
                        on_click=lambda _e: self._runSuggested(),
                    ),
                ]
            ),
        )
        self.body.controls.append(suggestion_row)

        self.body.controls.append(
            ft.Column(
                [
                    ft.Text(line, size=12, color=ft.Colors.ON_SURFACE_VARIANT)
                    for line in status.versionSummaryLines()
                ],
                spacing=0,
                tight=True,
            )
        )

        self.body.controls.append(
            ft.Text("Changed files", size=16, weight=ft.FontWeight.W_600)
        )

        if not status.changes:
            self.body.controls.append(
                ft.Text("Working tree clean.", color=ft.Colors.ON_SURFACE_VARIANT)
            )
            return

        for change in status.changes:
            self.body.controls.append(self._fileRow(change.path, change.kind))

        self.body.controls.append(ft.Container(height=8))
        self.body.controls.append(
            ft.OutlinedButton(
                "Discard all local changes",
                icon=ft.Icons.DELETE_SWEEP,
                style=ft.ButtonStyle(color=ft.Colors.RED_400),
                on_click=lambda _e: self._discardAll(),
            )
        )

    # --------------------------------------------------------
    # Method: _suggestionHint
    # Purpose: One-line explanation under the suggested action.
    # --------------------------------------------------------
    @staticmethod
    def _suggestionHint(status: ProjectStatus) -> str:
        if status.suggested_action == SuggestedAction.COMMIT:
            count = len(status.changes)
            noun = "file" if count == 1 else "files"
            return f"{count} {noun} changed on this computer — save them with Commit."
        if status.suggested_action == SuggestedAction.PUSH:
            noun = "commit" if status.ahead == 1 else "commits"
            return (
                f"This computer has {status.ahead} {noun} that Git does not have yet — "
                "Push sends them."
            )
        if status.suggested_action == SuggestedAction.PULL:
            noun = "commit" if status.behind == 1 else "commits"
            return (
                f"Git has {status.behind} {noun} this computer does not have yet — "
                "Pull downloads them."
            )
        if status.suggested_action == SuggestedAction.RESOLVE:
            if status.ahead and status.behind:
                return (
                    "This computer and Git both have new commits — they differ. "
                    "Best next step: Make this computer match Git (throws away local commits)."
                )
            return "Conflicts or mixed state — make this computer match Git, or pick a file choice."
        if status.suggested_action == SuggestedAction.SYNCED:
            return "This computer and Git are in sync."
        if status.suggested_action == SuggestedAction.NOT_A_REPO:
            return "Initialize Git from project settings."
        if status.suggested_action == SuggestedAction.MISSING_PATH:
            return "The folder path no longer exists."
        return "Open settings or refresh after fixing the issue."

    # --------------------------------------------------------
    # Method: _fileRow
    # Purpose: Row with compare / discard / conflict actions.
    # --------------------------------------------------------
    def _fileRow(self, file_path: str, kind: FileChangeKind) -> ft.Control:
        is_conflict = kind == FileChangeKind.CONFLICT
        buttons: list[ft.Control] = [
            ft.TextButton(
                "Compare",
                icon=ft.Icons.COMPARE,
                on_click=lambda _e, p=file_path: self._compareFile(p),
            ),
            ft.TextButton(
                "Discard",
                icon=ft.Icons.UNDO,
                style=ft.ButtonStyle(color=ft.Colors.RED_400),
                on_click=lambda _e, p=file_path: self._discardFile(p),
            ),
        ]
        if is_conflict:
            buttons.extend(
                [
                    ft.TextButton(
                        "Keep local",
                        on_click=lambda _e, p=file_path: self._keepLocal(p),
                    ),
                    ft.TextButton(
                        "Take remote",
                        on_click=lambda _e, p=file_path: self._takeRemote(p),
                    ),
                ]
            )

        return ft.Container(
            padding=ft.Padding.symmetric(vertical=4, horizontal=8),
            border=ft.Border.only(bottom=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT)),
            content=ft.Row(
                [
                    ft.Column(
                        [
                            ft.Text(file_path, size=13, expand=True),
                            ft.Text(kind.value, size=11, color=ft.Colors.ON_SURFACE_VARIANT),
                        ],
                        expand=True,
                        spacing=0,
                    ),
                    ft.Row(buttons, tight=True),
                ]
            ),
        )

    # --------------------------------------------------------
    # Method: _runSuggested
    # Purpose: Execute the card's suggested primary action.
    # --------------------------------------------------------
    def _runSuggested(self) -> None:
        if self.status is None:
            return
        mapping = {
            SuggestedAction.COMMIT: self.doCommit,
            SuggestedAction.PUSH: self.doPush,
            SuggestedAction.PULL: self.doPull,
            SuggestedAction.RESOLVE: self._openResolveHelp,
            SuggestedAction.NOT_A_REPO: self._editSettings,
        }
        handler = mapping.get(self.status.suggested_action)
        if handler:
            handler()
        else:
            Dialogs.showSnack(self.page, "Nothing to do — already synced.")

    # --------------------------------------------------------
    # Method: _openResolveHelp
    # Purpose: Present resolve choices when branches diverge.
    # --------------------------------------------------------
    def _openResolveHelp(self) -> None:
        outcome = ActionOutcome(
            title="Resolve differences",
            message=(
                "This computer and Git differ. "
                "Next: make this computer match Git (recommended if you do not care about local commits), "
                "or overwrite Git online."
            ),
            choices=[
                ActionChoice(
                    ActionId.MATCH_REMOTE,
                    "Make this computer match Git",
                    description=(
                        "Throw away local commits and files. "
                        "Git online is not changed."
                    ),
                    destructive=True,
                    requires_confirm=True,
                ),
                ActionChoice(ActionId.VIEW_DIFFS, "View local changes"),
                ActionChoice(ActionId.PULL_FIRST, "Try pull first"),
                ActionChoice(
                    ActionId.OVERWRITE_REMOTE,
                    "Overwrite remote",
                    destructive=True,
                    requires_confirm=True,
                ),
                ActionChoice(ActionId.CANCEL, "Cancel"),
            ],
        )
        self._handleOutcome(outcome, retry=self._openResolveHelp)

    # --------------------------------------------------------
    # Git actions
    # --------------------------------------------------------
    def doCommit(self) -> None:
        project = self.project
        if not project:
            return
        last_tag = self.status.last_tag if self.status else ""
        if not last_tag:
            last_tag = self.git.latestTag(project.path)
        suggested = ChangelogParser.suggestCommitMessage(project.path, last_tag=last_tag) or ""
        Dialogs.showCommit(self.page, suggested, on_commit=self._commitWithMessage)

    def _commitWithMessage(self, message: str) -> None:
        project = self.project
        if not project:
            return
        outcome = self.git.commit(project, message)
        self._handleOutcome(outcome, retry=lambda: self._commitWithMessage(message))
        if outcome.success:
            self.reload(silent=True)

    def doPull(self) -> None:
        project = self.project
        if not project:
            return
        outcome = self.git.pull(project)
        self._handleOutcome(outcome, retry=self.doPull)
        if outcome.success:
            try:
                self.store.save()
            except Exception:
                pass
            self.reload(silent=True)

    # --------------------------------------------------------
    # Method: _pullCurrentBranch
    # Purpose: Pull the branch this computer is on (not a stale default).
    # --------------------------------------------------------
    def _pullCurrentBranch(self) -> None:
        project = self.project
        if not project:
            return
        current = self.git.detectBranch(project.path)
        if current:
            project.default_branch = current
            try:
                self.store.save()
            except Exception:
                pass
        outcome = self.git.pull(project, branch=current or None)
        self._handleOutcome(outcome, retry=self._pullCurrentBranch)
        if outcome.success:
            self.reload(silent=True)

    def doPush(self, force: bool = False, set_upstream: bool = False) -> None:
        project = self.project
        if not project:
            return

        def run_push(create_tag_version: Optional[str] = None) -> None:
            outcome = self.git.push(project, force=force, set_upstream=set_upstream)
            if not outcome.success:
                self._handleOutcome(
                    outcome,
                    retry=lambda: self.doPush(force=force, set_upstream=set_upstream),
                )
                return

            if create_tag_version:
                tag_outcome = self.git.createTag(project.path, create_tag_version)
                if not tag_outcome.success:
                    Dialogs.showSnack(self.page, "Push succeeded, but tagging failed.", error=True)
                    self._handleOutcome(tag_outcome)
                    self.reload(silent=True)
                    return
                push_tag = self.git.pushTag(project, create_tag_version)
                if push_tag.success:
                    Dialogs.showSnack(
                        self.page,
                        f"Pushed and tagged {create_tag_version}",
                    )
                else:
                    Dialogs.showSnack(
                        self.page,
                        f"Pushed; tag created locally but not on Git yet ({push_tag.message})",
                        error=True,
                    )
                    self._handleOutcome(push_tag)
            else:
                self._handleOutcome(outcome)

            self.reload(silent=True)

        if force:
            Dialogs.showConfirm(
                self.page,
                title="Overwrite remote?",
                message=(
                    "This force-pushes your local branch and can erase commits on the remote. "
                    "Only continue if you are sure."
                ),
                confirm_label="Overwrite remote",
                on_confirm=lambda: run_push(None),
            )
            return

        # No Changelog version → suggest next version from Git tags.
        if not ChangelogParser.hasProperChangelog(project.path):
            last_tag = self.status.last_tag if self.status else ""
            if not last_tag:
                last_tag = self.git.latestTag(project.path)
            next_version = ChangelogParser.suggestNextVersionFromTag(last_tag)
            Dialogs.showPushVersionSuggest(
                self.page,
                suggested_version=next_version,
                last_tag=last_tag,
                on_push_only=lambda: run_push(None),
                on_push_and_tag=lambda ver: run_push(ver),
            )
            return

        run_push(None)

    # --------------------------------------------------------
    # Method: _handleOutcome
    # Purpose: Show success snack or choice dialog for failures.
    # --------------------------------------------------------
    def _handleOutcome(
        self,
        outcome: ActionOutcome,
        retry: Optional[Callable[[], None]] = None,
    ) -> None:
        if outcome.success:
            Dialogs.showSnack(self.page, outcome.title + (f" — {outcome.message}" if outcome.message else ""))
            return

        def on_choice(action_id: ActionId) -> None:
            self._dispatchAction(action_id, retry=retry)

        Dialogs.showChoice(self.page, outcome, on_choice)

    # --------------------------------------------------------
    # Method: _dispatchAction
    # Purpose: Execute a guided ActionId from a choice dialog.
    # --------------------------------------------------------
    def _dispatchAction(
        self,
        action_id: ActionId,
        retry: Optional[Callable[[], None]] = None,
    ) -> None:
        project = self.project
        if action_id == ActionId.CANCEL:
            return
        if action_id == ActionId.RETRY and retry:
            retry()
            return
        if action_id == ActionId.REENTER_PAT or action_id == ActionId.OPEN_SETTINGS:
            self._editSettings()
            return
        if action_id == ActionId.SET_REMOTE:
            self._editSettings()
            return
        if action_id == ActionId.VIEW_DIFFS:
            self.reload(silent=True)
            Dialogs.showSnack(self.page, "Review changed files below, then choose an action.")
            return
        if action_id == ActionId.PULL_FIRST:
            self.doPull()
            return
        if action_id == ActionId.PULL_CURRENT_BRANCH:
            self._pullCurrentBranch()
            return
        if action_id == ActionId.OVERWRITE_REMOTE:
            self.doPush(force=True, set_upstream=False)
            return
        if action_id == ActionId.FIRST_PUSH:
            self.doPush(force=False, set_upstream=True)
            return
        if not project:
            return
        if action_id == ActionId.STASH_THEN_PULL:
            outcome = self.git.stashThenPull(project)
            self._handleOutcome(outcome, retry=lambda: self._dispatchAction(action_id))
            if outcome.success:
                self.reload(silent=True)
            return
        if action_id == ActionId.DISCARD_THEN_PULL:
            Dialogs.showConfirm(
                self.page,
                title="Discard local changes?",
                message="All uncommitted local changes will be permanently deleted, then pull will run.",
                confirm_label="Discard and pull",
                on_confirm=lambda: self._runDiscardThenPull(),
            )
            return
        if action_id == ActionId.MATCH_REMOTE:
            Dialogs.showConfirm(
                self.page,
                title="Make this computer match Git?",
                message=(
                    "This deletes local commits and uncommitted files on this computer. "
                    "Git online is not changed. "
                    "After this, this folder will be identical to the remote branch."
                ),
                confirm_label="Match Git",
                on_confirm=lambda: self._runMatchRemote(),
            )
            return
        if action_id == ActionId.INIT_REPO:
            outcome = self.git.initRepo(project.path)
            self._handleOutcome(outcome)
            if outcome.success:
                self.reload(silent=True)
            return

    def _runDiscardThenPull(self) -> None:
        project = self.project
        if not project:
            return
        outcome = self.git.discardThenPull(project)
        self._handleOutcome(outcome)
        if outcome.success:
            self.reload(silent=True)

    # --------------------------------------------------------
    # Method: _runMatchRemote
    # Purpose: Hard-reset this computer to origin (Git unchanged).
    # --------------------------------------------------------
    def _runMatchRemote(self) -> None:
        project = self.project
        if not project:
            return
        outcome = self.git.resetToRemote(project)
        self._handleOutcome(outcome, retry=self._runMatchRemote)
        if outcome.success:
            try:
                self.store.save()
            except Exception:
                pass
            self.reload(silent=True)

    # --------------------------------------------------------
    # Per-file helpers
    # --------------------------------------------------------
    def _compareFile(self, file_path: str) -> None:
        project = self.project
        if not project:
            return
        diff_text = self.git.getDiff(project.path, file_path)
        Dialogs.showDiff(self.page, file_path, diff_text)

    def _discardFile(self, file_path: str) -> None:
        project = self.project
        if not project:
            return

        def run() -> None:
            outcome = self.git.discardFile(project.path, file_path)
            self._handleOutcome(outcome)
            if outcome.success:
                self.reload(silent=True)

        Dialogs.showConfirm(
            self.page,
            title="Discard file changes?",
            message=f"Discard local changes to:\n{file_path}",
            confirm_label="Discard",
            on_confirm=run,
        )

    def _discardAll(self) -> None:
        project = self.project
        if not project:
            return

        def run() -> None:
            outcome = self.git.discardAll(project.path)
            self._handleOutcome(outcome)
            if outcome.success:
                self.reload(silent=True)

        Dialogs.showConfirm(
            self.page,
            title="Discard ALL local changes?",
            message="This resets the working tree and removes untracked files. Cannot be undone.",
            confirm_label="Discard all",
            on_confirm=run,
        )

    def _keepLocal(self, file_path: str) -> None:
        project = self.project
        if not project:
            return
        outcome = self.git.resolveFileKeepLocal(project.path, file_path)
        self._handleOutcome(outcome)
        if outcome.success:
            self.reload(silent=True)

    def _takeRemote(self, file_path: str) -> None:
        project = self.project
        if not project:
            return
        outcome = self.git.resolveFileTakeRemote(project.path, file_path)
        self._handleOutcome(outcome)
        if outcome.success:
            self.reload(silent=True)

    # --------------------------------------------------------
    # Settings / remove
    # --------------------------------------------------------
    def _openProjectFolder(self) -> None:
        project = self.project
        if not project:
            return
        if not openFolderInExplorer(project.path):
            Dialogs.showSnack(
                self.page,
                "Could not open folder. Check that the path still exists.",
                error=True,
            )

    def _openProjectRemote(self) -> None:
        project = self.project
        if not project:
            return
        remote = ""
        if self.status and self.status.remote_url:
            remote = self.status.remote_url
        elif project.remote_url:
            remote = project.remote_url
        branch = ""
        if self.status and self.status.branch:
            branch = self.status.branch
        elif project.default_branch:
            branch = project.default_branch
        if not openRemoteInBrowser(remote, branch=branch):
            Dialogs.showSnack(
                self.page,
                "No remote URL set — open project settings and add the repo URL.",
                error=True,
            )

    def _editSettings(self) -> None:
        project = self.project
        if not project:
            return
        self.dashboard.openAddProjectDialog(existing=project)

    def _removeProject(self) -> None:
        project = self.project
        if not project:
            return

        def confirm() -> None:
            self.store.removeProject(project.id)
            self.dashboard.statuses.pop(project.id, None)
            Dialogs.showSnack(self.page, "Project removed from Syncher")
            self.on_back()

        Dialogs.showConfirm(
            self.page,
            title="Remove project?",
            message=(
                f"Remove “{project.name}” from Git Syncher?\n"
                "This does not delete files on disk — only the Syncher entry and stored PAT."
            ),
            confirm_label="Remove",
            on_confirm=confirm,
        )
