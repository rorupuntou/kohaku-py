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
    paymaster_address: str | None = None
    paymaster_adapter: str | None = None


# Official Tornado Paymaster addresses
MAINNET_PAYMASTER = "0xe06CB96C57D2442f8F60F5017354BC08F7e91308".lower()
SEPOLIA_PAYMASTER = "0x1c5aCCb9c09D72945b79EC986776136bE01d7B2F".lower()

# ERC-20 Token Contracts
TOKEN_ADDRESSES: dict[tuple[int, str], str] = {
    (1, "DAI"): "0x6B175474E89094C44Da98b954EedeAC495271d0F".lower(),
    (1, "USDC"): "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48".lower(),
    (1, "USDT"): "0xdAC17F958D2ee523a2206206994597C13D831ec7".lower(),
    (1, "WBTC"): "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599".lower(),
    (11155111, "DAI"): "0xFF34B3d4Aee8ddCd6F9AFFFB6Fe49bD371b8a357".lower(),
}

# Ethereum Mainnet (Chain ID 1) — Classic + Extended Denominations & Full ERC-20 Pools
MAINNET_POOLS: dict[str, TornadoPool] = {
    "tornado-cash-1-eth-0.01": TornadoPool(
        id="tornado-cash-1-eth-0.01",
        asset="ETH",
        amount="0.01",
        amount_wei=10_000_000_000_000_000,
        chain_id=1,
        contract_address="0x199112eb461ea7eec1d75b33343542e1d069b41c".lower(),
        deployed_block=26198980,
    ),
    "tornado-cash-1-eth-0.03": TornadoPool(
        id="tornado-cash-1-eth-0.03",
        asset="ETH",
        amount="0.03",
        amount_wei=30_000_000_000_000_000,
        chain_id=1,
        contract_address="0x398971a7ae0fed4ae435f353ef00d3d4e4c18fd4".lower(),
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
        paymaster_address=MAINNET_PAYMASTER,
        paymaster_adapter="0x4a3F73a23563bB467Aa034d0fAB61e7BcDf26161".lower(),
    ),
    "tornado-cash-1-eth-0.3": TornadoPool(
        id="tornado-cash-1-eth-0.3",
        asset="ETH",
        amount="0.3",
        amount_wei=300_000_000_000_000_000,
        chain_id=1,
        contract_address="0xf22487b84a618192aa68c0e1da24e9bbd892f774".lower(),
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
        paymaster_address=MAINNET_PAYMASTER,
        paymaster_adapter="0xC086b50Dd859Bb15D553327178DEdbC347B5b905".lower(),
    ),
    "tornado-cash-1-eth-3": TornadoPool(
        id="tornado-cash-1-eth-3",
        asset="ETH",
        amount="3",
        amount_wei=3_000_000_000_000_000_000,
        chain_id=1,
        contract_address="0x74185a3f30b873c0ce1f4257298d1cda61be2f9f".lower(),
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
        paymaster_address=MAINNET_PAYMASTER,
        paymaster_adapter="0x08d1103bff53CBdC9DB1e81B79475CEad2e35870".lower(),
    ),
    "tornado-cash-1-eth-30": TornadoPool(
        id="tornado-cash-1-eth-30",
        asset="ETH",
        amount="30",
        amount_wei=30_000_000_000_000_000_000,
        chain_id=1,
        contract_address="0xc11197f71c7730c8b5db7c84191e07575f1db896".lower(),
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
        paymaster_address=MAINNET_PAYMASTER,
        paymaster_adapter="0x3aF851f9BeEeE6E9fa06022f34Dc4C453D265aE5".lower(),
    ),
    # DAI Pools (18 decimals)
    "tornado-cash-1-dai-100": TornadoPool(
        id="tornado-cash-1-dai-100",
        asset="DAI",
        amount="100",
        amount_wei=100 * 10**18,
        chain_id=1,
        contract_address="0xD4B88Df4D29F5CedD6857912842cff3b20C8Cfa3".lower(),
        deployed_block=9117612,
        decimals=18,
    ),
    "tornado-cash-1-dai-1000": TornadoPool(
        id="tornado-cash-1-dai-1000",
        asset="DAI",
        amount="1000",
        amount_wei=1_000 * 10**18,
        chain_id=1,
        contract_address="0xFD8610d20aA15b7B2E3Be39B396a1bC3516c7144".lower(),
        deployed_block=9161917,
        decimals=18,
    ),
    "tornado-cash-1-dai-10000": TornadoPool(
        id="tornado-cash-1-dai-10000",
        asset="DAI",
        amount="10000",
        amount_wei=10_000 * 10**18,
        chain_id=1,
        contract_address="0x07687e702b410Fa43f4cB4Af7FA097918ffD2730".lower(),
        deployed_block=12066007,
        decimals=18,
        paymaster_address=MAINNET_PAYMASTER,
        paymaster_adapter="0x36A5b4bCE77700B9C52cFEE53Fc8cA3B58eb7E35".lower(),
    ),
    "tornado-cash-1-dai-100000": TornadoPool(
        id="tornado-cash-1-dai-100000",
        asset="DAI",
        amount="100000",
        amount_wei=100_000 * 10**18,
        chain_id=1,
        contract_address="0x23773E65ed146A459791799d01336DB287f25334".lower(),
        deployed_block=12066048,
        decimals=18,
        paymaster_address=MAINNET_PAYMASTER,
        paymaster_adapter="0x83Ff713F0939409E1c6023bc8aaB3E49eD968c8D".lower(),
    ),
    # USDC Pools (6 decimals)
    "tornado-cash-1-usdc-100": TornadoPool(
        id="tornado-cash-1-usdc-100",
        asset="USDC",
        amount="100",
        amount_wei=100 * 10**6,
        chain_id=1,
        contract_address="0xd96f2B1c14Db8458374d9Aca76E26c3D18364307".lower(),
        deployed_block=9161958,
        decimals=6,
        paymaster_address=MAINNET_PAYMASTER,
        paymaster_adapter="0x44336242f9766b4c751F6958499C5cc18325e25B".lower(),
    ),
    "tornado-cash-1-usdc-1000": TornadoPool(
        id="tornado-cash-1-usdc-1000",
        asset="USDC",
        amount="1000",
        amount_wei=1_000 * 10**6,
        chain_id=1,
        contract_address="0x4736dCf1b7A3d580672CcE6E7c65cd5cc9cFBa9D".lower(),
        deployed_block=9161965,
        decimals=6,
        paymaster_address=MAINNET_PAYMASTER,
        paymaster_adapter="0xB1C7e712AF153073979AdC5ef8B1Cc5A7b0cf031".lower(),
    ),
    # USDT Pools (6 decimals)
    "tornado-cash-1-usdt-100": TornadoPool(
        id="tornado-cash-1-usdt-100",
        asset="USDT",
        amount="100",
        amount_wei=100 * 10**6,
        chain_id=1,
        contract_address="0x169AD27A470D064DEDE56a2D3ff727986b15D52B".lower(),
        deployed_block=9162005,
        decimals=6,
        paymaster_address=MAINNET_PAYMASTER,
        paymaster_adapter="0xF006862cCa4829D3f3ddD52d93fC49C03D380a5F".lower(),
    ),
    "tornado-cash-1-usdt-1000": TornadoPool(
        id="tornado-cash-1-usdt-1000",
        asset="USDT",
        amount="1000",
        amount_wei=1_000 * 10**6,
        chain_id=1,
        contract_address="0x0836222F2B2B24A3F36f98668Ed8F0B38D1a872f".lower(),
        deployed_block=9162012,
        decimals=6,
        paymaster_address=MAINNET_PAYMASTER,
        paymaster_adapter="0x5DF524b6c9303eD94A7767c2eD787ee223c9bC54".lower(),
    ),
    # WBTC Pools (8 decimals)
    "tornado-cash-1-wbtc-0.1": TornadoPool(
        id="tornado-cash-1-wbtc-0.1",
        asset="WBTC",
        amount="0.1",
        amount_wei=10_000_000,
        chain_id=1,
        contract_address="0x178169B423a011fff22B9e3F3abeA13414dDD0F1".lower(),
        deployed_block=12067529,
        decimals=8,
        paymaster_address=MAINNET_PAYMASTER,
        paymaster_adapter="0x0fdF2f686B600523F9752aEca0abb6AD9603A22C".lower(),
    ),
    "tornado-cash-1-wbtc-1": TornadoPool(
        id="tornado-cash-1-wbtc-1",
        asset="WBTC",
        amount="1",
        amount_wei=100_000_000,
        chain_id=1,
        contract_address="0x610B717796ad172B316836AC95a2ffad065CeaB4".lower(),
        deployed_block=12066652,
        decimals=8,
        paymaster_address=MAINNET_PAYMASTER,
        paymaster_adapter="0xec3Cca694EEe55808B3f5EFEDd0bC03E52e47834".lower(),
    ),
    "tornado-cash-1-wbtc-10": TornadoPool(
        id="tornado-cash-1-wbtc-10",
        asset="WBTC",
        amount="10",
        amount_wei=1_000_000_000,
        chain_id=1,
        contract_address="0xbB93e510BbCD0B7beb5A853875f9eC60275CF498".lower(),
        deployed_block=12067591,
        decimals=8,
        paymaster_address=MAINNET_PAYMASTER,
        paymaster_adapter="0xC2C427E6ADF66F412921C17958CeDD9C7710F521".lower(),
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
        contract_address="0x0e999c5285141ccb6dfae68a0921f37abd3e6a87".lower(),
        deployed_block=11949077,
    ),
    "tornado-cash-11155111-eth-0.03": TornadoPool(
        id="tornado-cash-11155111-eth-0.03",
        asset="ETH",
        amount="0.03",
        amount_wei=30_000_000_000_000_000,
        chain_id=11155111,
        contract_address="0x9480be3964642efcd6cebdb3570db8dc0f788908".lower(),
        deployed_block=11949078,
    ),
    "tornado-cash-11155111-eth-0.1": TornadoPool(
        id="tornado-cash-11155111-eth-0.1",
        asset="ETH",
        amount="0.1",
        amount_wei=100_000_000_000_000_000,
        chain_id=11155111,
        contract_address="0x8c4a04d872a6c1be37964a21ba3a138525dff50b".lower(),
        deployed_block=5594400,
        paymaster_address=SEPOLIA_PAYMASTER,
        paymaster_adapter="0xa616aAE443FCCABfc2F1EA2Afe001E5046FFDCe0".lower(),
    ),
    "tornado-cash-11155111-eth-0.3": TornadoPool(
        id="tornado-cash-11155111-eth-0.3",
        asset="ETH",
        amount="0.3",
        amount_wei=300_000_000_000_000_000,
        chain_id=11155111,
        contract_address="0x83091415b54d764e215153ff54b36ccd44122e6e".lower(),
        deployed_block=11949080,
    ),
    "tornado-cash-11155111-eth-1": TornadoPool(
        id="tornado-cash-11155111-eth-1",
        asset="ETH",
        amount="1",
        amount_wei=1_000_000_000_000_000_000,
        chain_id=11155111,
        contract_address="0x8cc930096b4df705a007c4a039bdfa1320ed2508".lower(),
        deployed_block=5594401,
        paymaster_address=SEPOLIA_PAYMASTER,
        paymaster_adapter="0x67a898343F32641206d0f30CB3367944a8919A3A".lower(),
    ),
    "tornado-cash-11155111-eth-3": TornadoPool(
        id="tornado-cash-11155111-eth-3",
        asset="ETH",
        amount="3",
        amount_wei=3_000_000_000_000_000_000,
        chain_id=11155111,
        contract_address="0x7ee90edc51c3739af3ee277e09ade3f3d6bad4af".lower(),
        deployed_block=11949081,
    ),
    "tornado-cash-11155111-eth-10": TornadoPool(
        id="tornado-cash-11155111-eth-10",
        asset="ETH",
        amount="10",
        amount_wei=10_000_000_000_000_000_000,
        chain_id=11155111,
        contract_address="0x8d10d506d29fc62abb8a290b99f66db27fc43585".lower(),
        deployed_block=5594402,
    ),
    "tornado-cash-11155111-eth-30": TornadoPool(
        id="tornado-cash-11155111-eth-30",
        asset="ETH",
        amount="30",
        amount_wei=30_000_000_000_000_000_000,
        chain_id=11155111,
        contract_address="0x3d1c943dfb2c8d9905b0da0afd18615915ff343a".lower(),
        deployed_block=11949082,
    ),
    "tornado-cash-11155111-dai-100": TornadoPool(
        id="tornado-cash-11155111-dai-100",
        asset="DAI",
        amount="100",
        amount_wei=100 * 10**18,
        chain_id=11155111,
        contract_address="0x6921fd1a97441dd603a997ED6DDF388658daf754".lower(),
        deployed_block=5594406,
        decimals=18,
        paymaster_address=SEPOLIA_PAYMASTER,
        paymaster_adapter="0xbF0a7969dacF8337716d0F283df0574dF56b0479".lower(),
    ),
}

ALL_POOLS = {**MAINNET_POOLS, **SEPOLIA_POOLS}
SUPPORTED_ASSET_SYMBOLS = ["ETH", "USDC", "USDT", "DAI", "WBTC"]


def get_pool(pool_id: str) -> TornadoPool:
    if pool_id in ALL_POOLS:
        return ALL_POOLS[pool_id]
    raise KeyError(f"Pool '{pool_id}' not found in registry")


def resolve_asset(symbol: str, chain_id: int) -> dict[str, Any]:
    """Resolves only supported symbols for a given chain ID.

    Matches `edw_core::vault::tornadocash::resolve_asset`.
    """
    norm_symbol = symbol.strip().upper()
    if norm_symbol not in SUPPORTED_ASSET_SYMBOLS:
        raise ValueError(
            f"unsupported token `{symbol}`; expected ETH, USDC, USDT, DAI, or WBTC"
        )
    matching_pools = [
        p for p in ALL_POOLS.values() if p.chain_id == chain_id and p.asset.upper() == norm_symbol
    ]
    if not matching_pools:
        raise ValueError(f"no {symbol} pools on chain {chain_id}")

    sample_pool = matching_pools[0]
    is_native = norm_symbol == "ETH"
    token_addr = None if is_native else TOKEN_ADDRESSES.get((chain_id, norm_symbol))
    return {
        "symbol": norm_symbol,
        "decimals": sample_pool.decimals,
        "is_native": is_native,
        "token_address": token_addr,
        "chain_id": chain_id,
    }


def parse_amount(amount_str: str, decimals: int) -> int:
    """Parses a decimal token string into raw base units with strict validation.

    Matches `edw_core::vault::tornadocash::parse_amount`.
    """
    text = amount_str.strip()
    parts = text.split(".")
    if (
        len(parts) > 2
        or not parts[0]
        or not parts[0].isdigit()
        or (len(parts) == 2 and (len(parts[1]) > decimals or not parts[1] or not parts[1].isdigit()))
    ):
        raise ValueError(f"invalid amount `{amount_str}`")

    whole = int(parts[0])
    frac = parts[1] if len(parts) == 2 else ""
    padded_frac = frac.ljust(decimals, "0")
    frac_int = int(padded_frac) if padded_frac else 0
    return whole * (10**decimals) + frac_int


def parse_eth(amount_str: str) -> int:
    """Parse a decimal ETH string into integer wei (18 decimals)."""
    return parse_amount(amount_str, 18)


def format_amount(amount_raw: int, decimals: int) -> str:
    """Renders raw units with selected asset decimals, trimming trailing zeros."""
    if decimals == 0:
        return str(amount_raw)
    divisor = 10**decimals
    whole = amount_raw // divisor
    remainder = amount_raw % divisor
    if remainder == 0:
        return str(whole)
    frac_str = str(remainder).zfill(decimals).rstrip("0")
    return f"{whole}.{frac_str}"


def format_eth(amount_wei: int) -> str:
    """Renders wei as a decimal ETH string."""
    return format_amount(amount_wei, 18)


def deposit_pools_for_asset(
    amount_raw: int, chain_id: int, asset: str
) -> list[TornadoPool]:
    """Splits `amount_raw` into deposit pools for `asset`, largest denomination first.

    Matches `edw_core::vault::tornadocash::deposit_pools_for_asset`.
    """
    if amount_raw <= 0:
        raise ValueError("amount must be greater than zero")
    norm_asset = asset.strip().upper()
    pools = sorted(
        (
            p
            for p in ALL_POOLS.values()
            if p.chain_id == chain_id and p.asset.upper() == norm_asset
        ),
        key=lambda p: p.amount_wei,
        reverse=True,
    )
    if not pools:
        raise ValueError(f"no {norm_asset} pools on chain {chain_id}")

    remaining = amount_raw
    chosen: list[TornadoPool] = []
    for pool in pools:
        count, remaining = divmod(remaining, pool.amount_wei)
        if count > 0:
            chosen.extend([pool] * count)

    if remaining != 0:
        raise ValueError(
            f"amount {amount_raw} is not a sum of the {norm_asset} pool denominations on chain {chain_id}"
        )
    return chosen


def decompose_eth_amount(amount_wei: int, chain_id: int = 1) -> list[TornadoPool]:
    """Greedily split `amount_wei` into native ETH Tornado pools (largest denomination first)."""
    return deposit_pools_for_asset(amount_wei, chain_id, "ETH")


def exact_notes_for_asset(
    amount_raw: int, notes: list[Any], asset: str
) -> list[Any]:
    """Selects notes whose denominations sum to `amount_raw` exactly, largest first."""
    if amount_raw <= 0:
        raise ValueError("amount must be greater than zero")
    norm_asset = asset.strip().upper()
    available = [
        n
        for n in notes
        if getattr(n, "leaf_index", None) is not None
        and not getattr(n, "spent", False)
        and (getattr(n, "currency", None) or getattr(getattr(n, "pool", None), "asset", None) or "").upper() == norm_asset
    ]
    denoms = sorted(
        list(
            {
                int(getattr(n, "amount_wei", None) or getattr(getattr(n, "pool", None), "amount_wei", 0))
                for n in available
            }
        ),
        reverse=True,
    )
    remaining = amount_raw
    chosen: list[Any] = []
    for denom in denoms:
        want = remaining // denom
        taken = [
            n
            for n in available
            if int(getattr(n, "amount_wei", None) or getattr(getattr(n, "pool", None), "amount_wei", 0)) == denom
        ][:want]
        for t in taken:
            available.remove(t)
        remaining -= denom * len(taken)
        chosen.extend(taken)

    if remaining != 0:
        raise ValueError(f"held notes cannot make {amount_raw} exactly")
    return chosen


def _has_paymaster(n: Any) -> bool:
    if getattr(n, "paymaster_address", None):
        return True
    pool = getattr(n, "pool", None)
    if not pool and hasattr(n, "pool_id"):
        try:
            pool = get_pool(n.pool_id)
        except Exception:
            pool = None
    if pool and (getattr(pool, "paymaster_address", None) or getattr(pool, "paymaster", None)):
        return True
    return False


def withdrawal_notes(
    amount_raw: int, notes: list[Any], asset: str, chain_id: int
) -> list[Any]:
    """Selects notes for withdrawal.

    For ETH: ensures index 0 has a paymaster to sponsor gas.
    For ERC-20: selects token notes, and prepends a separate mined unspent ETH note with paymaster to sponsor gas.
    Matches `edw_core::vault::tornadocash::withdrawal_notes`.
    """
    norm_asset = asset.strip().upper()
    held = [
        n
        for n in notes
        if int(getattr(n, "chain_id", None) or getattr(getattr(n, "pool", None), "chain_id", 0)) == chain_id
    ]
    selected = exact_notes_for_asset(amount_raw, held, norm_asset)
    if norm_asset == "ETH":
        has_pm = [i for i, n in enumerate(selected) if _has_paymaster(n)]
        if not has_pm:
            raise ValueError("the selected ETH notes have no paymaster")
        idx = has_pm[0]
        selected[0], selected[idx] = selected[idx], selected[0]
    else:
        sponsors = [
            n
            for n in held
            if getattr(n, "leaf_index", None) is not None
            and not getattr(n, "spent", False)
            and (getattr(n, "currency", None) or getattr(getattr(n, "pool", None), "asset", None) or "").upper() == "ETH"
            and _has_paymaster(n)
        ]
        if not sponsors:
            raise ValueError(
                "every ERC-20 withdrawal requires an additional mined shielded ETH note with a paymaster to sponsor gas"
            )
        smallest_sponsor = min(
            sponsors,
            key=lambda n: int(getattr(n, "amount_wei", None) or getattr(getattr(n, "pool", None), "amount_wei", 0)),
        )
        selected.insert(0, smallest_sponsor)
    return selected

