"""Encrypted database implementation matching EDW layout and specification.

Directory Layout:
<data-dir>/<network>/
  header.json                   # Salt, nonce, and password-wrapped root data key
  <blinded_name_hex>.bin        # Blinded encrypted records
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from kohaku.edw.storage.cipher import BlindedCipher, InvalidPasswordError


class EncryptedDatabase:
    """Zero-knowledge on-disk byte key-value store with blinded filenames."""

    HEADER_FILE = "header.json"

    def __init__(self, directory: Path | str, cipher: BlindedCipher):
        self.directory = Path(directory)
        self.cipher = cipher
        self.is_open = True

    @classmethod
    def initialize(cls, directory: Path | str, password: str | bytes) -> EncryptedDatabase:
        """Create a fresh encrypted datastore in directory with password."""
        dir_path = Path(directory)
        dir_path.mkdir(parents=True, exist_ok=True)
        header_path = dir_path / cls.HEADER_FILE

        if header_path.exists():
            raise FileExistsError(f"Datastore already exists at {dir_path}")

        salt, nonce, wrapped_key, cipher = BlindedCipher.create_wrapped_root(password)
        header_data = {
            "version": 1,
            "salt": salt.hex(),
            "nonce": nonce.hex(),
            "wrapped_key": wrapped_key.hex(),
        }
        header_path.write_text(json.dumps(header_data, indent=2))
        return cls(dir_path, cipher)

    @classmethod
    def open(cls, directory: Path | str, password: str | bytes) -> EncryptedDatabase:
        """Open an existing encrypted datastore with password."""
        dir_path = Path(directory)
        header_path = dir_path / cls.HEADER_FILE

        if not header_path.exists():
            raise FileNotFoundError(f"No datastore found at {dir_path}")

        try:
            header_data = json.loads(header_path.read_text())
            salt = bytes.fromhex(header_data["salt"])
            nonce = bytes.fromhex(header_data["nonce"])
            wrapped_key = bytes.fromhex(header_data["wrapped_key"])
        except Exception as e:
            raise ValueError(f"Invalid or corrupted datastore header: {e}")

        cipher = BlindedCipher.unwrap_root(password, salt, nonce, wrapped_key)
        return cls(dir_path, cipher)

    def change_password(self, new_password: str | bytes) -> None:
        """Rewrites only header.json with new Argon2id salt without re-encrypting records."""
        self._check_open()
        import os
        from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

        new_salt = os.urandom(16)
        pw_key = BlindedCipher.derive_password_key(new_password, new_salt)
        new_nonce = os.urandom(12)
        chacha = ChaCha20Poly1305(pw_key)
        wrapped_key = chacha.encrypt(new_nonce, self.cipher.root_data_key, associated_data=b"edw-root-slot-v1")

        header_data = {
            "version": 1,
            "salt": new_salt.hex(),
            "nonce": new_nonce.hex(),
            "wrapped_key": wrapped_key.hex(),
        }
        (self.directory / self.HEADER_FILE).write_text(json.dumps(header_data, indent=2))

    def _logical_key(self, scope: str, key: str) -> str:
        return f"{scope}:{key}"

    def _record_path(self, logical_key: str) -> Path:
        blinded_name = self.cipher.derive_blinded_name(logical_key)
        return self.directory / f"{blinded_name}.bin"

    def _check_open(self) -> None:
        if not self.is_open:
            raise RuntimeError("Encrypted database is locked / closed")

    def has(self, scope: str, key: str) -> bool:
        self._check_open()
        path = self._record_path(self._logical_key(scope, key))
        return path.exists()

    def get(self, scope: str, key: str) -> bytes | None:
        self._check_open()
        logical_key = self._logical_key(scope, key)
        path = self._record_path(logical_key)
        if not path.exists():
            return None
        payload = path.read_bytes()
        return self.cipher.decrypt_record(logical_key, payload)

    def set(self, scope: str, key: str, value: bytes) -> None:
        self._check_open()
        logical_key = self._logical_key(scope, key)
        path = self._record_path(logical_key)
        payload = self.cipher.encrypt_record(logical_key, value)
        path.write_bytes(payload)

    def delete(self, scope: str, key: str) -> bool:
        self._check_open()
        logical_key = self._logical_key(scope, key)
        path = self._record_path(logical_key)
        if path.exists():
            path.unlink()
            return True
        return False

    def get_json(self, scope: str, key: str, default: Any = None) -> Any:
        data = self.get(scope, key)
        if data is None:
            return default
        return json.loads(data.decode("utf-8"))

    def set_json(self, scope: str, key: str, value: Any) -> None:
        payload = json.dumps(value).encode("utf-8")
        self.set(scope, key, payload)

    def lock(self) -> None:
        """Lock datastore and drop encryption key from active memory."""
        self.is_open = False
        # Overwrite cipher reference
        self.cipher = None  # type: ignore
