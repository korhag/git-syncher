from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from app.core.actions import ActionId, ActionOutcome


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
            ft.Text(outcome.message, size=14),
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
            title=ft.Text(outcome.title),
            content=ft.Column(
                content_controls,
                tight=True,
                scroll=ft.ScrollMode.AUTO,
                width=420,
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
            title=ft.Text(title),
            content=ft.Column(
                [
                    ft.Text(message),
                    checkbox,
                    error_text,
                ],
                tight=True,
                width=400,
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
            title=ft.Text("Commit changes"),
            content=ft.Column([field, error_text], tight=True, width=420),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _e: page.pop_dialog()),
                ft.FilledButton("Commit", on_click=handle_commit),
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
            title=ft.Text(f"Compare: {file_path}"),
            content=ft.Container(
                content=ft.Text(
                    diff_text or "(empty)",
                    selectable=True,
                    font_family="Consolas",
                    size=12,
                ),
                width=640,
                height=420,
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
    # --------------------------------------------------------
    @staticmethod
    def showSnack(page: ft.Page, message: str, error: bool = False) -> None:
        page.show_dialog(
            ft.SnackBar(
                content=ft.Text(message),
                bgcolor=ft.Colors.ERROR_CONTAINER if error else None,
            )
        )
