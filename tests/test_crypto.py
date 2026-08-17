from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from app.core.crypto import VaultCrypto
from app.core.store import VAULT_DAMAGED_MESSAGE, VaultDamagedError, VaultStore
from app.models.project import ProjectConfig


# ------------------------------------------------------------
# Tests: VaultCrypto
# ------------------------------------------------------------
class TestVaultCrypto:
    # --------------------------------------------------------
    # Method: testEncryptDecryptRoundTrip
    # --------------------------------------------------------
    def testEncryptDecryptRoundTrip(self) -> None:
        crypto = VaultCrypto()
        crypto.unlock("correct-horse-battery")
        token = crypto.encrypt(b'{"hello": "world"}')
        assert crypto.decrypt(token) == b'{"hello": "world"}'

    # --------------------------------------------------------
    # Method: testWrongPasswordRaises
    # --------------------------------------------------------
    def testWrongPasswordRaises(self) -> None:
        crypto = VaultCrypto()
        crypto.unlock("right-password")
        token = crypto.encrypt(b"secret")

        other = VaultCrypto(salt=crypto.salt)
        other.unlock("wrong-password")
        with pytest.raises(ValueError):
            other.decrypt(token)

    # --------------------------------------------------------
    # Method: testLockedEncryptFails
    # --------------------------------------------------------
    def testLockedEncryptFails(self) -> None:
        crypto = VaultCrypto()
        with pytest.raises(RuntimeError):
            crypto.encrypt(b"nope")

    # --------------------------------------------------------
    # Method: testSaltHexRoundTrip
    # --------------------------------------------------------
    def testSaltHexRoundTrip(self) -> None:
        crypto = VaultCrypto()
        restored = VaultCrypto.fromSaltHex(crypto.saltHex())
        assert restored.salt == crypto.salt


# ------------------------------------------------------------
# Tests: VaultStore
# ------------------------------------------------------------
class TestVaultStore:
    # --------------------------------------------------------
    # Method: testCreateUnlockAndPersistProjects
    # --------------------------------------------------------
    def testCreateUnlockAndPersistProjects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault.enc"
            store = VaultStore(vault_path=vault_path)
            store.createVault("master-secret")
            store.addProject(
                ProjectConfig(
                    id="p1",
                    name="Demo",
                    path="C:/projects/demo",
                    remote_url="https://github.com/ex/demo.git",
                    username="alice",
                    email="alice@example.com",
                    pat="ghp_test_token",
                    default_branch="main",
                )
            )

            assert vault_path.is_file()
            # Envelope should not contain plaintext PAT
            raw = vault_path.read_text(encoding="utf-8")
            assert "ghp_test_token" not in raw
            envelope = json.loads(raw)
            assert "salt" in envelope and "payload" in envelope

            store.lock()
            store2 = VaultStore(vault_path=vault_path)
            assert store2.unlockVault("master-secret") is True
            assert len(store2.projects) == 1
            assert store2.projects[0].pat == "ghp_test_token"
            assert store2.projects[0].name == "Demo"

    # --------------------------------------------------------
    # Method: testWrongMasterPassword
    # --------------------------------------------------------
    def testWrongMasterPassword(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault.enc"
            store = VaultStore(vault_path=vault_path)
            store.createVault("correct")
            store.lock()

            store2 = VaultStore(vault_path=vault_path)
            assert store2.unlockVault("incorrect") is False

    # --------------------------------------------------------
    # Method: testEmptyVaultRaisesDamaged
    # --------------------------------------------------------
    def testEmptyVaultRaisesDamaged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault.enc"
            vault_path.write_text("", encoding="utf-8")
            store = VaultStore(vault_path=vault_path)
            with pytest.raises(VaultDamagedError) as exc_info:
                store.unlockVault("anything-long")
            assert VAULT_DAMAGED_MESSAGE in str(exc_info.value)

    # --------------------------------------------------------
    # Method: testCorruptJsonRaisesDamaged
    # --------------------------------------------------------
    def testCorruptJsonRaisesDamaged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault.enc"
            vault_path.write_text("{not-json", encoding="utf-8")
            store = VaultStore(vault_path=vault_path)
            with pytest.raises(VaultDamagedError):
                store.unlockVault("anything-long")

    # --------------------------------------------------------
    # Method: testAtomicSaveKeepsPreviousOnTmpOnly
    # Purpose: Writing only the tmp file must not wipe vault.enc.
    # --------------------------------------------------------
    def testAtomicSaveKeepsPreviousOnTmpOnly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault.enc"
            store = VaultStore(vault_path=vault_path)
            store.createVault("master-secret")
            store.addProject(
                ProjectConfig(
                    id="p1",
                    name="Demo",
                    path="C:/projects/demo",
                    pat="token",
                )
            )
            before = vault_path.read_text(encoding="utf-8")
            assert before.strip()

            # Simulate crash after tmp write but before replace.
            tmp_path = store.tmpPath()
            tmp_path.write_text("", encoding="utf-8")
            assert vault_path.read_text(encoding="utf-8") == before

            store.lock()
            store2 = VaultStore(vault_path=vault_path)
            assert store2.unlockVault("master-secret") is True
            assert store2.projects[0].name == "Demo"

    # --------------------------------------------------------
    # Method: testSaveCreatesBackupAndRestore
    # --------------------------------------------------------
    def testSaveCreatesBackupAndRestore(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault.enc"
            store = VaultStore(vault_path=vault_path)
            store.createVault("master-secret")
            store.addProject(
                ProjectConfig(id="p1", name="First", path="C:/a", pat="t1")
            )
            assert store.backupExists() is True

            store.addProject(
                ProjectConfig(id="p2", name="Second", path="C:/b", pat="t2")
            )
            assert len(store.projects) == 2

            # Wipe vault as if a crash truncated it.
            vault_path.write_text("", encoding="utf-8")
            store.lock()

            store2 = VaultStore(vault_path=vault_path)
            with pytest.raises(VaultDamagedError):
                store2.unlockVault("master-secret")

            assert store2.restoreBackup() is True
            assert store2.unlockVault("master-secret") is True
            # Backup from before the last save still has the first project.
            assert len(store2.projects) >= 1
            assert store2.projects[0].name == "First"
