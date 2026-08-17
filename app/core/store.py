from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Optional

from app.core.crypto import VaultCrypto
from app.models.project import ProjectConfig


# ------------------------------------------------------------
# Class: VaultStore
# Purpose: Load and save the encrypted project vault to disk.
# ------------------------------------------------------------
class VaultStore:
    # --------------------------------------------------------
    # Method: __init__
    # Purpose: Point at a vault file path under data/.
    # --------------------------------------------------------
    def __init__(self, vault_path: Optional[Path] = None) -> None:
        root = Path(__file__).resolve().parents[2]
        self.vault_path = vault_path or (root / "data" / "vault.enc")
        self.crypto: Optional[VaultCrypto] = None
        self.projects: list[ProjectConfig] = []
        self._fingerprint: str = ""

    # --------------------------------------------------------
    # Method: vaultExists
    # Purpose: Whether a vault file already exists on disk.
    # --------------------------------------------------------
    def vaultExists(self) -> bool:
        return self.vault_path.is_file()

    # --------------------------------------------------------
    # Method: createVault
    # Purpose: Create a new empty vault protected by password.
    # Input: password (str) - New master password.
    # Output: None
    # --------------------------------------------------------
    def createVault(self, password: str) -> None:
        self.vault_path.parent.mkdir(parents=True, exist_ok=True)
        self.crypto = VaultCrypto()
        self.crypto.unlock(password)
        self._fingerprint = VaultCrypto.passwordFingerprint(password, self.crypto.salt)
        self.projects = []
        self.save()

    # --------------------------------------------------------
    # Method: unlockVault
    # Purpose: Unlock an existing vault with the master password.
    # Input: password (str)
    # Output: bool - True if unlock succeeded.
    # --------------------------------------------------------
    def unlockVault(self, password: str) -> bool:
        if not self.vaultExists():
            raise FileNotFoundError("Vault does not exist. Create one first.")
        raw = self.vault_path.read_bytes()
        envelope = json.loads(raw.decode("utf-8"))
        salt_hex = envelope["salt"]
        fingerprint = envelope.get("fingerprint", "")
        crypto = VaultCrypto.fromSaltHex(salt_hex)
        expected = VaultCrypto.passwordFingerprint(password, crypto.salt)
        if fingerprint and fingerprint != expected:
            return False
        crypto.unlock(password)
        try:
            plaintext = crypto.decrypt(bytes.fromhex(envelope["payload"]))
        except ValueError:
            return False
        data = json.loads(plaintext.decode("utf-8"))
        self.crypto = crypto
        self._fingerprint = expected
        self.projects = [ProjectConfig.fromDict(item) for item in data.get("projects", [])]
        return True

    # --------------------------------------------------------
    # Method: save
    # Purpose: Encrypt and write the current project list.
    # --------------------------------------------------------
    def save(self) -> None:
        if self.crypto is None or not self.crypto.isUnlocked():
            raise RuntimeError("Cannot save: vault is locked.")
        payload = {
            "version": 1,
            "projects": [project.toDict() for project in self.projects],
        }
        plaintext = json.dumps(payload, indent=2).encode("utf-8")
        token = self.crypto.encrypt(plaintext)
        envelope = {
            "salt": self.crypto.saltHex(),
            "fingerprint": self._fingerprint,
            "payload": token.hex(),
        }
        self.vault_path.parent.mkdir(parents=True, exist_ok=True)
        self.vault_path.write_text(json.dumps(envelope, indent=2), encoding="utf-8")

    # --------------------------------------------------------
    # Method: lock
    # Purpose: Clear secrets from memory.
    # --------------------------------------------------------
    def lock(self) -> None:
        if self.crypto is not None:
            self.crypto.lock()
        self.projects = []
        self._fingerprint = ""

    # --------------------------------------------------------
    # Method: addProject
    # Purpose: Append a project and persist the vault.
    # --------------------------------------------------------
    def addProject(self, project: ProjectConfig) -> ProjectConfig:
        if not project.id:
            project.id = str(uuid.uuid4())
        self.projects.append(project)
        self.save()
        return project

    # --------------------------------------------------------
    # Method: updateProject
    # Purpose: Replace a project by id and persist.
    # --------------------------------------------------------
    def updateProject(self, project: ProjectConfig) -> None:
        for index, existing in enumerate(self.projects):
            if existing.id == project.id:
                self.projects[index] = project
                self.save()
                return
        raise KeyError(f"Project not found: {project.id}")

    # --------------------------------------------------------
    # Method: removeProject
    # Purpose: Delete a project by id and persist.
    # --------------------------------------------------------
    def removeProject(self, project_id: str) -> None:
        self.projects = [p for p in self.projects if p.id != project_id]
        self.save()

    # --------------------------------------------------------
    # Method: getProject
    # Purpose: Look up a project by id.
    # --------------------------------------------------------
    def getProject(self, project_id: str) -> Optional[ProjectConfig]:
        for project in self.projects:
            if project.id == project_id:
                return project
        return None
