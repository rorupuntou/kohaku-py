"""Cryptographic primitives for EDW blinded encrypted datastore.

Follows the EDW specification:
- Argon2id: 64 MiB, 3 passes, 1 lane for password wrapping.
- Random 32-byte root data key.
- Per-record HKDF-SHA256 for blinded storage key and encryption key.
- ChaCha20-Poly1305 AEAD with logical key as associated data.
"""

from __future__ import annotations

import os
from typing import Tuple

from argon2.exceptions import VerifyMismatchError
from argon2.low_level import Type, hash_secret_raw
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


class InvalidPasswordError(Exception):
    """Raised when password verification or root key unwrapping fails."""
    pass


class BlindedCipher:
    """Handles password wrapping and per-record blinded AEAD encryption."""

    ARGON2_TIME_COST = 3
    ARGON2_MEMORY_COST = 65536  # 64 MiB in KiB
    ARGON2_PARALLELISM = 1
    ARGON2_HASH_LEN = 32

    def __init__(self, root_data_key: bytes):
        if len(root_data_key) != 32:
            raise ValueError("root_data_key must be exactly 32 bytes")
        self._root_data_key = root_data_key

    @property
    def root_data_key(self) -> bytes:
        return self._root_data_key

    @classmethod
    def derive_password_key(cls, password: str | bytes, salt: bytes) -> bytes:
        """Derive 32-byte key from password using Argon2id."""
        pw_bytes = password.encode("utf-8") if isinstance(password, str) else password
        return hash_secret_raw(
            secret=pw_bytes,
            salt=salt,
            time_cost=cls.ARGON2_TIME_COST,
            memory_cost=cls.ARGON2_MEMORY_COST,
            parallelism=cls.ARGON2_PARALLELISM,
            hash_len=cls.ARGON2_HASH_LEN,
            type=Type.ID,
        )

    @classmethod
    def create_wrapped_root(cls, password: str | bytes) -> Tuple[bytes, bytes, bytes, BlindedCipher]:
        """Generate a fresh 32-byte root key and wrap it under password slot.

        Returns: (salt, nonce, wrapped_key, BlindedCipher)
        """
        salt = os.urandom(16)
        password_key = cls.derive_password_key(password, salt)
        root_data_key = os.urandom(32)

        nonce = os.urandom(12)
        chacha = ChaCha20Poly1305(password_key)
        wrapped_key = chacha.encrypt(nonce, root_data_key, associated_data=b"edw-root-slot-v1")

        return salt, nonce, wrapped_key, cls(root_data_key)

    @classmethod
    def unwrap_root(
        cls,
        password: str | bytes,
        salt: bytes,
        nonce: bytes,
        wrapped_key: bytes,
    ) -> BlindedCipher:
        """Unwrap root key from password slot. Raises InvalidPasswordError on failure."""
        password_key = cls.derive_password_key(password, salt)
        chacha = ChaCha20Poly1305(password_key)
        try:
            root_data_key = chacha.decrypt(nonce, wrapped_key, associated_data=b"edw-root-slot-v1")
        except InvalidTag:
            raise InvalidPasswordError("Incorrect password or corrupted datastore header")
        return cls(root_data_key)

    def derive_blinded_name(self, logical_key: str | bytes) -> str:
        """Derive blinded record filename using HKDF-SHA256."""
        key_bytes = logical_key.encode("utf-8") if isinstance(logical_key, str) else logical_key
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"name:" + key_bytes,
        )
        return hkdf.derive(self._root_data_key).hex()

    def derive_record_key(self, logical_key: str | bytes) -> bytes:
        """Derive 32-byte record encryption key using HKDF-SHA256."""
        key_bytes = logical_key.encode("utf-8") if isinstance(logical_key, str) else logical_key
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"enc:" + key_bytes,
        )
        return hkdf.derive(self._root_data_key)

    def encrypt_record(self, logical_key: str | bytes, plaintext: bytes) -> bytes:
        """Encrypt record plaintext using ChaCha20-Poly1305 with logical key as associated data.

        Payload format: nonce (12 bytes) || ciphertext (N bytes + 16 bytes tag)
        """
        key_bytes = logical_key.encode("utf-8") if isinstance(logical_key, str) else logical_key
        record_key = self.derive_record_key(key_bytes)
        nonce = os.urandom(12)
        chacha = ChaCha20Poly1305(record_key)
        ciphertext = chacha.encrypt(nonce, plaintext, associated_data=key_bytes)
        return nonce + ciphertext

    def decrypt_record(self, logical_key: str | bytes, payload: bytes) -> bytes:
        """Decrypt record payload. Raises ValueError if authenticating tag or logical key fails."""
        if len(payload) < 28:
            raise ValueError("Payload too short (must contain 12-byte nonce and 16-byte tag)")
        key_bytes = logical_key.encode("utf-8") if isinstance(logical_key, str) else logical_key
        record_key = self.derive_record_key(key_bytes)
        nonce = payload[:12]
        ciphertext = payload[12:]
        chacha = ChaCha20Poly1305(record_key)
        try:
            return chacha.decrypt(nonce, ciphertext, associated_data=key_bytes)
        except InvalidTag:
            raise ValueError(f"Corrupted record or mismatched logical key '{logical_key}'")
