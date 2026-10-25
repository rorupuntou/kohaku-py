"""Tornado Cash pool registry for Ethereum Mainnet and Sepolia."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


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


# Ethereum Mainnet (Chain ID 1) — Classic + Extended ETH Denominations (EDW PR #111)
MAINNET_POOLS: dict[str, TornadoPool] = {
    "tornado-cash-1-eth-0.01": TornadoPool(
        id="tornado-cash-1-eth-0.01",
        asset="ETH",
        amount="0.01",
        amount_wei=10_000_000_000_000_000,
        chain_id=1,
        contract_address="0x199112eb461ea7eec1d75b33343542e1d069b41c",
        deployed_block=26198980,
    ),
    "tornado-cash-1-eth-0.03": TornadoPool(
        id="tornado-cash-1-eth-0.03",
        asset="ETH",
        amount="0.03",
        amount_wei=30_000_000_000_000_000,
        chain_id=1,
        contract_address="0x398971a7ae0fed4ae435f353ef00d3d4e4c18fd4",
        deployed_block=26198980,
    ),
    "tornado-cash-1-eth-0.1": TornadoPool(
        id="tornado-cash-1-eth-0.1",
        asset="ETH",
        amount="0.1",
        amount_wei=100_000_000_000_000_000,
        chain_id=1,
        contract_address="0x12D66f87A04A9E220743712CE6d9bB1B5616B8Fc".lower(),
        deployed_block=9116966,
    ),
    "tornado-cash-1-eth-0.3": TornadoPool(
        id="tornado-cash-1-eth-0.3",
        asset="ETH",
        amount="0.3",
        amount_wei=300_000_000_000_000_000,
        chain_id=1,
        contract_address="0xf22487b84a618192aa68c0e1da24e9bbd892f774",
        deployed_block=26198980,
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
    "tornado-cash-1-eth-3": TornadoPool(
        id="tornado-cash-1-eth-3",
        asset="ETH",
        amount="3",
        amount_wei=3_000_000_000_000_000_000,
        chain_id=1,
        contract_address="0x74185a3f30b873c0ce1f4257298d1cda61be2f9f",
        deployed_block=26198980,
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
    "tornado-cash-1-eth-30": TornadoPool(
        id="tornado-cash-1-eth-30",
        asset="ETH",
        amount="30",
        amount_wei=30_000_000_000_000_000_000,
        chain_id=1,
        contract_address="0xc11197f71c7730c8b5db7c84191e07575f1db896",
        deployed_block=26198983,
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
    "tornado-cash-11155111-eth-0.01": TornadoPool(
        id="tornado-cash-11155111-eth-0.01",
        asset="ETH",
        amount="0.01",
        amount_wei=10_000_000_000_000_000,
        chain_id=11155111,
        contract_address="0x0e999c5285141ccb6dfae68a0921f37abd3e6a87",
        deployed_block=11949077,
    ),
    "tornado-cash-11155111-eth-0.03": TornadoPool(
        id="tornado-cash-11155111-eth-0.03",
        asset="ETH",
        amount="0.03",
        amount_wei=30_000_000_000_000_000,
        chain_id=11155111,
        contract_address="0x9480be3964642efcd6cebdb3570db8dc0f788908",
        deployed_block=11949078,
    ),
    "tornado-cash-11155111-eth-0.1": TornadoPool(
        id="tornado-cash-11155111-eth-0.1",
        asset="ETH",
        amount="0.1",
        amount_wei=100_000_000_000_000_000,
        chain_id=11155111,
        contract_address="0x8c4a04d872a6c1be37964a21ba3a138525dff50b",
        deployed_block=5594400,
    ),
    "tornado-cash-11155111-eth-0.3": TornadoPool(
        id="tornado-cash-11155111-eth-0.3",
        asset="ETH",
        amount="0.3",
        amount_wei=300_000_000_000_000_000,
        chain_id=11155111,
        contract_address="0x83091415b54d764e215153ff54b36ccd44122e6e",
        deployed_block=11949080,
    ),
    "tornado-cash-11155111-eth-1": TornadoPool(
        id="tornado-cash-11155111-eth-1",
        asset="ETH",
        amount="1",
        amount_wei=1_000_000_000_000_000_000,
        chain_id=11155111,
        contract_address="0x8cc930096b4df705a007c4a039bdfa1320ed2508",
        deployed_block=5594401,
    ),
    "tornado-cash-11155111-eth-3": TornadoPool(
        id="tornado-cash-11155111-eth-3",
        asset="ETH",
        amount="3",
        amount_wei=3_000_000_000_000_000_000,
        chain_id=11155111,
        contract_address="0x7ee90edc51c3739af3ee277e09ade3f3d6bad4af",
        deployed_block=11949081,
    ),
    "tornado-cash-11155111-eth-10": TornadoPool(
        id="tornado-cash-11155111-eth-10",
        asset="ETH",
        amount="10",
        amount_wei=10_000_000_000_000_000_000,
        chain_id=11155111,
        contract_address="0x8d10d506d29fc62abb8a290b99f66db27fc43585",
        deployed_block=5594402,
    ),
    "tornado-cash-11155111-eth-30": TornadoPool(
        id="tornado-cash-11155111-eth-30",
        asset="ETH",
        amount="30",
        amount_wei=30_000_000_000_000_000_000,
        chain_id=11155111,
        contract_address="0x3d1c943dfb2c8d9905b0da0afd18615915ff343a",
        deployed_block=11949082,
    ),
}

ALL_POOLS = {**MAINNET_POOLS, **SEPOLIA_POOLS}


def get_pool(pool_id: str) -> TornadoPool:
    if pool_id in ALL_POOLS:
        return ALL_POOLS[pool_id]
    raise KeyError(f"Pool '{pool_id}' not found in registry")


def parse_eth(amount_str: str) -> int:
    """Parse a decimal ETH string (e.g. '33.34') into integer wei."""
    text = amount_str.strip()
    if not text:
        raise ValueError("Empty ETH amount")
    try:
        dec = Decimal(text)
    except InvalidOperation as e:
        raise ValueError(f"Invalid ETH amount: {amount_str}") from e
    if dec < 0:
        raise ValueError(f"ETH amount cannot be negative: {amount_str}")
    scaled = dec * (Decimal(10) ** 18)
    if scaled != int(scaled):
        raise ValueError(f"ETH amount has more than 18 decimals: {amount_str}")
    return int(scaled)


def decompose_eth_amount(amount_wei: int, chain_id: int = 1) -> list[TornadoPool]:
    """Greedily split `amount_wei` into native ETH Tornado pools (largest denomination first).

    Matches `edw_core::vault::tornadocash::deposit_pools` across `[100, 30, 10, 3, 1, 0.3, 0.1, 0.03, 0.01]` ETH.
    """
    if amount_wei <= 0:
        raise ValueError("Amount must be greater than zero")

    native_pools = sorted(
        (
            p
            for p in ALL_POOLS.values()
            if p.chain_id == chain_id and p.asset == "ETH"
        ),
        key=lambda p: p.amount_wei,
        reverse=True,
    )
    if not native_pools:
        raise ValueError(f"No native ETH pools configured for chain {chain_id}")

    remaining = amount_wei
    chosen: list[TornadoPool] = []
    for pool in native_pools:
        count, remaining = divmod(remaining, pool.amount_wei)
        if count > 0:
            chosen.extend([pool] * count)

    if remaining != 0:
        raise ValueError(
            f"Amount {amount_wei} wei cannot be represented as a sum of Tornado ETH denominations on chain {chain_id}"
        )
    return chosen
