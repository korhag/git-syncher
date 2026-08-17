from __future__ import annotations

from typing import Callable

import flet as ft

from app.core.store import VaultDamagedError, VaultStore


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
        self.is_create = not store.vaultExists()

    # --------------------------------------------------------
    # Method: build
    # Purpose: Return the unlock / create UI controls.
    # --------------------------------------------------------
    def build(self) -> ft.Control:
        title = "Create master password" if self.is_create else "Unlock vault"
        subtitle = (
            "This password encrypts your PATs and project settings on this machine."
            if self.is_create
            else "Enter your master password to unlock saved projects."
        )

        password_field = ft.TextField(
            label="Master password",
            password=True,
            can_reveal_password=True,
            autofocus=True,
            width=360,
            on_submit=lambda _e: self._submit(
                password_field, confirm_field, error_text, restore_button
            ),
        )
        confirm_field = ft.TextField(
            label="Confirm password",
            password=True,
            can_reveal_password=True,
            width=360,
            visible=self.is_create,
            on_submit=lambda _e: self._submit(
                password_field, confirm_field, error_text, restore_button
            ),
        )
        error_text = ft.Text("", color=ft.Colors.RED_400, size=13, width=360)
        restore_button = ft.OutlinedButton(
            "Restore backup",
            icon=ft.Icons.RESTORE,
            visible=False,
            width=360,
            on_click=lambda _e: self._restoreBackup(
                password_field, error_text, restore_button
            ),
        )

        git_banner: ft.Control
        if self.git_available:
            git_banner = ft.Text(
                self.git_version or "Git is available",
                size=12,
                color=ft.Colors.ON_SURFACE_VARIANT,
            )
        else:
            git_banner = ft.Container(
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
            )

        return ft.Container(
            expand=True,
            alignment=ft.Alignment.CENTER,
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.SYNC, size=56, color=ft.Colors.PRIMARY),
                    ft.Text("Git Syncher", size=28, weight=ft.FontWeight.BOLD),
                    ft.Text(title, size=18),
                    ft.Text(subtitle, size=13, color=ft.Colors.ON_SURFACE_VARIANT, width=360),
                    ft.Container(height=8),
                    password_field,
                    confirm_field,
                    error_text,
                    ft.FilledButton(
                        "Create vault" if self.is_create else "Unlock",
                        icon=ft.Icons.LOCK_OPEN,
                        on_click=lambda _e: self._submit(
                            password_field, confirm_field, error_text, restore_button
                        ),
                        width=360,
                    ),
                    restore_button,
                    ft.Container(height=16),
                    git_banner,
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                tight=True,
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
    ) -> None:
        password = (password_field.value or "").strip()
        if len(password) < 6:
            error_text.value = "Password must be at least 6 characters."
            restore_button.visible = False
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
                error_text.value = str(exc)
                restore_button.visible = self.store.backupExists()
                self.page.update()
                return
            except Exception as exc:  # noqa: BLE001
                error_text.value = f"Could not unlock: {exc}"
                restore_button.visible = self.store.backupExists()
                self.page.update()
                return
            if not ok:
                error_text.value = "Wrong master password."
                restore_button.visible = False
                self.page.update()
                return

        error_text.value = ""
        restore_button.visible = False
        self.on_unlocked()

    # --------------------------------------------------------
    # Method: _restoreBackup
    # Purpose: Copy vault.enc.bak over vault.enc, then unlock.
    # --------------------------------------------------------
    def _restoreBackup(
        self,
        password_field: ft.TextField,
        error_text: ft.Text,
        restore_button: ft.OutlinedButton,
    ) -> None:
        if not self.store.restoreBackup():
            error_text.value = (
                "No usable backup found (data/vault.enc.bak). "
                "Delete the empty vault.enc only if you are ready to create a new vault."
            )
            restore_button.visible = False
            self.page.update()
            return

        password = (password_field.value or "").strip()
        if len(password) < 6:
            error_text.value = (
                "Backup restored. Enter your master password (at least 6 characters) and Unlock."
            )
            restore_button.visible = False
            self.page.update()
            return

        try:
            ok = self.store.unlockVault(password)
        except VaultDamagedError as exc:
            error_text.value = str(exc)
            restore_button.visible = self.store.backupExists()
            self.page.update()
            return
        except Exception as exc:  # noqa: BLE001
            error_text.value = f"Could not unlock after restore: {exc}"
            self.page.update()
            return

        if not ok:
            error_text.value = "Backup restored, but that master password is wrong."
            restore_button.visible = False
            self.page.update()
            return

        error_text.value = ""
        restore_button.visible = False
        self.on_unlocked()
