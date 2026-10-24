"""Stealth keypair derivation and ERC-5564 Scheme 1 address generation."""

from __future__ import annotations

from dataclasses import dataclass
import secrets
from typing import Any

from eth_account import Account
from eth_hash.auto import keccak
from eth_keys import keys
from py_ecc.secp256k1 import secp256k1

from kohaku.stealth.constants import (
    STEALTH_SPENDING_PATH,
    STEALTH_VIEWING_PATH,
    get_chain_short_name,
)

Account.enable_unaudited_hdwallet_features()


@dataclass(frozen=True)
class StealthKeypair:
    """Fixed spending and viewing keypair derived from a mnemonic seed phrase."""

    spending_private_key: str
    viewing_private_key: str
    spending_public_key: str
    viewing_public_key: str
    stealth_meta_address: str
    stealth_meta_address_uri: str
    chain_id: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "spending_public_key": self.spending_public_key,
            "viewing_public_key": self.viewing_public_key,
            "stealth_meta_address": self.stealth_meta_address,
            "stealth_meta_address_uri": self.stealth_meta_address_uri,
            "chain_id": self.chain_id,
        }


def _compress_point(point: tuple[int, int]) -> bytes:
    x, y = point
    prefix = b"\x02" if y % 2 == 0 else b"\x03"
    return prefix + x.to_bytes(32, "big")


def _decompress_point(pub_bytes: bytes) -> tuple[int, int]:
    """Decompresses 33-byte secp256k1 point."""
    if len(pub_bytes) != 33:
        raise ValueError(f"Compressed pubkey must be 33 bytes, got {len(pub_bytes)}")
    prefix = pub_bytes[0]
    x = int.from_bytes(pub_bytes[1:33], "big")

    # y^2 = x^3 + 7 mod P
    y_sq = (pow(x, 3, secp256k1.P) + 7) % secp256k1.P
    # Tonelli-Shanks for P = 3 mod 4: y = y_sq^((P+1)/4)
    y = pow(y_sq, (secp256k1.P + 1) // 4, secp256k1.P)

    if (prefix == 2 and y % 2 != 0) or (prefix == 3 and y % 2 == 0):
        y = secp256k1.P - y

    return (x, y)


def _point_to_address(point: tuple[int, int]) -> str:
    x, y = point
    uncompressed = x.to_bytes(32, "big") + y.to_bytes(32, "big")
    return "0x" + keccak(uncompressed)[12:].hex()


def derive_stealth_keypair(mnemonic: str, chain_id: int = 1, profile: int = 0) -> StealthKeypair:
    """Derives the fixed ERC-5564 stealth spending and viewing keypairs

    from a BIP-39 mnemonic seed phrase at profile index.
    """
    spend_path = f"m/44'/60'/{profile}'/5564'/1'/0'"
    view_path = f"m/44'/60'/{profile}'/5564'/1'/1'"
    spend_acc = Account.from_mnemonic(mnemonic, account_path=spend_path)
    view_acc = Account.from_mnemonic(mnemonic, account_path=view_path)

    spend_priv_hex = spend_acc.key.hex()
    view_priv_hex = view_acc.key.hex()

    spend_pub = keys.PrivateKey(spend_acc.key).public_key.to_compressed_bytes().hex()
    view_pub = keys.PrivateKey(view_acc.key).public_key.to_compressed_bytes().hex()

    meta_address = f"0x{spend_pub}{view_pub}"
    prefix = get_chain_short_name(chain_id)
    uri = f"st:{prefix}:{meta_address}"

    return StealthKeypair(
        spending_private_key=spend_priv_hex,
        viewing_private_key=view_priv_hex,
        spending_public_key=f"0x{spend_pub}",
        viewing_public_key=f"0x{view_pub}",
        stealth_meta_address=meta_address,
        stealth_meta_address_uri=uri,
        chain_id=chain_id,
    )


def generate_stealth_address(stealth_meta_address_or_uri: str) -> dict[str, Any]:
    """Generates a one-time stealth address for a recipient using ERC-5564 Scheme 1 (secp256k1)."""
    meta = stealth_meta_address_or_uri
    if meta.startswith("st:"):
        parts = meta.split(":")
        meta = parts[2]

    clean_hex = meta[2:] if meta.startswith("0x") else meta
    if len(clean_hex) != 132:
        raise ValueError(f"Invalid stealth meta-address length: expected 132 hex chars (66 bytes), got {len(clean_hex)}")

    spend_pub_bytes = bytes.fromhex(clean_hex[:66])
    view_pub_bytes = bytes.fromhex(clean_hex[66:132])

    P_spend = _decompress_point(spend_pub_bytes)
    P_view = _decompress_point(view_pub_bytes)

    # Ephemeral keypair (r, R)
    r_scalar = int.from_bytes(secrets.token_bytes(32), "big") % secp256k1.N
    R_ephemeral = secp256k1.multiply(secp256k1.G, r_scalar)
    R_compressed = _compress_point(R_ephemeral)

    # Shared secret S = r * P_view
    S = secp256k1.multiply(P_view, r_scalar)
    shared_hash = keccak(_compress_point(S))
    view_tag = f"0x{shared_hash[0]:02x}"
    s_scalar = int.from_bytes(shared_hash, "big") % secp256k1.N

    # Stealth pubkey P_stealth = P_spend + s * G
    sG = secp256k1.multiply(secp256k1.G, s_scalar)
    P_stealth = secp256k1.add(P_spend, sG)
    stealth_address = _point_to_address(P_stealth)

    return {
        "stealth_address": stealth_address,
        "ephemeral_public_key": "0x" + R_compressed.hex(),
        "view_tag": view_tag,
        "scheme_id": 1,
    }


def recover_stealth_private_key(
    spending_private_key: str,
    viewing_private_key: str,
    ephemeral_public_key: str,
) -> str:
    """Allows recipient to recover the one-time private key to spend from the stealth address."""
    p_bytes = bytes.fromhex(spending_private_key[2:] if spending_private_key.startswith("0x") else spending_private_key)
    v_bytes = bytes.fromhex(viewing_private_key[2:] if viewing_private_key.startswith("0x") else viewing_private_key)
    r_pub_bytes = bytes.fromhex(ephemeral_public_key[2:] if ephemeral_public_key.startswith("0x") else ephemeral_public_key)

    p_scalar = int.from_bytes(p_bytes, "big") % secp256k1.N
    v_scalar = int.from_bytes(v_bytes, "big") % secp256k1.N

    R_point = _decompress_point(r_pub_bytes)
    S = secp256k1.multiply(R_point, v_scalar)
    shared_hash = keccak(_compress_point(S))
    s_scalar = int.from_bytes(shared_hash, "big") % secp256k1.N

    p_stealth = (p_scalar + s_scalar) % secp256k1.N
    return "0x" + p_stealth.to_bytes(32, "big").hex()
