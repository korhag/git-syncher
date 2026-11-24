from __future__ import annotations

from app.models.account import VaultAccount, findAccountByKey


# ------------------------------------------------------------
# Tests: VaultAccount identity helper
# ------------------------------------------------------------
class TestAccountIdentity:
    # --------------------------------------------------------
    # Method: testIdentityReturnsStoredFields
    # --------------------------------------------------------
    def testIdentityReturnsStoredFields(self) -> None:
        account = VaultAccount(
            id="acc-1",
            label="Work",
            username="korhag",
            email="me@example.com",
        )
        assert account.identity() == ("korhag", "me@example.com")

    # --------------------------------------------------------
    # Method: testFindByIdAndLabel
    # --------------------------------------------------------
    def testFindByIdAndLabel(self) -> None:
        account = VaultAccount(
            id="acc-1",
            label="Work",
            username="korhag",
            email="me@example.com",
        )
        accounts = [account]
        assert findAccountByKey(accounts, "acc-1") is account
        assert findAccountByKey(accounts, "Work (korhag)") is account
        assert findAccountByKey(accounts, "Work") is account
        assert findAccountByKey(accounts, "") is None
        assert findAccountByKey(accounts, "other") is None
