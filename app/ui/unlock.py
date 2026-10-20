from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from app import __version__
from app.core.store import VAULT_DAMAGED_MESSAGE, VaultDamagedError, VaultStore
from app.core.vault_registry import DEFAULT_VAULT_NAME, VaultEntry, VaultRegistry
from app.ui.dialogs import Dialogs
from app.ui.layout import contentWidth


# ------------------------------------------------------------
# Class: UnlockView
# Purpose: Pick a vault, unlock it, or create a new one.
# ------------------------------------------------------------
class UnlockView:
    # --------------------------------------------------------
    # Method: __init__
    # Purpose: Bind store, registry, and the unlock callback.
    # Input: create_new - Open straight into the new-vault form.
    # --------------------------------------------------------
    def __init__(
        self,
        page: ft.Page,
        store: VaultStore,
        on_unlocked: Callable[[], None],
        git_available: bool,
        git_version: str,
        registry: VaultRegistry,
        create_new: bool = False,
    ) -> None:
        self.page = page
        self.store = store
        self.on_unlocked = on_unlocked
        self.git_available = git_available
        self.git_version = git_version
        self.registry = registry
        # First run, or an explicit new-vault request, asks for a name.
        self.naming_new = create_new or not registry.list()
        # A missing file still needs a password, but it is not a new vault.
        self.is_create = self.naming_new or not store.vaultExists()
        self._host: Optional[ft.Container] = None
        self._notice = ""
        self._switch_to_create = lambda: None
        self._show_recovery_after_damage = lambda _message: None

    # --------------------------------------------------------
    # Method: build
    # Purpose: Return the unlock / create UI controls.
    # --------------------------------------------------------
    def build(self) -> ft.Control:
        self._host = ft.Container(expand=True, content=self._compose())
        return self._host

    # --------------------------------------------------------
    # Method: _rerender
    # Purpose: Rebuild the form after the selected vault changes.
    # --------------------------------------------------------
    def _rerender(self) -> None:
        if self._host is None:
            return
        self._host.content = self._compose()
        self.page.update()

    # --------------------------------------------------------
    # Method: _selectedEntry
    # Purpose: Registry entry matching the store's current file.
    # --------------------------------------------------------
    def _selectedEntry(self) -> Optional[VaultEntry]:
        try:
            current = self.store.vault_path.resolve()
        except OSError:
            current = self.store.vault_path
        for entry in self.registry.list():
            try:
                if self.registry.pathFor(entry) == current:
                    return entry
            except OSError:
                continue
        return self.registry.last()

    # --------------------------------------------------------
    # Method: _compose
    # Purpose: Build the current unlock or create form.
    # --------------------------------------------------------
    def _compose(self) -> ft.Control:
        form_width = contentWidth(self.page, preferred=360)
        if self.naming_new:
            title = "Create vault"
            subtitle = (
                "Name this vault and choose a password. "
                "It encrypts this vault's projects and PATs on this machine."
            )
        elif self.is_create:
            title = "Create master password"
            subtitle = (
                "This password encrypts your PATs and project settings on this machine."
            )
        else:
            title = "Unlock vault"
            subtitle = "Enter your master password to unlock saved projects."

        title_text = ft.Text(title, size=18)
        subtitle_text = ft.Text(
            subtitle,
            size=13,
            color=ft.Colors.ON_SURFACE_VARIANT,
            width=form_width,
        )

        entries = self.registry.list()
        selected = self._selectedEntry()
        vault_dropdown: Optional[ft.Dropdown] = None
        if entries and not self.naming_new:
            vault_dropdown = ft.Dropdown(
                label="Vault",
                value=selected.id if selected is not None else None,
                options=[
                    ft.DropdownOption(key=entry.id, text=entry.name)
                    for entry in entries
                ],
                width=form_width,
            )

            def on_vault_change(e: ft.ControlEvent) -> None:
                vault_id = e.control.value
                if not vault_id:
                    return
                current = self._selectedEntry()
                if current is not None and vault_id == current.id:
                    return
                entry = self.registry.get(str(vault_id))
                if entry is None:
                    return
                self.registry.setLast(entry.id)
                self.store.selectVault(self.registry.pathFor(entry))
                self.naming_new = False
                self.is_create = not self.store.vaultExists()
                self._notice = ""
                self._rerender()

            vault_dropdown.on_change = on_vault_change

        name_field = ft.TextField(
            label="Vault name",
            value=DEFAULT_VAULT_NAME if not entries else "",
            autofocus=self.naming_new,
            width=form_width,
            visible=self.naming_new,
        )
        password_field = ft.TextField(
            label="Master password",
            password=True,
            can_reveal_password=True,
            autofocus=not self.naming_new,
            width=form_width,
        )
        confirm_field = ft.TextField(
            label="Confirm password",
            password=True,
            can_reveal_password=True,
            width=form_width,
            visible=self.is_create,
        )
        error_text = ft.Text(
            self._notice,
            color=ft.Colors.RED_400,
            size=13,
            width=form_width,
        )
        self._notice = ""
        primary_button = ft.FilledButton(
            "Create vault" if self.is_create else "Unlock",
            icon=ft.Icons.LOCK_OPEN,
            width=form_width,
        )
        new_vault_button = ft.OutlinedButton(
            "New vault",
            icon=ft.Icons.ADD,
            visible=not self.naming_new,
            width=form_width,
        )
        cancel_button = ft.OutlinedButton(
            "Cancel",
            icon=ft.Icons.CLOSE,
            visible=self.naming_new and bool(entries),
            width=form_width,
        )
        restore_button = ft.OutlinedButton(
            "Restore backup",
            icon=ft.Icons.RESTORE,
            visible=False,
            width=form_width,
        )
        start_over_button = ft.OutlinedButton(
            "Start over",
            icon=ft.Icons.DELETE_OUTLINE,
            visible=False,
            width=form_width,
            style=ft.ButtonStyle(color=ft.Colors.RED_400),
        )

        def refresh_recovery() -> None:
            damaged = (not self.is_create) and self.store.isVaultDamaged()
            restore_button.visible = damaged and self.store.backupExists()
            start_over_button.visible = damaged
            if damaged and not error_text.value:
                error_text.value = VAULT_DAMAGED_MESSAGE

        def switch_to_create() -> None:
            self.naming_new = False
            self.is_create = True
            title_text.value = "Create master password"
            subtitle_text.value = (
                "This password encrypts your PATs and project settings on this machine."
            )
            name_field.visible = False
            confirm_field.visible = True
            primary_button.text = "Create vault"
            new_vault_button.visible = True
            cancel_button.visible = False
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

        def start_new_vault(_e: ft.ControlEvent) -> None:
            self.naming_new = True
            self.is_create = True
            self._notice = ""
            self._rerender()

        def cancel_new_vault(_e: ft.ControlEvent) -> None:
            self.naming_new = False
            last = self.registry.last()
            if last is not None:
                self.store.selectVault(self.registry.pathFor(last))
            self.is_create = not self.store.vaultExists()
            self._notice = ""
            self._rerender()

        password_field.on_submit = lambda _e: self._submit(
            name_field,
            password_field,
            confirm_field,
            error_text,
            restore_button,
            start_over_button,
        )
        name_field.on_submit = password_field.on_submit
        confirm_field.on_submit = password_field.on_submit
        primary_button.on_click = password_field.on_submit
        new_vault_button.on_click = start_new_vault
        cancel_button.on_click = cancel_new_vault
        restore_button.on_click = lambda _e: self._restoreBackup(
            password_field,
            error_text,
            restore_button,
            start_over_button,
        )
        start_over_button.on_click = lambda _e: self._confirmStartOver(
            error_text,
        )

        refresh_recovery()

        form_controls: list[ft.Control] = [
            ft.Icon(ft.Icons.SYNC, size=56, color=ft.Colors.PRIMARY),
            ft.Text("Git Syncher", size=28, weight=ft.FontWeight.BOLD),
            title_text,
            subtitle_text,
            ft.Container(height=8),
        ]
        if vault_dropdown is not None:
            form_controls.append(vault_dropdown)
        form_controls.extend(
            [
                name_field,
                password_field,
                confirm_field,
                error_text,
                primary_button,
                new_vault_button,
                cancel_button,
                restore_button,
                start_over_button,
            ]
        )
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
                        width=form_width,
                    ),
                ]
            )

        self._switch_to_create = switch_to_create
        self._show_recovery_after_damage = show_recovery_after_damage

        form = ft.Container(
            expand=True,
            alignment=ft.Alignment.CENTER,
            content=ft.Column(
                form_controls,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                scroll=ft.ScrollMode.AUTO,
                expand=True,
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
            padding=12,
            content=ft.Column(
                [form, footer],
                expand=True,
            ),
        )

    # --------------------------------------------------------
    # Method: _submit
    # Purpose: Validate password and create or unlock the vault.
    # --------------------------------------------------------
    def _submit(
        self,
        name_field: ft.TextField,
        password_field: ft.TextField,
        confirm_field: ft.TextField,
        error_text: ft.Text,
        restore_button: ft.OutlinedButton,
        start_over_button: ft.OutlinedButton,
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

        if self.naming_new:
            try:
                cleaned = self.registry.validateName(name_field.value or "")
            except ValueError as exc:
                error_text.value = str(exc)
                self.page.update()
                return
            created: Optional[VaultEntry] = None
            try:
                created = self.registry.add(cleaned)
                self.store.selectVault(self.registry.pathFor(created))
                self.store.createVault(password)
            except Exception as exc:  # noqa: BLE001
                if created is not None:
                    self._rollbackNewVault(created)
                error_text.value = f"Could not create vault: {exc}"
                self.page.update()
                return
        elif self.is_create:
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
    # Method: _rollbackNewVault
    # Purpose: Undo a registry entry when creating its file failed.
    # --------------------------------------------------------
    def _rollbackNewVault(self, entry: VaultEntry) -> None:
        path = self.registry.pathFor(entry)
        try:
            self.registry.remove(entry.id)
        except KeyError:
            pass
        for candidate in (
            path,
            path.with_suffix(path.suffix + ".bak"),
            path.with_suffix(path.suffix + ".tmp"),
        ):
            if candidate.is_file():
                try:
                    candidate.unlink()
                except OSError:
                    pass
        last = self.registry.last()
        if last is not None:
            self.store.selectVault(self.registry.pathFor(last))
        else:
            self.store.lock()

    # --------------------------------------------------------
    # Method: _finishUnlock
    # Purpose: Remember this vault, drop duplicates, open dashboard.
    # --------------------------------------------------------
    def _finishUnlock(self) -> None:
        entry = self._selectedEntry()
        if entry is not None:
            self.registry.setLast(entry.id)
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
    def _confirmStartOver(self, error_text: ft.Text) -> None:
        def do_start_over() -> None:
            if not self.store.discardDamagedVault():
                error_text.value = (
                    "Could not remove the damaged vault file. "
                    "Close the app and delete the vault file manually."
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
                "A backup of the vault is kept if one exists."
            ),
            confirm_label="Start over",
            on_confirm=do_start_over,
        )

    # --------------------------------------------------------
    # Method: _restoreBackup
    # Purpose: Copy the vault backup over the vault file, then unlock.
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
                "No usable backup found. "
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
