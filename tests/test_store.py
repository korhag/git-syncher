from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from app.core.crypto import VaultCrypto
from app.core.store import VAULT_VERSION, VaultStore
from app.models.account import VaultAccount
from app.models.project import ProjectConfig


# ------------------------------------------------------------
# Tests: VaultStore uniqueness (path + default branch)
# ------------------------------------------------------------
class TestVaultStoreUniqueness:
    # --------------------------------------------------------
    # Method: testAddDuplicateRejected
    # --------------------------------------------------------
    def testAddDuplicateRejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "repo"
            folder.mkdir()
            vault_path = Path(tmp) / "vault.enc"
            store = VaultStore(vault_path=vault_path)
            store.createVault("master-secret")
            store.addProject(
                ProjectConfig(
                    id="p1",
                    name="One",
                    path=str(folder),
                    default_branch="master",
                )
            )
            with pytest.raises(ValueError, match="already tracked for branch master"):
                store.addProject(
                    ProjectConfig(
                        id="p2",
                        name="Two",
                        path=str(folder),
                        default_branch="master",
                    )
                )
            assert len(store.projects) == 1

    # --------------------------------------------------------
    # Method: testSamePathDifferentBranchAllowed
    # --------------------------------------------------------
    def testSamePathDifferentBranchAllowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "repo"
            folder.mkdir()
            vault_path = Path(tmp) / "vault.enc"
            store = VaultStore(vault_path=vault_path)
            store.createVault("master-secret")
            store.addProject(
                ProjectConfig(
                    id="p1",
                    name="Master",
                    path=str(folder),
                    default_branch="master",
                )
            )
            store.addProject(
                ProjectConfig(
                    id="p2",
                    name="Main",
                    path=str(folder),
                    default_branch="main",
                )
            )
            assert len(store.projects) == 2

    # --------------------------------------------------------
    # Method: testUpdateToCollisionRejected
    # --------------------------------------------------------
    def testUpdateToCollisionRejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder_a = Path(tmp) / "a"
            folder_b = Path(tmp) / "b"
            folder_a.mkdir()
            folder_b.mkdir()
            vault_path = Path(tmp) / "vault.enc"
            store = VaultStore(vault_path=vault_path)
            store.createVault("master-secret")
            store.addProject(
                ProjectConfig(
                    id="p1",
                    name="A",
                    path=str(folder_a),
                    default_branch="main",
                )
            )
            store.addProject(
                ProjectConfig(
                    id="p2",
                    name="B",
                    path=str(folder_b),
                    default_branch="main",
                )
            )
            collision = ProjectConfig(
                id="p2",
                name="B",
                path=str(folder_a),
                default_branch="main",
            )
            with pytest.raises(ValueError, match="already tracked"):
                store.updateProject(collision)
            kept = store.getProject("p2")
            assert kept is not None
            assert VaultStore.normalizePath(kept.path) == VaultStore.normalizePath(
                str(folder_b)
            )

    # --------------------------------------------------------
    # Method: testCollapseDuplicateProjects
    # --------------------------------------------------------
    def testCollapseDuplicateProjects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "repo"
            folder.mkdir()
            vault_path = Path(tmp) / "vault.enc"
            store = VaultStore(vault_path=vault_path)
            store.createVault("master-secret")
            # Bypass uniqueness to seed duplicates (legacy vault).
            store.projects = [
                ProjectConfig(
                    id="keep",
                    name="First",
                    path=str(folder),
                    default_branch="master",
                ),
                ProjectConfig(
                    id="drop1",
                    name="Second",
                    path=str(folder),
                    default_branch="master",
                ),
                ProjectConfig(
                    id="drop2",
                    name="Third",
                    path=str(folder),
                    default_branch="master",
                ),
            ]
            store.save()
            removed = store.collapseDuplicateProjects()
            assert removed == 2
            assert len(store.projects) == 1
            assert store.projects[0].id == "keep"
            # Second call is a no-op.
            assert store.collapseDuplicateProjects() == 0


# ------------------------------------------------------------
# Tests: VaultStore saved Git accounts
# ------------------------------------------------------------
class TestVaultAccounts:
    # --------------------------------------------------------
    # Method: testAccountCrudRoundTrip
    # --------------------------------------------------------
    def testAccountCrudRoundTrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault.enc"
            store = VaultStore(vault_path=vault_path)
            store.createVault("master-secret")
            account = store.addAccount(
                VaultAccount(
                    id="a1",
                    label="Work",
                    username="alice",
                    email="alice@work.example",
                )
            )
            assert account.id == "a1"
            assert len(store.accounts) == 1

            store.lock()
            store2 = VaultStore(vault_path=vault_path)
            assert store2.unlockVault("master-secret") is True
            assert len(store2.accounts) == 1
            assert store2.accounts[0].label == "Work"

            updated = VaultAccount(
                id="a1",
                label="Work GitHub",
                username="alice",
                email="alice@work.example",
            )
            store2.updateAccount(updated)
            assert store2.accounts[0].label == "Work GitHub"

            store2.removeAccount("a1")
            assert store2.accounts == []

    # --------------------------------------------------------
    # Method: testDuplicateAccountLabelRejected
    # --------------------------------------------------------
    def testDuplicateAccountLabelRejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault.enc"
            store = VaultStore(vault_path=vault_path)
            store.createVault("master-secret")
            store.addAccount(
                VaultAccount(
                    id="a1",
                    label="Work",
                    username="alice",
                    email="alice@example.com",
                )
            )
            with pytest.raises(ValueError, match="already exists"):
                store.addAccount(
                    VaultAccount(
                        id="a2",
                        label=" work ",
                        username="bob",
                        email="bob@example.com",
                    )
                )

    # --------------------------------------------------------
    # Method: testRemoveAccountDoesNotAffectProjects
    # --------------------------------------------------------
    def testRemoveAccountDoesNotAffectProjects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "repo"
            folder.mkdir()
            vault_path = Path(tmp) / "vault.enc"
            store = VaultStore(vault_path=vault_path)
            store.createVault("master-secret")
            store.addAccount(
                VaultAccount(
                    id="a1",
                    label="Work",
                    username="alice",
                    email="alice@example.com",
                )
            )
            store.addProject(
                ProjectConfig(
                    id="p1",
                    name="Demo",
                    path=str(folder),
                    username="alice",
                    email="alice@example.com",
                )
            )
            store.removeAccount("a1")
            project = store.getProject("p1")
            assert project is not None
            assert project.username == "alice"
            assert project.email == "alice@example.com"

    # --------------------------------------------------------
    # Method: testV1VaultUnlockMigratesToV2OnSave
    # --------------------------------------------------------
    def testV1VaultUnlockMigratesToV2OnSave(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault.enc"
            password = "master-secret"
            crypto = VaultCrypto()
            crypto.unlock(password)
            payload = {
                "version": 1,
                "projects": [
                    ProjectConfig(
                        id="p1",
                        name="Demo",
                        path="C:/projects/demo",
                        username="alice",
                        email="alice@example.com",
                    ).toDict()
                ],
            }
            plaintext = json.dumps(payload, indent=2).encode("utf-8")
            token = crypto.encrypt(plaintext)
            envelope = {
                "salt": crypto.saltHex(),
                "fingerprint": VaultCrypto.passwordFingerprint(password, crypto.salt),
                "payload": token.hex(),
            }
            vault_path.write_text(json.dumps(envelope, indent=2), encoding="utf-8")

            store = VaultStore(vault_path=vault_path)
            assert store.unlockVault(password) is True
            assert store.accounts == []
            assert len(store.projects) == 1

            store.addAccount(
                VaultAccount(
                    id="a1",
                    label="Work",
                    username="alice",
                    email="alice@example.com",
                )
            )

            store.lock()
            store2 = VaultStore(vault_path=vault_path)
            assert store2.unlockVault(password) is True
            assert len(store2.accounts) == 1

            raw = vault_path.read_text(encoding="utf-8")
            inner = json.loads(raw)
            crypto2 = VaultCrypto.fromSaltHex(inner["salt"])
            crypto2.unlock(password)
            data = json.loads(crypto2.decrypt(bytes.fromhex(inner["payload"])))
            assert data["version"] == VAULT_VERSION
            assert "accounts" in data
            assert len(data["accounts"]) == 1
