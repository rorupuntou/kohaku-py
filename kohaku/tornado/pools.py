"""Tornado Cash pool registry for Ethereum Mainnet and Sepolia."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TornadoPool:
    id: str
    asset: str
    amount: str
    amount_wei: int
    chain_id: int
    contract_address: str
    deployed_block: int
    decimals: int = 18


# Ethereum Mainnet (Chain ID 1)
MAINNET_POOLS: dict[str, TornadoPool] = {
    "tornado-cash-1-eth-0.1": TornadoPool(
        id="tornado-cash-1-eth-0.1",
        asset="ETH",
        amount="0.1",
        amount_wei=100_000_000_000_000_000,
        chain_id=1,
        contract_address="0x12D66f87A04A9E220743712CE6d9bB1B5616B8Fc".lower(),
        deployed_block=9116966,
    ),
    "tornado-cash-1-eth-1": TornadoPool(
        id="tornado-cash-1-eth-1",
        asset="ETH",
        amount="1",
        amount_wei=1_000_000_000_000_000_000,
        chain_id=1,
        contract_address="0x47CE0C6eD5B0Ce3d3A51fdb1C52DC66a7c3c2936".lower(),
        deployed_block=9117609,
    ),
    "tornado-cash-1-eth-10": TornadoPool(
        id="tornado-cash-1-eth-10",
        asset="ETH",
        amount="10",
        amount_wei=10_000_000_000_000_000_000,
        chain_id=1,
        contract_address="0x910Cbd523D972eb0a6f4cAe4618aD62622b39DbF".lower(),
        deployed_block=9117720,
    ),
    "tornado-cash-1-eth-100": TornadoPool(
        id="tornado-cash-1-eth-100",
        asset="ETH",
        amount="100",
        amount_wei=100_000_000_000_000_000_000,
        chain_id=1,
        contract_address="0xA160cdAB225685dA1d56aa342Ad8841c3b53f291".lower(),
        deployed_block=9161895,
    ),
    "tornado-cash-1-dai-100": TornadoPool(
        id="tornado-cash-1-dai-100",
        asset="DAI",
        amount="100",
        amount_wei=100_000_000_000_000_000_000,
        chain_id=1,
        contract_address="0xD4B88Df4D29F5CedD6857912842cff3b20C8Cfa3".lower(),
        deployed_block=9117612,
    ),
    "tornado-cash-1-usdc-100": TornadoPool(
        id="tornado-cash-1-usdc-100",
        asset="USDC",
        amount="100",
        amount_wei=100_000_000,
        chain_id=1,
        contract_address="0xd96f2Bae24A12B2624F0e00f918C4FeAc5980005".lower(),
        deployed_block=9161958,
        decimals=6,
    ),
}

# Sepolia Testnet (Chain ID 11155111)
SEPOLIA_POOLS: dict[str, TornadoPool] = {
    "tornado-cash-11155111-eth-0.1": TornadoPool(
        id="tornado-cash-11155111-eth-0.1",
        asset="ETH",
        amount="0.1",
        amount_wei=100_000_000_000_000_000,
        chain_id=11155111,
        contract_address="0x89c9F1E29aE7b425555462fa112e4dFfAfe1C5e6".lower(),
        deployed_block=5500000,
    ),
}

ALL_POOLS = {**MAINNET_POOLS, **SEPOLIA_POOLS}


def get_pool(pool_id: str) -> TornadoPool:
    if pool_id in ALL_POOLS:
        return ALL_POOLS[pool_id]
    raise KeyError(f"Pool '{pool_id}' not found in registry")
