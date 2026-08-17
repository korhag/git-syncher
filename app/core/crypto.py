from __future__ import annotations

import base64
import hashlib
import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


# Default iteration count for PBKDF2 (balanced for desktop UX).
_PBKDF2_ITERATIONS = 390_000
_SALT_BYTES = 16


# ------------------------------------------------------------
# Class: VaultCrypto
# Purpose: Derive a Fernet key from a master password and
#          encrypt / decrypt vault payloads.
# ------------------------------------------------------------
class VaultCrypto:
    # --------------------------------------------------------
    # Method: __init__
    # Purpose: Create a crypto helper; optionally with salt.
    # --------------------------------------------------------
    def __init__(self, salt: Optional[bytes] = None) -> None:
        self.salt = salt if salt is not None else os.urandom(_SALT_BYTES)
        self._fernet: Optional[Fernet] = None

    # --------------------------------------------------------
    # Method: deriveKey
    # Purpose: Derive a Fernet-compatible key from password.
    # Input: password (str) - Master password entered by user.
    # Output: bytes - URL-safe base64-encoded 32-byte key.
    # --------------------------------------------------------
    def deriveKey(self, password: str) -> bytes:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=self.salt,
            iterations=_PBKDF2_ITERATIONS,
        )
        raw_key = kdf.derive(password.encode("utf-8"))
        return base64.urlsafe_b64encode(raw_key)

    # --------------------------------------------------------
    # Method: unlock
    # Purpose: Bind this instance to a password-derived key.
    # Input: password (str) - Master password.
    # Output: None
    # --------------------------------------------------------
    def unlock(self, password: str) -> None:
        key = self.deriveKey(password)
        self._fernet = Fernet(key)

    # --------------------------------------------------------
    # Method: isUnlocked
    # Purpose: Whether a key has been derived and stored.
    # --------------------------------------------------------
    def isUnlocked(self) -> bool:
        return self._fernet is not None

    # --------------------------------------------------------
    # Method: lock
    # Purpose: Clear the in-memory Fernet key.
    # --------------------------------------------------------
    def lock(self) -> None:
        self._fernet = None

    # --------------------------------------------------------
    # Method: encrypt
    # Purpose: Encrypt plaintext bytes with the unlocked key.
    # Input: plaintext (bytes)
    # Output: bytes - Fernet token
    # --------------------------------------------------------
    def encrypt(self, plaintext: bytes) -> bytes:
        if self._fernet is None:
            raise RuntimeError("Vault is locked. Call unlock() first.")
        return self._fernet.encrypt(plaintext)

    # --------------------------------------------------------
    # Method: decrypt
    # Purpose: Decrypt a Fernet token; raises on wrong password.
    # Input: token (bytes)
    # Output: bytes - plaintext
    # --------------------------------------------------------
    def decrypt(self, token: bytes) -> bytes:
        if self._fernet is None:
            raise RuntimeError("Vault is locked. Call unlock() first.")
        try:
            return self._fernet.decrypt(token)
        except InvalidToken as exc:
            raise ValueError("Wrong master password or corrupted vault.") from exc

    # --------------------------------------------------------
    # Method: saltHex
    # Purpose: Hex-encoded salt for persistence alongside vault.
    # --------------------------------------------------------
    def saltHex(self) -> str:
        return self.salt.hex()

    # --------------------------------------------------------
    # Method: fromSaltHex
    # Purpose: Reconstruct VaultCrypto with a known salt.
    # --------------------------------------------------------
    @classmethod
    def fromSaltHex(cls, salt_hex: str) -> "VaultCrypto":
        return cls(salt=bytes.fromhex(salt_hex))

    # --------------------------------------------------------
    # Method: passwordFingerprint
    # Purpose: Non-reversible check value stored to verify unlock
    #          without decrypting the whole vault first.
    # --------------------------------------------------------
    @staticmethod
    def passwordFingerprint(password: str, salt: bytes) -> str:
        digest = hashlib.sha256(salt + password.encode("utf-8")).hexdigest()
        return digest
