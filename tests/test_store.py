from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.core.store import VaultStore
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
