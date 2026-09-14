from __future__ import annotations

from typing import Any, Callable, Optional

import flet as ft

from app.core.actions import ActionId, ActionOutcome
from app.ui.layout import dialogHeight, dialogWidth


# ------------------------------------------------------------
# Class: Dialogs
# Purpose: Shared modal dialogs for choices, confirmations,
#          commit message, diffs, and toasts (Flet 0.86+).
# ------------------------------------------------------------
class Dialogs:
    # --------------------------------------------------------
    # Method: showChoice
    # Purpose: Present ActionOutcome choices; call on_choice(id).
    # --------------------------------------------------------
    @staticmethod
    def showChoice(
        page: ft.Page,
        outcome: ActionOutcome,
        on_choice: Callable[[ActionId], None],
    ) -> None:
        details_control = ft.Text(
            outcome.details or "",
            selectable=True,
            size=12,
            color=ft.Colors.ON_SURFACE_VARIANT,
            visible=False,
        )

        def close_and(action_id: ActionId) -> None:
            page.pop_dialog()
            on_choice(action_id)

        buttons: list[ft.Control] = []
        for choice in outcome.choices:
            color = ft.Colors.RED_400 if choice.destructive else None

            def make_handler(cid: ActionId = choice.id) -> Callable[[ft.ControlEvent], None]:
                return lambda _e: close_and(cid)

            buttons.append(
                ft.TextButton(
                    choice.label,
                    on_click=make_handler(),
                    style=ft.ButtonStyle(color=color) if color else None,
                    tooltip=choice.description or None,
                )
            )

        def toggle_details(_e: ft.ControlEvent) -> None:
            details_control.visible = not details_control.visible
            page.update()

        content_controls: list[ft.Control] = [
            ft.Text(outcome.message, size=13, selectable=True),
        ]
        if outcome.details:
            content_controls.append(
                ft.TextButton(
                    "Show details",
                    on_click=toggle_details,
                    icon=ft.Icons.INFO_OUTLINE,
                )
            )
            content_controls.append(details_control)

        dialog = ft.AlertDialog(
            modal=True,
            scrollable=True,
            title=ft.Text(outcome.title),
            content=ft.Column(
                content_controls,
                tight=True,
                scroll=ft.ScrollMode.AUTO,
                width=dialogWidth(page, preferred=520),
                height=dialogHeight(page, preferred=420),
            ),
            actions=buttons,
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.show_dialog(dialog)

    # --------------------------------------------------------
    # Method: showConfirm
    # Purpose: Destructive confirmation with required checkbox.
    # --------------------------------------------------------
    @staticmethod
    def showConfirm(
        page: ft.Page,
        title: str,
        message: str,
        confirm_label: str,
        on_confirm: Callable[[], None],
        on_cancel: Optional[Callable[[], None]] = None,
    ) -> None:
        checkbox = ft.Checkbox(label="I understand this cannot be undone", value=False)
        error_text = ft.Text("", color=ft.Colors.RED_400, size=12)

        def handle_cancel(_e: ft.ControlEvent) -> None:
            page.pop_dialog()
            if on_cancel:
                on_cancel()

        def handle_confirm(_e: ft.ControlEvent) -> None:
            if not checkbox.value:
                error_text.value = "Please confirm with the checkbox first."
                page.update()
                return
            page.pop_dialog()
            on_confirm()

        dialog = ft.AlertDialog(
            modal=True,
            scrollable=True,
            title=ft.Text(title),
            content=ft.Column(
                [
                    ft.Text(message, size=13, selectable=True),
                    checkbox,
                    error_text,
                ],
                tight=True,
                scroll=ft.ScrollMode.AUTO,
                width=dialogWidth(page, preferred=520),
                height=dialogHeight(page, preferred=360),
            ),
            actions=[
                ft.TextButton("Cancel", on_click=handle_cancel),
                ft.TextButton(
                    confirm_label,
                    on_click=handle_confirm,
                    style=ft.ButtonStyle(color=ft.Colors.RED_400),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.show_dialog(dialog)

    # --------------------------------------------------------
    # Method: showYesNo
    # Purpose: Simple confirm without the destructive checkbox.
    # --------------------------------------------------------
    @staticmethod
    def showYesNo(
        page: ft.Page,
        title: str,
        message: str,
        confirm_label: str,
        on_confirm: Callable[[], None],
        on_cancel: Optional[Callable[[], None]] = None,
    ) -> None:
        def handle_cancel(_e: ft.ControlEvent) -> None:
            page.pop_dialog()
            if on_cancel:
                on_cancel()

        def handle_confirm(_e: ft.ControlEvent) -> None:
            page.pop_dialog()
            on_confirm()

        dialog = ft.AlertDialog(
            modal=True,
            scrollable=True,
            title=ft.Text(title),
            content=ft.Text(
                message,
                width=dialogWidth(page, preferred=420),
            ),
            actions=[
                ft.TextButton("Cancel", on_click=handle_cancel),
                ft.FilledButton(confirm_label, on_click=handle_confirm),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.show_dialog(dialog)

    # --------------------------------------------------------
    # Method: showWarningChoice
    # Purpose: Warning dialog with stay vs continue actions.
    # --------------------------------------------------------
    @staticmethod
    def showWarningChoice(
        page: ft.Page,
        title: str,
        message: str,
        stay_label: str,
        continue_label: str,
        on_stay: Callable[[], None],
        on_continue: Callable[[], None],
    ) -> None:
        def handle_stay(_e: ft.ControlEvent) -> None:
            page.pop_dialog()
            on_stay()

        def handle_continue(_e: ft.ControlEvent) -> None:
            page.pop_dialog()
            on_continue()

        dialog = ft.AlertDialog(
            modal=True,
            scrollable=True,
            title=ft.Row(
                [
                    ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color=ft.Colors.AMBER_400),
                    ft.Text(title),
                ],
                spacing=8,
                tight=True,
            ),
            content=ft.Text(
                message,
                width=dialogWidth(page, preferred=420),
            ),
            actions=[
                ft.TextButton(continue_label, on_click=handle_continue),
                ft.FilledButton(stay_label, on_click=handle_stay),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.show_dialog(dialog)

    # --------------------------------------------------------
    # Method: showCommit
    # Purpose: Commit message dialog with optional prefill.
    # --------------------------------------------------------
    @staticmethod
    def showCommit(
        page: ft.Page,
        suggested_message: str,
        on_commit: Callable[[str], None],
    ) -> None:
        field = ft.TextField(
            label="Commit message",
            value=suggested_message,
            multiline=True,
            min_lines=2,
            max_lines=5,
            autofocus=True,
        )
        error_text = ft.Text("", color=ft.Colors.RED_400, size=12)

        def handle_commit(_e: ft.ControlEvent) -> None:
            message = (field.value or "").strip()
            if not message:
                error_text.value = "Commit message cannot be empty."
                page.update()
                return
            page.pop_dialog()
            on_commit(message)

        dialog = ft.AlertDialog(
            modal=True,
            scrollable=True,
            title=ft.Text("Commit changes"),
            content=ft.Column(
                [field, error_text],
                tight=True,
                width=dialogWidth(page, preferred=420),
            ),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _e: page.pop_dialog()),
                ft.FilledButton("Commit", on_click=handle_commit),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.show_dialog(dialog)

    # --------------------------------------------------------
    # Method: showPushVersionSuggest
    # Purpose: When there is no Changelog, suggest next Git tag version.
    # --------------------------------------------------------
    @staticmethod
    def showPushVersionSuggest(
        page: ft.Page,
        suggested_version: str,
        last_tag: str,
        on_push_only: Callable[[], None],
        on_push_and_tag: Callable[[str], None],
    ) -> None:
        tag_field = ft.TextField(
            label="Next version tag",
            value=suggested_version if suggested_version.startswith("v") else f"v{suggested_version}",
            autofocus=True,
        )
        from_note = (
            f"Latest Git tag: {last_tag}"
            if last_tag
            else "No Git tags yet — starting from v0.1.0"
        )
        hint = ft.Text(
            f"No Changelog.md with a version found. {from_note}. "
            "You can push as usual, or also create this tag on Git.",
            size=13,
            color=ft.Colors.ON_SURFACE_VARIANT,
        )

        def push_only(_e: ft.ControlEvent) -> None:
            page.pop_dialog()
            on_push_only()

        def push_and_tag(_e: ft.ControlEvent) -> None:
            version = (tag_field.value or "").strip()
            if not version:
                return
            page.pop_dialog()
            on_push_and_tag(version)

        dialog = ft.AlertDialog(
            modal=True,
            scrollable=True,
            title=ft.Text("Push — suggested version"),
            content=ft.Column(
                [hint, tag_field],
                tight=True,
                width=dialogWidth(page, preferred=420),
                spacing=12,
            ),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _e: page.pop_dialog()),
                ft.OutlinedButton("Push only", on_click=push_only),
                ft.FilledButton("Push and tag", on_click=push_and_tag),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.show_dialog(dialog)

    # --------------------------------------------------------
    # Method: showDiff
    # Purpose: Show unified diff text for a file.
    # --------------------------------------------------------
    @staticmethod
    def showDiff(page: ft.Page, file_path: str, diff_text: str) -> None:
        dialog = ft.AlertDialog(
            modal=True,
            scrollable=True,
            title=ft.Text(f"Compare: {file_path}"),
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Text(
                            diff_text or "(empty)",
                            selectable=True,
                            font_family="Consolas",
                            size=12,
                        ),
                    ],
                    scroll=ft.ScrollMode.AUTO,
                    expand=True,
                ),
                width=dialogWidth(page, preferred=640),
                height=dialogHeight(page, preferred=420),
                bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                padding=12,
                border_radius=8,
            ),
            actions=[ft.TextButton("Close", on_click=lambda _e: page.pop_dialog())],
        )
        page.show_dialog(dialog)

    # --------------------------------------------------------
    # Method: copyText
    # Purpose: Copy text with Flet 0.80+ Clipboard (async service).
    #          Falls back to a selectable dialog if clipboard fails.
    # --------------------------------------------------------
    @staticmethod
    def copyText(page: ft.Page, text: str, success_message: str) -> None:
        if not text:
            Dialogs.showSnack(page, "No paths to copy.")
            return

        setter = getattr(page, "set_clipboard", None)
        if callable(setter):
            try:
                setter(text)
                Dialogs.showSnack(page, success_message)
                return
            except Exception:
                Dialogs._showCopyFallback(page, text)
                return

        clip = Dialogs._clipboardService(page)
        run_task = getattr(page, "run_task", None)
        if clip is not None and callable(run_task):
            async def _set() -> None:
                try:
                    await clip.set(text)
                    Dialogs.showSnack(page, success_message)
                except Exception:
                    Dialogs._showCopyFallback(page, text)

            try:
                run_task(_set)
                return
            except Exception:
                pass
        Dialogs._showCopyFallback(page, text)

    # --------------------------------------------------------
    # Method: _clipboardService
    # Purpose: One Clipboard service attached to the page.
    # --------------------------------------------------------
    @staticmethod
    def _clipboardService(page: ft.Page) -> Optional[Any]:
        existing = getattr(page, "_syncher_clipboard", None)
        if existing is not None:
            return existing
        clipboard_cls = getattr(ft, "Clipboard", None)
        if clipboard_cls is None:
            return None
        try:
            clip = clipboard_cls()
        except Exception:
            return None
        services = getattr(page, "services", None)
        if services is not None:
            try:
                services.append(clip)
                page.update()
            except Exception:
                pass
        try:
            setattr(page, "_syncher_clipboard", clip)
        except Exception:
            pass
        return clip

    # --------------------------------------------------------
    # Method: _showCopyFallback
    # Purpose: Selectable path list when the clipboard API fails.
    # --------------------------------------------------------
    @staticmethod
    def _showCopyFallback(page: ft.Page, text: str) -> None:
        dialog = ft.AlertDialog(
            modal=True,
            scrollable=True,
            title=ft.Text("Copy these paths"),
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Text(
                            "Clipboard is not available here. "
                            "Select the text below and copy it.",
                            size=13,
                        ),
                        ft.Text(
                            text,
                            selectable=True,
                            font_family="Consolas",
                            size=12,
                        ),
                    ],
                    scroll=ft.ScrollMode.AUTO,
                    expand=True,
                    spacing=8,
                ),
                width=dialogWidth(page, preferred=640),
                height=dialogHeight(page, preferred=420),
                bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                padding=12,
                border_radius=8,
            ),
            actions=[ft.TextButton("Close", on_click=lambda _e: page.pop_dialog())],
        )
        page.show_dialog(dialog)

    # --------------------------------------------------------
    # Method: showSnack
    # Purpose: Brief status toast at the bottom of the page.
    # Notes: Implemented via show_dialog (Flet 0.86). Callers must
    #        pop any open AlertDialog first, or the snack steals the stack.
    # --------------------------------------------------------
    @staticmethod
    def showSnack(page: ft.Page, message: str, error: bool = False) -> None:
        page.show_dialog(
            ft.SnackBar(
                content=ft.Text(message),
                bgcolor=ft.Colors.ERROR_CONTAINER if error else None,
            )
        )
