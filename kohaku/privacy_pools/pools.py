"""Privacy Pools (0xBow) registry and metadata (Mainnet v1 & v2)."""

from __future__ import annotations

from dataclasses import dataclass

PRIVACY_POOLS_ENTRYPOINT = "0x6818809eefce719e480a7526d76bd3e561526b46"
NATIVE_ASSET_PLACEHOLDER = "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"


@dataclass(frozen=True)
class PrivacyPool:
    id: str
    chain_id: int
    asset: str
    contract_address: str
    decimals: int = 18
    asset_address: str = NATIVE_ASSET_PLACEHOLDER
    deployed_block: int = 22153713

    @property
    def is_native(self) -> bool:
        return self.asset.upper() == "ETH"


# All 14 Mainnet 0xBow Privacy Pools from Saga v2/publish-config.json
MAINNET_PRIVACY_POOLS: dict[str, PrivacyPool] = {
    "privacy-pools-1-eth": PrivacyPool(
        id="privacy-pools-1-eth",
        chain_id=1,
        asset="ETH",
        contract_address="0xf241d57c6debae225c0f2e6ea1529373c9a9c9fb",
        decimals=18,
        asset_address=NATIVE_ASSET_PLACEHOLDER,
        deployed_block=22153714,
    ),
    "privacy-pools-1-usds": PrivacyPool(
        id="privacy-pools-1-usds",
        chain_id=1,
        asset="USDS",
        contract_address="0x05e4dbd71b56861eed2aaa12d00a797f04b5d3c0",
        decimals=18,
        asset_address="0xdc035d45d973e3ec169d2276ddab16f1e407384f",
        deployed_block=22926060,
    ),
    "privacy-pools-1-susds": PrivacyPool(
        id="privacy-pools-1-susds",
        chain_id=1,
        asset="sUSDS",
        contract_address="0xbbda2173cdfea1c3bd7f2908798f1265301d750c",
        decimals=18,
        asset_address="0xa3931d71877c0e7a3148cb7eb4463524fec27fbd",
        deployed_block=22941972,
    ),
    "privacy-pools-1-dai": PrivacyPool(
        id="privacy-pools-1-dai",
        chain_id=1,
        asset="DAI",
        contract_address="0x1c31c03b8cb2ee674d0f11de77135536db828257",
        decimals=18,
        asset_address="0x6b175474e89094c44da98b954eedeac495271d0f",
        deployed_block=22947279,
    ),
    "privacy-pools-1-usdt": PrivacyPool(
        id="privacy-pools-1-usdt",
        chain_id=1,
        asset="USDT",
        contract_address="0xe859c0bd25f260baee534fb52e307d3b64d24572",
        decimals=6,
        asset_address="0xdac17f958d2ee523a2206206994597c13d831ec7",
        deployed_block=22989008,
    ),
    "privacy-pools-1-usdc": PrivacyPool(
        id="privacy-pools-1-usdc",
        chain_id=1,
        asset="USDC",
        contract_address="0xb419c2867ab3cbc78921660cb95150d95a94ce86",
        decimals=6,
        asset_address="0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
        deployed_block=22989008,
    ),
    "privacy-pools-1-wsteth": PrivacyPool(
        id="privacy-pools-1-wsteth",
        chain_id=1,
        asset="wstETH",
        contract_address="0x1a604e9dfa0efdc7ffda378af16cb81243b61633",
        decimals=18,
        asset_address="0x7f39c581f595b53c5cb19bd0b3f8da6c935e2ca0",
        deployed_block=23041559,
    ),
    "privacy-pools-1-wbtc": PrivacyPool(
        id="privacy-pools-1-wbtc",
        chain_id=1,
        asset="WBTC",
        contract_address="0xf973f4b180a568157cd7a0e6006449139e6bfc32",
        decimals=8,
        asset_address="0x2260fac5e5542a773aa44fbcfedf7c193bc2c599",
        deployed_block=23041559,
    ),
    "privacy-pools-1-usde": PrivacyPool(
        id="privacy-pools-1-usde",
        chain_id=1,
        asset="USDe",
        contract_address="0xe6d36b33b00a7c0cb0c2a8d39d07e7db0c526abc",
        decimals=18,
        asset_address="0x4c9edd5852cd905f086c759e8383e09bff1e68b3",
        deployed_block=23097322,
    ),
    "privacy-pools-1-usd1": PrivacyPool(
        id="privacy-pools-1-usd1",
        chain_id=1,
        asset="USD1",
        contract_address="0xc0a8bc0f4f982b4d4f1ffae8f4fccb58c9b29c98",
        decimals=18,
        asset_address="0x8d0d000ee44948fc98c9b98a4fa4921476f08b0d",
        deployed_block=23097322,
    ),
    "privacy-pools-1-frxusd": PrivacyPool(
        id="privacy-pools-1-frxusd",
        chain_id=1,
        asset="frxUSD",
        contract_address="0xc6c769fac7aabeadd31a03fae5ca0ec5b4c50f84",
        decimals=18,
        asset_address="0xcacd6fd266af91b8aed52accc382b4e165586e29",
        deployed_block=23097322,
    ),
    "privacy-pools-1-woeth": PrivacyPool(
        id="privacy-pools-1-woeth",
        chain_id=1,
        asset="wOETH",
        contract_address="0x7d2959bcfb936a84531518e8391ddba844e03ebe",
        decimals=18,
        asset_address="0xdcee70654261af21c44c093c300ed3bb97b78192",
        deployed_block=23241349,
    ),
    "privacy-pools-1-fxusd": PrivacyPool(
        id="privacy-pools-1-fxusd",
        chain_id=1,
        asset="fxUSD",
        contract_address="0xd14f4b36e1d1d98c218db782c49149876042bc56",
        decimals=18,
        asset_address="0x085780639cc2cacd35e474e71f4d000e2405d8f6",
        deployed_block=24018902,
    ),
    "privacy-pools-1-bold": PrivacyPool(
        id="privacy-pools-1-bold",
        chain_id=1,
        asset="BOLD",
        contract_address="0xb4b5fd38fd4788071d7287e3cb52948e0d10b23e",
        decimals=18,
        asset_address="0x6440f144b7e50d6a8439336510312d2f54beb01d",
        deployed_block=24435268,
    ),
}

ALL_PRIVACY_POOLS: dict[str, PrivacyPool] = dict(MAINNET_PRIVACY_POOLS)


def get_privacy_pool(pool_id: str) -> PrivacyPool:
    if pool_id not in ALL_PRIVACY_POOLS:
        raise KeyError(
            f"Unknown Privacy Pool '{pool_id}'. Available: {list(ALL_PRIVACY_POOLS.keys())}"
        )
    return ALL_PRIVACY_POOLS[pool_id]
