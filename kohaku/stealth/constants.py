"""ERC-5564 and ERC-6538 Stealth Address constants."""

from __future__ import annotations

# BIP-44-ish derivation paths matching Kohaku / Scopelift specifications
STEALTH_SPENDING_PATH = "m/44'/60'/0'/5564'/1'/0'"
STEALTH_VIEWING_PATH = "m/44'/60'/0'/5564'/1'/1'"

# ScopeLift canonical deployments
ERC5564_ANNOUNCER = "0x55649E01B5Df198D18D95b5cc5051630cfD45564"
ERC6538_REGISTRY = "0x6538E6bf4B0eBd30A8Ea093027Ac2422ce5d6538"

# Chain short prefixes for st:<prefix>:<meta_address>
CHAIN_SHORT_NAMES: dict[int, str] = {
    1: "eth",
    11155111: "sep",
    10: "oeth",
    8453: "base",
    42161: "arb1",
    100: "gno",
}


def get_chain_short_name(chain_id: int) -> str:
    return CHAIN_SHORT_NAMES.get(chain_id, f"chain{chain_id}")
