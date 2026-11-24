from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


DEFAULT_VAULT_NAME = "Default"
LEGACY_VAULT_FILE = "vault.enc"
REGISTRY_FILE = "vaults.json"


# ------------------------------------------------------------
# Class: VaultEntry
# Purpose: Plain metadata for one vault. The password and
#          projects stay inside the encrypted vault file.
# ------------------------------------------------------------
@dataclass
class VaultEntry:
    id: str
    name: str
    file: str


# ------------------------------------------------------------
# Class: VaultRegistry
# Purpose: Remember vault names, files, and the last-used vault.
#          Stored as plaintext JSON under data/ (no secrets).
# ------------------------------------------------------------
class VaultRegistry:
    # --------------------------------------------------------
    # Method: __init__
    # Purpose: Load data/vaults.json, or migrate data/vault.enc.
    # Input: data_dir (Path) - Folder that holds the registry.
    #        Defaults to <repo>/data.
    # --------------------------------------------------------
    def __init__(self, data_dir: Optional[Path] = None) -> None:
        root = Path(__file__).resolve().parents[2]
        self.data_dir = data_dir or (root / "data")
        self._entries: list[VaultEntry] = []
        self._last_id: str = ""
        self._load()

    # --------------------------------------------------------
    # Method: registryPath
    # Purpose: Path of the plaintext vault index.
    # --------------------------------------------------------
    def registryPath(self) -> Path:
        return self.data_dir / REGISTRY_FILE

    # --------------------------------------------------------
    # Method: list
    # Purpose: Vaults in saved order.
    # --------------------------------------------------------
    def list(self) -> list[VaultEntry]:
        return list(self._entries)

    # --------------------------------------------------------
    # Method: get
    # Purpose: Look up a vault by id.
    # --------------------------------------------------------
    def get(self, vault_id: str) -> Optional[VaultEntry]:
        for entry in self._entries:
            if entry.id == vault_id:
                return entry
        return None

    # --------------------------------------------------------
    # Method: last
    # Purpose: Last-used vault, or the first one if that id is gone.
    # --------------------------------------------------------
    def last(self) -> Optional[VaultEntry]:
        found = self.get(self._last_id)
        if found is not None:
            return found
        if self._entries:
            return self._entries[0]
        return None

    # --------------------------------------------------------
    # Method: setLast
    # Purpose: Remember which vault to open next time.
    # --------------------------------------------------------
    def setLast(self, vault_id: str) -> None:
        if self.get(vault_id) is None:
            raise KeyError(f"Vault not found: {vault_id}")
        if self._last_id == vault_id:
            return
        self._last_id = vault_id
        self._save()

    # --------------------------------------------------------
    # Method: findByName
    # Purpose: Existing vault with the same name (case-insensitive).
    # --------------------------------------------------------
    def findByName(self, name: str) -> Optional[VaultEntry]:
        key = self.normalizeName(name)
        if not key:
            return None
        for entry in self._entries:
            if self.normalizeName(entry.name) == key:
                return entry
        return None

    # --------------------------------------------------------
    # Method: validateName
    # Purpose: Reject an empty or duplicate vault name.
    # --------------------------------------------------------
    def validateName(self, name: str) -> str:
        cleaned = (name or "").strip()
        if not cleaned:
            raise ValueError("Enter a vault name.")
        dup = self.findByName(cleaned)
        if dup is not None:
            raise ValueError(f"A vault named “{cleaned}” already exists.")
        return cleaned

    # --------------------------------------------------------
    # Method: add
    # Purpose: Register a new vault file and make it the last one.
    #          Does not create the encrypted file.
    # --------------------------------------------------------
    def add(self, name: str) -> VaultEntry:
        cleaned = self.validateName(name)
        vault_id = str(uuid.uuid4())
        entry = VaultEntry(
            id=vault_id,
            name=cleaned,
            file=f"vaults/{vault_id}.enc",
        )
        self._entries.append(entry)
        self._last_id = entry.id
        self._save()
        return entry

    # --------------------------------------------------------
    # Method: remove
    # Purpose: Drop a registry entry (used to roll back a failed
    #          create). Does not delete the encrypted file.
    # --------------------------------------------------------
    def remove(self, vault_id: str) -> None:
        if self.get(vault_id) is None:
            raise KeyError(f"Vault not found: {vault_id}")
        self._entries = [entry for entry in self._entries if entry.id != vault_id]
        if self._last_id == vault_id:
            self._last_id = self._entries[0].id if self._entries else ""
        self._save()

    # --------------------------------------------------------
    # Method: pathFor
    # Purpose: Absolute path of a vault's encrypted file.
    # --------------------------------------------------------
    def pathFor(self, entry: VaultEntry) -> Path:
        return (self.data_dir / entry.file).resolve()

    # --------------------------------------------------------
    # Method: normalizeName
    # Purpose: Trim and lowercase for duplicate name checks.
    # --------------------------------------------------------
    @staticmethod
    def normalizeName(name: str) -> str:
        return (name or "").strip().casefold()

    # --------------------------------------------------------
    # Method: _load
    # Purpose: Read the registry, or adopt a legacy vault.enc.
    # --------------------------------------------------------
    def _load(self) -> None:
        path = self.registryPath()
        if path.is_file():
            if self._readRegistry(path):
                self._repairLast()
                return
        self._migrateLegacyOrEmpty()

    # --------------------------------------------------------
    # Method: _readRegistry
    # Purpose: Parse vaults.json. False when the file is unusable.
    # --------------------------------------------------------
    def _readRegistry(self, path: Path) -> bool:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return False
        if not isinstance(data, dict):
            return False
        raw_vaults = data.get("vaults", [])
        if not isinstance(raw_vaults, list):
            return False
        entries: list[VaultEntry] = []
        for item in raw_vaults:
            if not isinstance(item, dict):
                continue
            vault_id = str(item.get("id") or "").strip()
            name = str(item.get("name") or "").strip()
            relative = str(item.get("file") or "").strip()
            if not vault_id or not name or not self._isSafeRelative(relative):
                continue
            entries.append(VaultEntry(id=vault_id, name=name, file=relative))
        self._entries = entries
        self._last_id = str(data.get("last_id") or "").strip()
        return True

    # --------------------------------------------------------
    # Method: _repairLast
    # Purpose: Point last_id at a real vault when it is stale.
    # --------------------------------------------------------
    def _repairLast(self) -> None:
        if not self._entries:
            if self._last_id:
                self._last_id = ""
                self._save()
            return
        if self.get(self._last_id) is None:
            self._last_id = self._entries[0].id
            self._save()

    # --------------------------------------------------------
    # Method: _migrateLegacyOrEmpty
    # Purpose: Register data/vault.enc as "Default" once, without
    #          moving or rewriting the encrypted file.
    # --------------------------------------------------------
    def _migrateLegacyOrEmpty(self) -> None:
        legacy = self.data_dir / LEGACY_VAULT_FILE
        if legacy.is_file():
            entry = VaultEntry(
                id=str(uuid.uuid4()),
                name=DEFAULT_VAULT_NAME,
                file=LEGACY_VAULT_FILE,
            )
            self._entries = [entry]
            self._last_id = entry.id
            self._save()
            return
        self._entries = []
        self._last_id = ""

    # --------------------------------------------------------
    # Method: _isSafeRelative
    # Purpose: Reject absolute paths and parent-directory escapes.
    # --------------------------------------------------------
    @staticmethod
    def _isSafeRelative(relative: str) -> bool:
        path = Path(relative)
        if path.is_absolute():
            return False
        return ".." not in path.parts

    # --------------------------------------------------------
    # Method: _save
    # Purpose: Write the registry atomically.
    # --------------------------------------------------------
    def _save(self) -> None:
        payload = {
            "last_id": self._last_id,
            "vaults": [
                {"id": entry.id, "name": entry.name, "file": entry.file}
                for entry in self._entries
            ],
        }
        text = json.dumps(payload, indent=2)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.registryPath().with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, self.registryPath())
