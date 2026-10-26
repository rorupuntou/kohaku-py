from pathlib import Path
import pytest

from kohaku.edw.storage.cipher import BlindedCipher, InvalidPasswordError
from kohaku.edw.storage.database import EncryptedDatabase
from kohaku.edw.storage.keyring import KeyringManager


def test_blinded_cipher_lifecycle():
    password = "super-secret-password-123"
    salt, nonce, wrapped, cipher = BlindedCipher.create_wrapped_root(password)

    # Unwrap root key
    opened_cipher = BlindedCipher.unwrap_root(password, salt, nonce, wrapped)
    assert opened_cipher.root_data_key == cipher.root_data_key

    # Wrong password fails
    with pytest.raises(InvalidPasswordError):
        BlindedCipher.unwrap_root("wrong-password", salt, nonce, wrapped)

    # Blinded names are deterministic and unlinkable
    name1 = cipher.derive_blinded_name("profile:0:0/vaults")
    name2 = cipher.derive_blinded_name("profile:0:0/vaults")
    name3 = cipher.derive_blinded_name("keyring/mnemonic:0")
    assert name1 == name2
    assert name1 != name3
    assert len(name1) == 64  # 32 bytes in hex

    # AEAD record encryption
    payload = b"Top secret private key or mnemonic"
    enc = cipher.encrypt_record("keyring/mnemonic:0", payload)
    dec = cipher.decrypt_record("keyring/mnemonic:0", enc)
    assert dec == payload

    # Mismatched associated data fails
    with pytest.raises(ValueError):
        cipher.decrypt_record("keyring/mnemonic:1", enc)


def test_encrypted_database_disk_zero_leakage(tmp_path: Path):
    db_dir = tmp_path / "edw_datastore"
    password = "wallet-master-pass"

    # 1. Initialize DB
    db = EncryptedDatabase.initialize(db_dir, password)
    secret_text = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
    db.set("keyring", "mnemonic:0", secret_text.encode("utf-8"))
    db.set_json("profiles", "index", [{"m": 0, "x": 0, "name": "default"}])

    # 2. Inspect raw files on disk: verify zero plaintext leakage and strict 0700/0600 permissions
    import stat

    assert stat.S_IMODE(db_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE((db_dir / "header.json").stat().st_mode) == 0o600
    raw_files = list(db_dir.glob("*.bin"))
    assert len(raw_files) == 2  # exactly two blinded records
    for rf in raw_files:
        assert stat.S_IMODE(rf.stat().st_mode) == 0o600
        content = rf.read_bytes()
        assert b"abandon" not in content
        assert b"default" not in content
        assert b"keyring" not in content

    # 3. Lock DB
    db.lock()
    with pytest.raises(RuntimeError):
        db.get("keyring", "mnemonic:0")

    # 4. Reopen with correct password
    reopened = EncryptedDatabase.open(db_dir, password)
    val = reopened.get("keyring", "mnemonic:0")
    assert val is not None
    assert val.decode("utf-8") == secret_text
    profiles = reopened.get_json("profiles", "index")
    assert profiles[0]["name"] == "default"

    # 5. Wrong password fails
    with pytest.raises(InvalidPasswordError):
        EncryptedDatabase.open(db_dir, "incorrect-pass")

    # 6. Change password without re-encrypting records
    reopened.change_password("new-wallet-pass-2026")
    reopened.lock()

    # Reopen with new password succeeds
    new_db = EncryptedDatabase.open(db_dir, "new-wallet-pass-2026")
    assert new_db.get("keyring", "mnemonic:0").decode("utf-8") == secret_text

    # Old password no longer works
    with pytest.raises(InvalidPasswordError):
        EncryptedDatabase.open(db_dir, password)


def test_keyring_manager_and_fresh_address_rotation(tmp_path: Path):
    db = EncryptedDatabase.initialize(tmp_path / "keyring_store", "pass123")
    km = KeyringManager(db)

    phrase = "test test test test test test test test test test test junk"
    m_idx = km.add_mnemonic(phrase)
    assert m_idx == 0

    profile = km.create_profile("cypherpunk", mnemonic_index=0, profile_index=0)
    assert profile.name == "cypherpunk"

    # Addresses derivation along m/44'/60'/0'/0/i
    addr0 = km.derive_address(0, 0, 0)
    addr1 = km.derive_address(0, 0, 1)
    assert addr0 != addr1
    assert addr0.startswith("0x") and len(addr0) == 42

    # Fresh address rotation
    # Peek does not advance cursor
    peek_addr = km.get_next_fresh_address(0, 0, peek=True)
    assert peek_addr == addr0

    # Normal fetch advances cursor
    fresh0 = km.get_next_fresh_address(0, 0, peek=False)
    assert fresh0 == addr0

    fresh1 = km.get_next_fresh_address(0, 0, peek=False)
    assert fresh1 == addr1

    fresh2 = km.get_next_fresh_address(0, 0, peek=False)
    assert fresh2 == km.derive_address(0, 0, 2)

    # Stealth keys derivation
    stealth = km.derive_stealth_keys(0, 0, chain_id=1)
    assert stealth.stealth_meta_address_uri.startswith("st:eth:0x")

    # Tornado keychain derivation
    kc = km.get_tornado_keychain(0, 0)
    note0 = kc.derive_note("tornado-cash-1-eth-0.1", nonce=0)
    assert note0.amount == "0.1"
