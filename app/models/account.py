from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Optional, Sequence


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

    # --------------------------------------------------------
    # Method: identity
    # Purpose: Username and email to copy into a project.
    # --------------------------------------------------------
    def identity(self) -> tuple[str, str]:
        return self.username, self.email


# ------------------------------------------------------------
# Function: findAccountByKey
# Purpose: Resolve a dropdown value (id, label, or "label (user)").
# ------------------------------------------------------------
def findAccountByKey(
    accounts: Sequence[VaultAccount],
    raw: str,
) -> Optional[VaultAccount]:
    key = (raw or "").strip()
    if not key:
        return None
    for account in accounts:
        if account.id == key:
            return account
        label = f"{account.label} ({account.username})"
        if label == key or account.label == key:
            return account
    return None
