"""Privacy Pools registry and metadata."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PrivacyPool:
    id: str
    chain_id: int
    asset: str
    contract_address: str
    decimals: int = 18

    @property
    def is_native(self) -> bool:
        return self.asset.upper() == "ETH"


MAINNET_PRIVACY_POOLS: dict[str, PrivacyPool] = {
    "privacy-pools-1-eth": PrivacyPool(
        id="privacy-pools-1-eth",
        chain_id=1,
        asset="ETH",
        contract_address="0xf241d57c6debae225c0f2e6ea1529373c9a9c9fb",
        decimals=18,
    ),
    "privacy-pools-1-dai": PrivacyPool(
        id="privacy-pools-1-dai",
        chain_id=1,
        asset="DAI",
        contract_address="0x1c31c03b8cb2ee674d0f11de77135536db828257",
        decimals=18,
    ),
    "privacy-pools-1-usdc": PrivacyPool(
        id="privacy-pools-1-usdc",
        chain_id=1,
        asset="USDC",
        contract_address="0xb419c2867ab3cbc78921660cb95150d95a94ce86",
        decimals=6,
    ),
    "privacy-pools-1-usdt": PrivacyPool(
        id="privacy-pools-1-usdt",
        chain_id=1,
        asset="USDT",
        contract_address="0xe859c0bd25f260baee534fb52e307d3b64d24572",
        decimals=6,
    ),
    "privacy-pools-1-wbtc": PrivacyPool(
        id="privacy-pools-1-wbtc",
        chain_id=1,
        asset="WBTC",
        contract_address="0xf973f4b180a568157cd7a0e6006449139e6bfc32",
        decimals=8,
    ),
    "privacy-pools-1-wsteth": PrivacyPool(
        id="privacy-pools-1-wsteth",
        chain_id=1,
        asset="wstETH",
        contract_address="0x1a604e9dfa0efdc7ffda378af16cb81243b61633",
        decimals=18,
    ),
    "privacy-pools-1-bold": PrivacyPool(
        id="privacy-pools-1-bold",
        chain_id=1,
        asset="BOLD",
        contract_address="0xb4b5fd38fd4788071d7287e3cb52948e0d10b23e",
        decimals=18,
    ),
    "privacy-pools-1-susds": PrivacyPool(
        id="privacy-pools-1-susds",
        chain_id=1,
        asset="sUSDS",
        contract_address="0xbbda2173cdfea1c3bd7f2908798f1265301d750c",
        decimals=18,
    ),
    "privacy-pools-1-usds": PrivacyPool(
        id="privacy-pools-1-usds",
        chain_id=1,
        asset="USDS",
        contract_address="0x05e4dbd71b56861eed2aaa12d00a797f04b5d3c0",
        decimals=18,
    ),
}

ALL_PRIVACY_POOLS: dict[str, PrivacyPool] = dict(MAINNET_PRIVACY_POOLS)


def get_privacy_pool(pool_id: str) -> PrivacyPool:
    if pool_id not in ALL_PRIVACY_POOLS:
        raise KeyError(f"Unknown Privacy Pool '{pool_id}'. Available: {list(ALL_PRIVACY_POOLS.keys())}")
    return ALL_PRIVACY_POOLS[pool_id]
