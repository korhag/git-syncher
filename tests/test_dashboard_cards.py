from __future__ import annotations

import flet as ft

from app.models.project import SuggestedAction
from app.ui.dashboard import cardBorderColor


# ------------------------------------------------------------
# Tests: cardBorderColor
# ------------------------------------------------------------
class TestCardBorderColor:
    # --------------------------------------------------------
    # Method: testSyncedHasNoAccent
    # Purpose: Synced cards stay on the normal outline.
    # --------------------------------------------------------
    def testSyncedHasNoAccent(self) -> None:
        assert cardBorderColor(SuggestedAction.SYNCED) is None

    # --------------------------------------------------------
    # Method: testUnsyncedUsesActionColor
    # Purpose: Every other state keeps its existing chip color.
    # --------------------------------------------------------
    def testUnsyncedUsesActionColor(self) -> None:
        expected = {
            SuggestedAction.COMMIT: ft.Colors.AMBER_400,
            SuggestedAction.PUSH: ft.Colors.BLUE_400,
            SuggestedAction.PULL: ft.Colors.CYAN_400,
            SuggestedAction.MERGE: ft.Colors.ORANGE_400,
            SuggestedAction.RESOLVE: ft.Colors.ORANGE_400,
            SuggestedAction.NOT_A_REPO: ft.Colors.GREY_400,
            SuggestedAction.MISSING_PATH: ft.Colors.RED_400,
            SuggestedAction.UNKNOWN: ft.Colors.GREY_400,
        }
        for action, color in expected.items():
            assert cardBorderColor(action) == color
