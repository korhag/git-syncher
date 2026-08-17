from __future__ import annotations

import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Optional

from app.core.crypto import VaultCrypto
from app.models.project import ProjectConfig


# Shown when vault.enc is empty or not valid JSON (not a wrong password).
VAULT_DAMAGED_MESSAGE = (
    "The vault file is empty or damaged (often after a crash while saving). "
    "Use Restore backup if you have vault.enc.bak, or Start over to create a new vault "
    "and re-add projects."
)


# ------------------------------------------------------------
# Class: VaultDamagedError
# Purpose: Raised when vault.enc cannot be parsed as an envelope.
# ------------------------------------------------------------
class VaultDamagedError(RuntimeError):
    pass


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
    # Method: backupPath
    # Purpose: Path to the last-known-good vault backup.
    # --------------------------------------------------------
    def backupPath(self) -> Path:
        return self.vault_path.with_suffix(self.vault_path.suffix + ".bak")

    # --------------------------------------------------------
    # Method: tmpPath
    # Purpose: Temporary path used for atomic writes.
    # --------------------------------------------------------
    def tmpPath(self) -> Path:
        return self.vault_path.with_suffix(self.vault_path.suffix + ".tmp")

    # --------------------------------------------------------
    # Method: vaultExists
    # Purpose: Whether a vault file already exists on disk.
    # --------------------------------------------------------
    def vaultExists(self) -> bool:
        return self.vault_path.is_file()

    # --------------------------------------------------------
    # Method: backupExists
    # Purpose: Whether a non-empty vault.enc.bak exists.
    # --------------------------------------------------------
    def backupExists(self) -> bool:
        path = self.backupPath()
        return path.is_file() and path.stat().st_size > 0

    # --------------------------------------------------------
    # Method: isVaultDamaged
    # Purpose: True when vault.enc exists but is empty or invalid.
    # --------------------------------------------------------
    def isVaultDamaged(self) -> bool:
        if not self.vaultExists():
            return False
        return not self._looksLikeValidEnvelope(self.vault_path)

    # --------------------------------------------------------
    # Method: discardDamagedVault
    # Purpose: Delete broken vault.enc and .tmp; keep .bak.
    # Output: bool - True if the vault file was removed (or gone).
    # --------------------------------------------------------
    def discardDamagedVault(self) -> bool:
        removed = False
        for path in (self.vault_path, self.tmpPath()):
            if path.is_file():
                try:
                    path.unlink()
                    removed = True
                except OSError:
                    return False
        self.lock()
        return not self.vaultExists() or removed

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
        if not raw.strip():
            raise VaultDamagedError(VAULT_DAMAGED_MESSAGE)
        try:
            envelope = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise VaultDamagedError(VAULT_DAMAGED_MESSAGE) from exc
        if not isinstance(envelope, dict) or "salt" not in envelope or "payload" not in envelope:
            raise VaultDamagedError(VAULT_DAMAGED_MESSAGE)

        salt_hex = envelope["salt"]
        fingerprint = envelope.get("fingerprint", "")
        crypto = VaultCrypto.fromSaltHex(salt_hex)
        expected = VaultCrypto.passwordFingerprint(password, crypto.salt)
        if fingerprint and fingerprint != expected:
            return False
        crypto.unlock(password)
        try:
            plaintext = crypto.decrypt(bytes.fromhex(envelope["payload"]))
        except (ValueError, TypeError):
            return False
        try:
            data = json.loads(plaintext.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise VaultDamagedError(VAULT_DAMAGED_MESSAGE) from exc
        self.crypto = crypto
        self._fingerprint = expected
        self.projects = [ProjectConfig.fromDict(item) for item in data.get("projects", [])]
        return True

    # --------------------------------------------------------
    # Method: restoreBackup
    # Purpose: Replace damaged vault.enc with vault.enc.bak.
    # Output: bool - True if restore succeeded.
    # --------------------------------------------------------
    def restoreBackup(self) -> bool:
        bak = self.backupPath()
        if not bak.is_file() or bak.stat().st_size == 0:
            return False
        self.vault_path.parent.mkdir(parents=True, exist_ok=True)
        # Copy to tmp then replace so a failed copy does not wipe vault.enc.
        tmp = self.tmpPath()
        shutil.copy2(bak, tmp)
        os.replace(tmp, self.vault_path)
        return True

    # --------------------------------------------------------
    # Method: save
    # Purpose: Encrypt and write the current project list atomically.
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
        text = json.dumps(envelope, indent=2)
        self.vault_path.parent.mkdir(parents=True, exist_ok=True)

        # Keep last good vault before replace (only if current looks valid).
        if self._looksLikeValidEnvelope(self.vault_path):
            shutil.copy2(self.vault_path, self.backupPath())

        tmp = self.tmpPath()
        with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, self.vault_path)

    # --------------------------------------------------------
    # Method: _looksLikeValidEnvelope
    # Purpose: True when path is non-empty JSON with salt/payload.
    # --------------------------------------------------------
    @staticmethod
    def _looksLikeValidEnvelope(path: Path) -> bool:
        if not path.is_file() or path.stat().st_size == 0:
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return False
        return (
            isinstance(data, dict)
            and bool(data.get("salt"))
            and bool(data.get("payload"))
        )

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
    # Method: normalizePath
    # Purpose: Canonical folder path for duplicate checks.
    # --------------------------------------------------------
    @staticmethod
    def normalizePath(path: str) -> str:
        raw = (path or "").strip()
        if not raw:
            return ""
        candidate = Path(raw).expanduser()
        try:
            return str(candidate.resolve())
        except OSError:
            return os.path.normpath(str(candidate))

    # --------------------------------------------------------
    # Method: findDuplicate
    # Purpose: Existing project with same folder + default branch.
    # Input: path, branch; exclude_id skips that project (edit).
    # Output: ProjectConfig or None.
    # --------------------------------------------------------
    def findDuplicate(
        self,
        path: str,
        branch: str,
        exclude_id: Optional[str] = None,
    ) -> Optional[ProjectConfig]:
        key_path = self.normalizePath(path)
        key_branch = (branch or "").strip()
        if not key_path:
            return None
        for project in self.projects:
            if exclude_id and project.id == exclude_id:
                continue
            if (
                self.normalizePath(project.path) == key_path
                and (project.default_branch or "").strip() == key_branch
            ):
                return project
        return None

    # --------------------------------------------------------
    # Method: collapseDuplicateProjects
    # Purpose: Keep first of each path+branch pair; drop extras.
    # Output: int - number of removed entries (0 if unchanged).
    # --------------------------------------------------------
    def collapseDuplicateProjects(self) -> int:
        seen: set[tuple[str, str]] = set()
        kept: list[ProjectConfig] = []
        removed = 0
        for project in self.projects:
            key = (
                self.normalizePath(project.path),
                (project.default_branch or "").strip(),
            )
            if key in seen:
                removed += 1
                continue
            seen.add(key)
            kept.append(project)
        if removed:
            self.projects = kept
            self.save()
        return removed

    # --------------------------------------------------------
    # Method: addProject
    # Purpose: Append a project and persist the vault.
    # --------------------------------------------------------
    def addProject(self, project: ProjectConfig) -> ProjectConfig:
        if not project.id:
            project.id = str(uuid.uuid4())
        dup = self.findDuplicate(project.path, project.default_branch)
        if dup is not None:
            branch = (project.default_branch or "").strip() or "…"
            raise ValueError(
                f"This folder is already tracked for branch {branch}."
            )
        project.path = self.normalizePath(project.path) or project.path
        self.projects.append(project)
        self.save()
        return project

    # --------------------------------------------------------
    # Method: updateProject
    # Purpose: Replace a project by id and persist.
    # --------------------------------------------------------
    def updateProject(self, project: ProjectConfig) -> None:
        dup = self.findDuplicate(
            project.path,
            project.default_branch,
            exclude_id=project.id,
        )
        if dup is not None:
            branch = (project.default_branch or "").strip() or "…"
            raise ValueError(
                f"This folder is already tracked for branch {branch}."
            )
        project.path = self.normalizePath(project.path) or project.path
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

