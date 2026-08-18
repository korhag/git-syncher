from __future__ import annotations

from typing import Callable

import flet as ft

from app import __version__
from app.core.store import VAULT_DAMAGED_MESSAGE, VaultDamagedError, VaultStore
from app.ui.dialogs import Dialogs


# ------------------------------------------------------------
# Class: UnlockView
# Purpose: First-run create-password or unlock existing vault.
# ------------------------------------------------------------
class UnlockView:
    # --------------------------------------------------------
    # Method: __init__
    # Purpose: Bind store and callback when vault is ready.
    # --------------------------------------------------------
    def __init__(
        self,
        page: ft.Page,
        store: VaultStore,
        on_unlocked: Callable[[], None],
        git_available: bool,
        git_version: str,
    ) -> None:
        self.page = page
        self.store = store
        self.on_unlocked = on_unlocked
        self.git_available = git_available
        self.git_version = git_version
        # Empty/damaged vault.enc still "exists" — treat as create only when missing.
        self.is_create = not store.vaultExists()

    # --------------------------------------------------------
    # Method: build
    # Purpose: Return the unlock / create UI controls.
    # --------------------------------------------------------
    def build(self) -> ft.Control:
        title_text = ft.Text(
            "Create master password" if self.is_create else "Unlock vault",
            size=18,
        )
        subtitle_text = ft.Text(
            (
                "This password encrypts your PATs and project settings on this machine."
                if self.is_create
                else "Enter your master password to unlock saved projects."
            ),
            size=13,
            color=ft.Colors.ON_SURFACE_VARIANT,
            width=360,
        )

        password_field = ft.TextField(
            label="Master password",
            password=True,
            can_reveal_password=True,
            autofocus=True,
            width=360,
        )
        confirm_field = ft.TextField(
            label="Confirm password",
            password=True,
            can_reveal_password=True,
            width=360,
            visible=self.is_create,
        )
        error_text = ft.Text("", color=ft.Colors.RED_400, size=13, width=360)
        primary_button = ft.FilledButton(
            "Create vault" if self.is_create else "Unlock",
            icon=ft.Icons.LOCK_OPEN,
            width=360,
        )
        restore_button = ft.OutlinedButton(
            "Restore backup",
            icon=ft.Icons.RESTORE,
            visible=False,
            width=360,
        )
        start_over_button = ft.OutlinedButton(
            "Start over",
            icon=ft.Icons.DELETE_OUTLINE,
            visible=False,
            width=360,
            style=ft.ButtonStyle(color=ft.Colors.RED_400),
        )

        def refresh_recovery() -> None:
            damaged = (not self.is_create) and self.store.isVaultDamaged()
            restore_button.visible = damaged and self.store.backupExists()
            start_over_button.visible = damaged
            if damaged and not error_text.value:
                error_text.value = VAULT_DAMAGED_MESSAGE

        def switch_to_create() -> None:
            self.is_create = True
            title_text.value = "Create master password"
            subtitle_text.value = (
                "This password encrypts your PATs and project settings on this machine."
            )
            confirm_field.visible = True
            primary_button.text = "Create vault"
            restore_button.visible = False
            start_over_button.visible = False
            error_text.value = (
                "Broken vault removed. Choose a master password and create a new vault."
            )
            self.page.update()

        def show_recovery_after_damage(message: str) -> None:
            error_text.value = message
            restore_button.visible = self.store.backupExists()
            start_over_button.visible = True
            self.page.update()

        password_field.on_submit = lambda _e: self._submit(
            password_field,
            confirm_field,
            error_text,
            restore_button,
            start_over_button,
            primary_button,
            title_text,
            subtitle_text,
        )
        confirm_field.on_submit = password_field.on_submit
        primary_button.on_click = password_field.on_submit
        restore_button.on_click = lambda _e: self._restoreBackup(
            password_field,
            error_text,
            restore_button,
            start_over_button,
        )
        start_over_button.on_click = lambda _e: self._confirmStartOver(
            error_text,
            restore_button,
            start_over_button,
            confirm_field,
            primary_button,
            title_text,
            subtitle_text,
        )

        refresh_recovery()

        form_controls: list[ft.Control] = [
            ft.Icon(ft.Icons.SYNC, size=56, color=ft.Colors.PRIMARY),
            ft.Text("Git Syncher", size=28, weight=ft.FontWeight.BOLD),
            title_text,
            subtitle_text,
            ft.Container(height=8),
            password_field,
            confirm_field,
            error_text,
            primary_button,
            restore_button,
            start_over_button,
        ]
        # Keep git-missing warning; do not use git version as the app footer.
        if not self.git_available:
            form_controls.extend(
                [
                    ft.Container(height=16),
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Icon(ft.Icons.WARNING_AMBER, color=ft.Colors.AMBER),
                                ft.Text(
                                    "Git was not found. Install Git and restart the app.",
                                    color=ft.Colors.AMBER,
                                    expand=True,
                                ),
                            ]
                        ),
                        bgcolor=ft.Colors.AMBER_900,
                        padding=12,
                        border_radius=8,
                        width=400,
                    ),
                ]
            )

        # Keep switch_to_create / show_recovery for handlers via closure attrs.
        self._switch_to_create = switch_to_create
        self._show_recovery_after_damage = show_recovery_after_damage

        form = ft.Container(
            expand=True,
            alignment=ft.Alignment.CENTER,
            content=ft.Column(
                form_controls,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                tight=True,
            ),
        )
        footer = ft.Row(
            [
                ft.Container(expand=True),
                ft.Text(
                    f"v{__version__}",
                    size=11,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            ],
            alignment=ft.MainAxisAlignment.END,
        )
        return ft.Container(
            expand=True,
            padding=20,
            content=ft.Column(
                [form, footer],
                expand=True,
            ),
        )

    # --------------------------------------------------------
    # Method: _submit
    # Purpose: Validate password and create or unlock vault.
    # --------------------------------------------------------
    def _submit(
        self,
        password_field: ft.TextField,
        confirm_field: ft.TextField,
        error_text: ft.Text,
        restore_button: ft.OutlinedButton,
        start_over_button: ft.OutlinedButton,
        primary_button: ft.FilledButton,
        title_text: ft.Text,
        subtitle_text: ft.Text,
    ) -> None:
        password = (password_field.value or "").strip()
        if len(password) < 6:
            error_text.value = "Password must be at least 6 characters."
            self.page.update()
            return

        if self.is_create:
            confirm = (confirm_field.value or "").strip()
            if password != confirm:
                error_text.value = "Passwords do not match."
                self.page.update()
                return
            try:
                self.store.createVault(password)
            except Exception as exc:  # noqa: BLE001
                error_text.value = f"Could not create vault: {exc}"
                self.page.update()
                return
        else:
            try:
                ok = self.store.unlockVault(password)
            except VaultDamagedError as exc:
                self._show_recovery_after_damage(str(exc))
                return
            except Exception as exc:  # noqa: BLE001
                error_text.value = f"Could not unlock: {exc}"
                restore_button.visible = self.store.backupExists()
                start_over_button.visible = self.store.isVaultDamaged()
                self.page.update()
                return
            if not ok:
                error_text.value = "Wrong master password."
                restore_button.visible = False
                start_over_button.visible = False
                self.page.update()
                return

        error_text.value = ""
        restore_button.visible = False
        start_over_button.visible = False
        self._finishUnlock()

    # --------------------------------------------------------
    # Method: _finishUnlock
    # Purpose: Collapse duplicate vault entries, then open dashboard.
    # --------------------------------------------------------
    def _finishUnlock(self) -> None:
        removed = 0
        try:
            removed = self.store.collapseDuplicateProjects()
        except Exception:
            removed = 0
        self.on_unlocked()
        if removed:
            noun = "entry" if removed == 1 else "entries"
            Dialogs.showSnack(
                self.page,
                f"Removed {removed} duplicate project {noun}",
            )

    # --------------------------------------------------------
    # Method: _confirmStartOver
    # Purpose: Confirm, discard damaged vault, switch to create mode.
    # --------------------------------------------------------
    def _confirmStartOver(
        self,
        error_text: ft.Text,
        restore_button: ft.OutlinedButton,
        start_over_button: ft.OutlinedButton,
        confirm_field: ft.TextField,
        primary_button: ft.FilledButton,
        title_text: ft.Text,
        subtitle_text: ft.Text,
    ) -> None:
        def do_start_over() -> None:
            if not self.store.discardDamagedVault():
                error_text.value = (
                    "Could not remove the damaged vault file. "
                    "Close the app and delete data/vault.enc manually."
                )
                self.page.update()
                return
            self._switch_to_create()

        Dialogs.showConfirm(
            self.page,
            title="Start over?",
            message=(
                "This deletes the broken vault file on this computer. "
                "Saved projects and PATs in that file cannot be recovered. "
                "You will create a new vault and re-add projects. "
                "A vault.enc.bak file is kept if one exists."
            ),
            confirm_label="Start over",
            on_confirm=do_start_over,
        )

    # --------------------------------------------------------
    # Method: _restoreBackup
    # Purpose: Copy vault.enc.bak over vault.enc, then unlock.
    # --------------------------------------------------------
    def _restoreBackup(
        self,
        password_field: ft.TextField,
        error_text: ft.Text,
        restore_button: ft.OutlinedButton,
        start_over_button: ft.OutlinedButton,
    ) -> None:
        if not self.store.restoreBackup():
            error_text.value = (
                "No usable backup found (data/vault.enc.bak). "
                "Use Start over to create a new vault."
            )
            restore_button.visible = False
            start_over_button.visible = True
            self.page.update()
            return

        password = (password_field.value or "").strip()
        if len(password) < 6:
            error_text.value = (
                "Backup restored. Enter your master password (at least 6 characters) "
                "and Unlock."
            )
            restore_button.visible = False
            start_over_button.visible = False
            self.page.update()
            return

        try:
            ok = self.store.unlockVault(password)
        except VaultDamagedError as exc:
            self._show_recovery_after_damage(str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            error_text.value = f"Could not unlock after restore: {exc}"
            start_over_button.visible = self.store.isVaultDamaged()
            self.page.update()
            return

        if not ok:
            error_text.value = "Backup restored, but that master password is wrong."
            restore_button.visible = False
            start_over_button.visible = False
            self.page.update()
            return

        error_text.value = ""
        restore_button.visible = False
        start_over_button.visible = False
        self._finishUnlock()
