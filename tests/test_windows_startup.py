from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app import main as entry
from app.core.shortcuts import APP_USER_MODEL_ID, ShortcutResult


def testWindowsStartupBrandsWindowBeforeShowing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("FLET_APP_USER_MODEL_ID", raising=False)
    page = MagicMock()
    page.window.visible = False
    activation = MagicMock()

    def initialize(shown_page):
        assert shown_page.window.icon == str(tmp_path / "assets" / "icon.ico")
        assert shown_page.window.visible is False

    def run(target, **kwargs):
        assert entry.os.environ["FLET_APP_USER_MODEL_ID"] == APP_USER_MODEL_ID
        assert kwargs["view"] == entry.ft.AppView.FLET_APP_HIDDEN
        target(page)

    with (
        patch.object(entry.sys, "platform", "win32"),
        patch.object(entry, "projectRoot", return_value=tmp_path),
        patch.object(entry, "ensureWindowsShortcut", return_value=ShortcutResult(True, "")) as repair,
        patch.object(entry.ft, "run", side_effect=run),
    ):
        entry.runApp(initialize, activation)

    repair.assert_called_once_with(tmp_path)
    assert page.window.visible is True
    page.update.assert_called_once()
    activation.attach.assert_called_once_with(page)


def testWindowsStartupRevealsFletError(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("FLET_APP_USER_MODEL_ID", raising=False)
    page = MagicMock()
    page.window.visible = False

    def initialize(_page):
        raise RuntimeError("startup failed")

    with (
        patch.object(entry.sys, "platform", "win32"),
        patch.object(entry, "projectRoot", return_value=tmp_path),
        patch.object(entry, "ensureWindowsShortcut", return_value=ShortcutResult(True, "")),
        patch.object(entry.ft, "run", side_effect=lambda target, **_kwargs: target(page)),
        pytest.raises(RuntimeError, match="startup failed"),
    ):
        entry.runApp(initialize)

    assert page.window.visible is True


def testWindowsSecondLaunchSignalsExistingInstance() -> None:
    lock_path = MagicMock()
    with (
        patch.object(entry.sys, "platform", "win32"),
        patch.object(entry.sys, "argv", ["app.main"]),
        patch.object(entry, "getAppLock", return_value=MagicMock(lock_path=lock_path)),
        patch.object(entry, "acquireAppLock", return_value=False),
        patch.object(entry, "requestActivation") as activate,
        patch.object(entry, "runApp") as run,
    ):
        entry.launchApp()

    activate.assert_called_once_with(lock_path)
    run.assert_not_called()
