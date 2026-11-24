from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import Mock

import flet as ft
import pytest

from app.core.actions import ActionOutcome
from app.models.project import ProjectConfig
from app.ui.dashboard import DashboardView


def visible_controls(control: ft.Control) -> Iterator[ft.Control]:
    """Walk displayed dialog content, including its action buttons."""
    if not control.visible:
        return
    yield control
    content = getattr(control, "content", None)
    if isinstance(content, ft.Control):
        yield from visible_controls(content)
    for children in ("controls", "actions"):
        for child in getattr(control, children, []):
            yield from visible_controls(child)


def folder_field(dialog: ft.AlertDialog) -> ft.TextField:
    return next(
        c for c in visible_controls(dialog)
        if isinstance(c, ft.TextField) and c.label == "Folder path"
    )


def assert_pinned(dialog: ft.AlertDialog, control: ft.Control) -> None:
    """The control must remain visible when the project fields are scrolled."""
    assert not dialog.scrollable
    assert any(c is control for c in visible_controls(dialog))
    folder = folder_field(dialog)
    (fields,) = (
        c for c in visible_controls(dialog)
        if isinstance(c, ft.Column) and c.scroll
        and any(child is folder for child in visible_controls(c))
    )
    assert all(c is not control for c in visible_controls(fields))


@pytest.fixture
def dashboard() -> DashboardView:
    page = Mock(width=960, height=860)
    page.window.width, page.window.height = 960, 860
    store = Mock(accounts=[])
    store.findDuplicate.return_value = None
    git = Mock()
    git.isRepo.return_value = False
    git.resolveBranchForSave.return_value = "main"
    busy = Mock(busy=False)

    def run_work(_message, work, on_done):
        on_done(work(), None)
        return True

    busy.runOrSnack.side_effect = run_work
    return DashboardView(page, store, git, busy, Mock(), Mock())


def open_dialog(
    dashboard: DashboardView, existing: ProjectConfig | None = None
) -> ft.AlertDialog:
    dashboard.openAddProjectDialog(existing)
    return dashboard.page.show_dialog.call_args.args[0]


@pytest.mark.parametrize("size", [(960, 860), (800, 480)])
def test_add_shows_initialization_and_missing_path_feedback(dashboard, size):
    dashboard.page.width, dashboard.page.height = size
    dashboard.page.window.width, dashboard.page.window.height = size
    dialog = open_dialog(dashboard)
    init = next(c for c in visible_controls(dialog) if isinstance(c, ft.Checkbox))
    assert not init.value
    assert_pinned(dialog, init)

    save = next(c for c in visible_controls(dialog) if isinstance(c, ft.FilledButton))
    save.on_click(None)
    message = next(
        c for c in visible_controls(dialog)
        if isinstance(c, ft.Text) and "folder path" in (c.value or "").lower()
    )
    assert_pinned(dialog, message)
    dashboard.page.pop_dialog.assert_not_called()
    dashboard.busy.runOrSnack.assert_not_called()


def test_unchecked_non_repo_explains_save_and_allows_retry(dashboard, tmp_path):
    dialog = open_dialog(dashboard)
    folder = folder_field(dialog)
    folder.value = str(tmp_path)
    folder.on_blur(None)
    init = next(c for c in visible_controls(dialog) if isinstance(c, ft.Checkbox))
    save = next(c for c in visible_controls(dialog) if isinstance(c, ft.FilledButton))
    save.on_click(None)
    message = next(
        c for c in visible_controls(dialog)
        if isinstance(c, ft.Text) and "initialize git" in (c.value or "").lower()
    )
    assert_pinned(dialog, message)
    assert not save.disabled
    dashboard.git.initRepo.assert_not_called()
    dashboard.store.addProject.assert_not_called()
    dashboard.page.pop_dialog.assert_not_called()

    dashboard.git.initRepo.return_value = ActionOutcome("Initialized", "", success=True)
    dashboard.git.checkoutSavedBranch.return_value = ActionOutcome("Ready", "", success=True)
    dashboard.refreshAll = Mock()
    init.value = True
    save.on_click(None)
    dashboard.git.initRepo.assert_called_once_with(str(tmp_path), "main")
    dashboard.store.addProject.assert_called_once()
    dashboard.page.pop_dialog.assert_called_once()


def test_initialization_visibility_follows_mode_and_selected_folder(dashboard, tmp_path):
    dialog = open_dialog(dashboard)
    init = next(c for c in visible_controls(dialog) if isinstance(c, ft.Checkbox))
    tabs = next(c for c in visible_controls(dialog) if isinstance(c, ft.Tabs))

    def switch_tab(index):
        tabs.selected_index = index
        tabs.on_change(SimpleNamespace(control=tabs))

    switch_tab(1)
    assert all(c is not init for c in visible_controls(dialog))
    switch_tab(0)
    assert_pinned(dialog, init)

    dashboard.git.isRepo.return_value = True
    dashboard.git.detectRemoteUrl.return_value = ""
    dashboard.git.suggestBranchNames.return_value = ["main"]
    dashboard.git.detectLocalUser.return_value = ("", "")
    folder = folder_field(dialog)
    folder.value = str(tmp_path)
    folder.on_blur(None)
    assert all(c is not init for c in visible_controls(dialog))
    switch_tab(1)
    switch_tab(0)
    assert all(c is not init for c in visible_controls(dialog))

    project = ProjectConfig(
        id="p", name="Project", path=str(tmp_path), default_branch="main"
    )
    edit = open_dialog(dashboard, existing=project)
    assert all(not isinstance(c, ft.Checkbox) for c in visible_controls(edit))
