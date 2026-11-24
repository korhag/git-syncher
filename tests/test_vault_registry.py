from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from app.core.vault_registry import DEFAULT_VAULT_NAME, LEGACY_VAULT_FILE, VaultRegistry


# ------------------------------------------------------------
# Tests: VaultRegistry names, last vault, and legacy migration
# ------------------------------------------------------------
class TestVaultRegistry:
    # --------------------------------------------------------
    # Method: testAddPersistsAndBecomesLast
    # --------------------------------------------------------
    def testAddPersistsAndBecomesLast(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            registry = VaultRegistry(data_dir=data_dir)
            first = registry.add("Work")
            second = registry.add("Personal")
            assert [entry.name for entry in registry.list()] == ["Work", "Personal"]
            assert registry.last() == second
            assert registry.pathFor(second) == (data_dir / "vaults" / f"{second.id}.enc").resolve()

            reloaded = VaultRegistry(data_dir=data_dir)
            assert reloaded.last() is not None
            assert reloaded.last().id == second.id
            assert reloaded.get(first.id) is not None
            assert reloaded.get(first.id).name == "Work"

    # --------------------------------------------------------
    # Method: testRejectsEmptyAndDuplicateNames
    # --------------------------------------------------------
    def testRejectsEmptyAndDuplicateNames(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry = VaultRegistry(data_dir=Path(tmp))
            registry.add("Work")
            with pytest.raises(ValueError, match="Enter a vault name"):
                registry.add("   ")
            with pytest.raises(ValueError, match="already exists"):
                registry.add("work")
            assert len(registry.list()) == 1

    # --------------------------------------------------------
    # Method: testSetLastPersists
    # --------------------------------------------------------
    def testSetLastPersists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            registry = VaultRegistry(data_dir=data_dir)
            first = registry.add("Work")
            registry.add("Personal")
            registry.setLast(first.id)
            reloaded = VaultRegistry(data_dir=data_dir)
            assert reloaded.last() is not None
            assert reloaded.last().id == first.id

    # --------------------------------------------------------
    # Method: testStaleLastIdFallsBackToFirst
    # --------------------------------------------------------
    def testStaleLastIdFallsBackToFirst(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            registry = VaultRegistry(data_dir=data_dir)
            first = registry.add("Work")
            registry.add("Personal")
            raw = json.loads(registry.registryPath().read_text(encoding="utf-8"))
            raw["last_id"] = "missing"
            registry.registryPath().write_text(json.dumps(raw), encoding="utf-8")

            reloaded = VaultRegistry(data_dir=data_dir)
            assert reloaded.last() is not None
            assert reloaded.last().id == first.id
            saved = json.loads(registry.registryPath().read_text(encoding="utf-8"))
            assert saved["last_id"] == first.id

    # --------------------------------------------------------
    # Method: testLegacyVaultMigratesInPlace
    # --------------------------------------------------------
    def testLegacyVaultMigratesInPlace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            legacy = data_dir / LEGACY_VAULT_FILE
            legacy.write_bytes(b"encrypted-bytes")

            registry = VaultRegistry(data_dir=data_dir)
            entries = registry.list()
            assert len(entries) == 1
            assert entries[0].name == DEFAULT_VAULT_NAME
            assert entries[0].file == LEGACY_VAULT_FILE
            assert registry.pathFor(entries[0]) == legacy.resolve()
            assert registry.last() == entries[0]
            assert legacy.read_bytes() == b"encrypted-bytes"

            again = VaultRegistry(data_dir=data_dir)
            assert len(again.list()) == 1
            assert again.list()[0].id == entries[0].id
            assert legacy.read_bytes() == b"encrypted-bytes"

    # --------------------------------------------------------
    # Method: testRemoveRepointsLastVault
    # --------------------------------------------------------
    def testRemoveRepointsLastVault(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry = VaultRegistry(data_dir=Path(tmp))
            first = registry.add("Work")
            second = registry.add("Personal")
            registry.remove(second.id)
            assert registry.last() is not None
            assert registry.last().id == first.id
            assert registry.get(second.id) is None
