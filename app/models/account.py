from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


# ------------------------------------------------------------
# Class: VaultAccount
# Purpose: Reusable Git identity stored in the encrypted vault.
# ------------------------------------------------------------
@dataclass
class VaultAccount:
    id: str
    label: str
    username: str
    email: str

    # --------------------------------------------------------
    # Method: toDict
    # Purpose: Serialize for vault storage.
    # --------------------------------------------------------
    def toDict(self) -> dict[str, Any]:
        return asdict(self)

    # --------------------------------------------------------
    # Method: fromDict
    # Purpose: Restore from vault JSON.
    # --------------------------------------------------------
    @classmethod
    def fromDict(cls, data: dict[str, Any]) -> "VaultAccount":
        return cls(
            id=str(data.get("id", "")),
            label=str(data.get("label", "")),
            username=str(data.get("username", "")),
            email=str(data.get("email", "")),
        )
