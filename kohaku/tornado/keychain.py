"""Deterministic Tornado Cash note derivation from mnemonic or private key via EIP-712."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from eth_account import Account
from eth_hash.auto import keccak
from kohaku.tornado.note import TornadoNote
from kohaku.tornado.pools import ALL_POOLS, MAINNET_POOLS, TornadoPool, get_pool

Account.enable_unaudited_hdwallet_features()

KEYCHAIN_PATH = "m/44'/60'/{profile_index}'/29795'/0/0"
DOMAIN_NAME = "TornadoCash Keychain"
DOMAIN_VERSION = "1"
TORNADO_SALT = keccak(b"tornado")


class TornadoKeychain:
    """Derives deterministic Tornado Cash notes matching the Ethereum Foundation's

    kohaku-tornadocash-keychain specification.
    """

    def __init__(self, private_key: bytes | str):
        if isinstance(private_key, str):
            if private_key.startswith("0x") or private_key.startswith("0X"):
                private_key = private_key[2:]
            self.key = bytes.fromhex(private_key)
        else:
            self.key = private_key

        self.account = Account.from_key(self.key)
        self.address = self.account.address
        self._signatures_cache: dict[tuple[int, int], bytes] = {}

    @classmethod
    def from_mnemonic(cls, mnemonic: str, profile_index: int = 0) -> TornadoKeychain:
        """Derives the Tornado Keychain signing key at m/44'/60'/<profile_index>'/29795'/0/0."""
        path = KEYCHAIN_PATH.format(profile_index=profile_index)
        acc = Account.from_mnemonic(mnemonic.strip(), account_path=path)
        return cls(acc.key)

    def _get_signature_rs(self, chain_id: int, nonce: int) -> bytes:
        cache_key = (chain_id, nonce)
        if cache_key in self._signatures_cache:
            return self._signatures_cache[cache_key]

        domain_data = {
            "name": DOMAIN_NAME,
            "version": DOMAIN_VERSION,
            "chainId": chain_id,
            "salt": TORNADO_SALT,
        }
        message_types = {
            "TornadoCashNote": [
                {"name": "nonce", "type": "uint64"},
            ]
        }
        message_data = {
            "nonce": nonce,
        }

        signed = Account.sign_typed_data(
            self.key,
            domain_data=domain_data,
            message_types=message_types,
            message_data=message_data,
        )

        r_bytes = signed.r.to_bytes(32, "big")
        s_bytes = signed.s.to_bytes(32, "big")
        rs = r_bytes + s_bytes
        self._signatures_cache[cache_key] = rs
        return rs

    def derive_note(self, pool_id_or_pool: str | TornadoPool, nonce: int = 0) -> TornadoNote:
        """Derives a deterministic note for the given pool and nonce."""
        if isinstance(pool_id_or_pool, str):
            pool = get_pool(pool_id_or_pool)
        else:
            pool = pool_id_or_pool

        rs = self._get_signature_rs(pool.chain_id, nonce)

        # Address as raw 20 bytes
        addr_clean = pool.contract_address.lower().replace("0x", "")
        addr_bytes = bytes.fromhex(addr_clean)

        secret = keccak(b"secret" + addr_bytes + rs)[:31]
        nullifier = keccak(b"nullifier" + addr_bytes + rs)[:31]

        return TornadoNote(
            currency=pool.asset,
            amount=pool.amount,
            chain_id=pool.chain_id,
            nullifier=nullifier,
            secret=secret,
        )

    def scan_wallet(
        self,
        pools: list[TornadoPool | str] | None = None,
        max_consecutive_empty: int = 20,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> list[dict[str, Any]]:
        """Scans historical nonces across pools, stopping after `max_consecutive_empty` unused nonces.

        Returns all recovered notes with their on-chain mined and spent status.
        """
        from kohaku.tornado.vault import TornadoVault

        target_pools = [get_pool(p) if isinstance(p, str) else p for p in (pools or list(MAINNET_POOLS.values()))]

        # Pre-sync vaults for all target pools
        vaults = {p.id: TornadoVault(p) for p in target_pools}
        for idx, (p_id, v) in enumerate(vaults.items(), 1):
            if on_progress:
                on_progress(0, 0)
            v.sync()

        recovered: list[dict[str, Any]] = []
        consecutive_empty = 0
        nonce = 0

        while consecutive_empty < max_consecutive_empty:
            found_any = False
            for pool in target_pools:
                vault = vaults[pool.id]
                note = self.derive_note(pool, nonce)
                status = vault.check_note(note)

                if status["mined"]:
                    found_any = True
                    recovered.append({
                        "nonce": nonce,
                        "pool": pool.id,
                        "amount": f"{pool.amount} {pool.asset}",
                        "mined": True,
                        "spent": status["spent"],
                        "spendable": status["spendable"],
                        "leaf_index": status["leaf_index"],
                        "note": note,
                        "note_uri": note.to_note_string(),
                    })

            if found_any:
                consecutive_empty = 0
            else:
                consecutive_empty += 1

            if on_progress:
                on_progress(nonce, consecutive_empty)

            nonce += 1

        return recovered
