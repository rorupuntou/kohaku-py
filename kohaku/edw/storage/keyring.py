"""Keyring and profile derivation management.

Derivation paths according to EDW specs:
- Address { index }:      m/44'/60'/x'/0/i
- Stealth { scheme }:     m/44'/60'/x'/5564'/scheme'/{0,1} (spending and viewing)
- TornadoCash:            m/44'/60'/x'/29795'/0/deposit (nullifier and secret)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from eth_account import Account

from kohaku.edw.storage.database import EncryptedDatabase
from kohaku.stealth import StealthKeypair, derive_stealth_keypair
from kohaku.tornado.keychain import TornadoKeychain
from kohaku.tornado.note import TornadoNote

Account.enable_unaudited_hdwallet_features()


@dataclass
class ProfileRecord:
    mnemonic_index: int
    profile_index: int
    name: str


class KeyringManager:
    """Manages stored mnemonic phrases, profiles, and address vaults."""

    def __init__(self, db: EncryptedDatabase):
        self.db = db

    def add_mnemonic(self, mnemonic: str) -> int:
        """Store recovery phrase under a fresh index. Returns mnemonic index."""
        mnemonics: List[int] = self.db.get_json("keyring", "mnemonics", default=[])
        next_idx = len(mnemonics)
        self.db.set("keyring", f"mnemonic:{next_idx}", mnemonic.strip().encode("utf-8"))
        mnemonics.append(next_idx)
        self.db.set_json("keyring", "mnemonics", mnemonics)
        return next_idx

    def get_mnemonic(self, mnemonic_index: int) -> str:
        data = self.db.get("keyring", f"mnemonic:{mnemonic_index}")
        if data is None:
            raise KeyError(f"Mnemonic index {mnemonic_index} not found")
        return data.decode("utf-8")

    def create_profile(self, name: str, mnemonic_index: int = 0, profile_index: int = 0) -> ProfileRecord:
        """Create and register a profile record."""
        profiles: List[dict] = self.db.get_json("profiles", "index", default=[])
        # Check if already exists
        for p in profiles:
            if p["m"] == mnemonic_index and p["x"] == profile_index:
                return ProfileRecord(p["m"], p["x"], p["name"])

        new_entry = {"m": mnemonic_index, "x": profile_index, "name": name}
        profiles.append(new_entry)
        self.db.set_json("profiles", "index", profiles)

        # Initialize profile pointer and empty vaults list
        scope = f"profile:{mnemonic_index}:{profile_index}"
        self.db.set_json(scope, "pointer", {"m": mnemonic_index, "x": profile_index})
        self.db.set_json(scope, "vaults", [])
        self.db.set_json(scope, "fresh_cursor", 0)
        return ProfileRecord(mnemonic_index, profile_index, name)

    def list_profiles(self) -> List[ProfileRecord]:
        raw = self.db.get_json("profiles", "index", default=[])
        return [ProfileRecord(r["m"], r["x"], r["name"]) for r in raw]

    def derive_address(self, mnemonic_index: int, profile_index: int, address_index: int) -> str:
        """Derive standard EOA address: m/44'/60'/x'/0/i."""
        phrase = self.get_mnemonic(mnemonic_index)
        path = f"m/44'/60'/{profile_index}'/0/{address_index}"
        acct = Account.from_mnemonic(phrase, account_path=path)
        return acct.address

    def get_next_fresh_address(
        self,
        mnemonic_index: int,
        profile_index: int,
        peek: bool = False,
    ) -> str:
        """Get the next fresh unlinked address for this profile.

        If peek=False, advances and stores the cursor in the encrypted datastore.
        """
        scope = f"profile:{mnemonic_index}:{profile_index}"
        cursor: int = self.db.get_json(scope, "fresh_cursor", default=0)
        address = self.derive_address(mnemonic_index, profile_index, cursor)
        if not peek:
            self.db.set_json(scope, "fresh_cursor", cursor + 1)
        return address

    def derive_stealth_keys(
        self,
        mnemonic_index: int,
        profile_index: int,
        chain_id: int = 1,
    ) -> StealthKeypair:
        """Derive ERC-5564 stealth meta-address for this profile."""
        phrase = self.get_mnemonic(mnemonic_index)
        return derive_stealth_keypair(phrase, profile=profile_index, chain_id=chain_id)

    def get_tornado_keychain(
        self,
        mnemonic_index: int,
        profile_index: int,
    ) -> TornadoKeychain:
        """Derive Tornado keychain for generating notes."""
        phrase = self.get_mnemonic(mnemonic_index)
        return TornadoKeychain.from_mnemonic(phrase, profile_index=profile_index)
