"""Tornado Cash Relayer Registry state synchronizer (`tornado-cash-1-relayer-registry`)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from kohaku.sync.client import DEFAULT_SAGA_URL, SagaClient

RELAYER_REGISTRY_ADDRESS = "0x58e8dcc13be9780fc42e8723d8ead4cf46943df2"
RELAYER_REGISTERED_TOPIC = (
    "0x9ca7c9c762eff27b021608f232b4c4b8f9b8bf9a3d322297e47cc4209a67d5e2"
)
WORKER_REGISTERED_TOPIC = (
    "0xafa759fb3c68e89eaaba359f0930ab40c24875b73cc9e2f6a38b0180019eb8f3"
)
WORKER_UNREGISTERED_TOPIC = (
    "0x490a66cc56c789979052c7052fc0c10a6c4627d8e6165caec80db97a4c383521"
)
STAKE_ADDED_TOPIC = (
    "0x1275dbe2a271b2b822e60f1d44894fa5fb337e7e2dc6a200205b1a5b17c07d64"
)
STAKE_BURNED_TOPIC = (
    "0x659f33fc6677bebf3a9bf3101092792e31f35766d0358e54577bdd91a655f6a0"
)


@dataclass
class RegisteredRelayer:
    address: str
    ens_name: str
    ens_hash: str
    staked_wei: int = 0
    burned_wei: int = 0
    relay_count: int = 0
    registered_block: int = 0
    last_active_block: int = 0
    workers: set[str] = field(default_factory=set)

    @property
    def staked_torn(self) -> float:
        return self.staked_wei / 1e18

    @property
    def burned_torn(self) -> float:
        return self.burned_wei / 1e18

    @property
    def mainnet_subdomain(self) -> str:
        return f"mainnet-tornado.{self.ens_name}" if self.ens_name else ""


class RelayerRegistryVault:
    """Reconstructs the on-chain Tornado Cash Relayer Registry state from Saga CDN,
    local `.jsonl` snapshots, or direct Ethereum RPC logs.
    """

    def __init__(
        self,
        protocol_id: str = "tornado-cash-1-relayer-registry",
        client: SagaClient | None = None,
    ):
        self.protocol_id = protocol_id
        self.client = client or SagaClient(base_url=DEFAULT_SAGA_URL)
        self.relayers: dict[str, RegisteredRelayer] = {}
        self.synced = False

    def ingest_event(self, event: Any) -> None:
        topic = event.event_topic.lower()
        raw = bytes.fromhex(event.data[2:]) if event.data.startswith("0x") else bytes.fromhex(event.data)

        if topic == RELAYER_REGISTERED_TOPIC and len(raw) >= 128:
            ens_hash = "0x" + raw[0:32].hex()
            str_offset = int.from_bytes(raw[32:64], "big")
            relayer_addr = "0x" + raw[64:96][-20:].hex().lower()
            staked_wei = int.from_bytes(raw[96:128], "big")
            ens_name = ""
            if len(raw) >= str_offset + 32:
                str_len = int.from_bytes(raw[str_offset : str_offset + 32], "big")
                ens_name = raw[str_offset + 32 : str_offset + 32 + str_len].decode(
                    "utf-8", errors="replace"
                )
            existing = self.relayers.get(relayer_addr)
            if existing is None:
                self.relayers[relayer_addr] = RegisteredRelayer(
                    address=relayer_addr,
                    ens_name=ens_name,
                    ens_hash=ens_hash,
                    staked_wei=staked_wei,
                    registered_block=event.block_number,
                    last_active_block=event.block_number,
                    workers={relayer_addr},
                )
            else:
                existing.ens_name = ens_name
                existing.ens_hash = ens_hash
                existing.staked_wei += staked_wei
                existing.registered_block = event.block_number

        elif topic == STAKE_ADDED_TOPIC and len(raw) >= 64:
            relayer_addr = "0x" + raw[0:32][-20:].hex().lower()
            added_wei = int.from_bytes(raw[32:64], "big")
            rel = self.relayers.setdefault(
                relayer_addr,
                RegisteredRelayer(address=relayer_addr, ens_name="", ens_hash=""),
            )
            rel.staked_wei += added_wei
            rel.last_active_block = max(rel.last_active_block, event.block_number)

        elif topic == STAKE_BURNED_TOPIC and len(raw) >= 64:
            relayer_addr = "0x" + raw[0:32][-20:].hex().lower()
            burned_wei = int.from_bytes(raw[32:64], "big")
            rel = self.relayers.setdefault(
                relayer_addr,
                RegisteredRelayer(address=relayer_addr, ens_name="", ens_hash=""),
            )
            rel.staked_wei = max(0, rel.staked_wei - burned_wei)
            rel.burned_wei += burned_wei
            rel.relay_count += 1
            rel.last_active_block = max(rel.last_active_block, event.block_number)

        elif topic == WORKER_REGISTERED_TOPIC and len(raw) >= 64:
            relayer_addr = "0x" + raw[0:32][-20:].hex().lower()
            worker_addr = "0x" + raw[32:64][-20:].hex().lower()
            rel = self.relayers.setdefault(
                relayer_addr,
                RegisteredRelayer(address=relayer_addr, ens_name="", ens_hash=""),
            )
            rel.workers.add(worker_addr)

        elif topic == WORKER_UNREGISTERED_TOPIC and len(raw) >= 64:
            relayer_addr = "0x" + raw[0:32][-20:].hex().lower()
            worker_addr = "0x" + raw[32:64][-20:].hex().lower()
            if relayer_addr in self.relayers:
                self.relayers[relayer_addr].workers.discard(worker_addr)

    def sync(self) -> None:
        """Streams all chunks for `tornado-cash-1-relayer-registry` and builds the registry."""
        self.relayers.clear()
        for event in self.client.stream_events(self.protocol_id, include_hot=True):
            self.ingest_event(event)
        self.synced = True

    def active_relayers(self, min_stake_torn: float = 100.0) -> list[RegisteredRelayer]:
        """Returns relayers sorted by relay activity and current TORN stake."""
        min_wei = int(min_stake_torn * 1e18)
        eligible = [
            r
            for r in self.relayers.values()
            if r.ens_name and r.staked_wei >= min_wei
        ]
        return sorted(
            eligible,
            key=lambda r: (r.last_active_block, r.relay_count, r.staked_wei),
            reverse=True,
        )

    @staticmethod
    def ens_namehash(name: str) -> bytes:
        """Computes EIP-137 ENS namehash for a domain or subdomain."""
        from eth_hash.auto import keccak

        node = b"\x00" * 32
        if name:
            for label in reversed(name.strip(".").split(".")):
                label_hash = keccak(label.encode("utf-8"))
                node = keccak(node + label_hash)
        return node

    @classmethod
    def resolve_ens_url(
        cls,
        ens_name: str,
        rpc_url: str,
        subdomain_prefix: str = "mainnet-tornado",
        socks5_proxy: str | None = None,
    ) -> str | None:
        """Resolves the live relayer endpoint URL stored in the ENS `url` text record
        of `<subdomain_prefix>.<ens_name>` (e.g. `mainnet-tornado.reltor.eth`).
        """
        from kohaku.edw.p2p import P2PBroadcaster

        ens_registry = "0x00000000000C2E074eC69A0dFb2997BA6C7d2e1e"
        full_domain = f"{subdomain_prefix}.{ens_name}" if subdomain_prefix else ens_name
        node_hex = cls.ens_namehash(full_domain).hex()

        broadcaster = P2PBroadcaster(rpc_urls=[rpc_url], socks5_proxy=socks5_proxy)
        # 1. resolver(bytes32) -> 0x0178b8bf
        res_hex = broadcaster.rpc_call(
            "eth_call",
            [{"to": ens_registry, "data": f"0x0178b8bf{node_hex}"}, "latest"],
        )
        if not isinstance(res_hex, str) or len(res_hex) < 66 or int(res_hex, 16) == 0:
            return None
        resolver_addr = "0x" + res_hex[-40:]

        # 2. text(bytes32 node, string key="url") -> 0x59d1d43c
        calldata = (
            f"0x59d1d43c{node_hex}"
            + "00" * 31
            + "40"
            + "00" * 31
            + "03"
            + "75726c".ljust(64, "0")
        )
        txt_hex = broadcaster.rpc_call(
            "eth_call",
            [{"to": resolver_addr, "data": calldata}, "latest"],
        )
        if not isinstance(txt_hex, str) or len(txt_hex) < 130:
            return None
        raw = bytes.fromhex(txt_hex[2:])
        offset = int.from_bytes(raw[0:32], "big")
        if len(raw) < offset + 32:
            return None
        str_len = int.from_bytes(raw[offset : offset + 32], "big")
        if str_len == 0 or len(raw) < offset + 32 + str_len:
            return None
        url_str = raw[offset + 32 : offset + 32 + str_len].decode("utf-8", errors="replace").strip()
        if url_str and not (url_str.startswith("http://") or url_str.startswith("https://")):
            url_str = f"https://{url_str}"
        return url_str or None

    @staticmethod
    def fetch_relayer_status(
        base_url: str,
        socks5_proxy: str | None = None,
        timeout: float = 8.0,
    ) -> RelayerStatusQuote:
        """Queries `<base_url>/v1/status` (or `/status`) over HTTPS or Tor SOCKS5
        and returns a parsed `RelayerStatusQuote`.
        """
        from kohaku.edw.p2p import get_json_via_proxy

        clean_base = base_url.rstrip("/")
        last_err: Exception | None = None
        for suffix in ("/v1/status", "/status"):
            target = f"{clean_base}{suffix}"
            try:
                data = get_json_via_proxy(target, proxy=socks5_proxy, timeout=timeout)
                if isinstance(data, dict) and "rewardAccount" in data:
                    health_obj = data.get("health") or {}
                    is_healthy = str(health_obj.get("status", "true")).lower() == "true"
                    return RelayerStatusQuote(
                        base_url=clean_base,
                        reward_account=str(data["rewardAccount"]),
                        service_fee_percent=float(data.get("tornadoServiceFee", 0.5)),
                        net_id=int(data.get("netId", 1)),
                        healthy=is_healthy,
                        gas_prices=dict(data.get("gasPrices") or {}),
                        eth_prices=dict(data.get("ethPrices") or {}),
                    )
            except Exception as e:
                last_err = e
                continue
        raise ConnectionError(f"Failed to query relayer status from {clean_base}: {last_err}")

    @classmethod
    def select_best_relayer(
        cls,
        candidates: list[dict[str, Any]] | None = None,
        socks5_proxy: str | None = None,
        timeout: float = 6.0,
    ) -> RelayerStatusQuote:
        """Probes candidate relayers and returns the healthiest relayer with the lowest fee."""
        relayer_list = candidates if candidates is not None else list(DEFAULT_ACTIVE_MAINNET_RELAYERS)
        quotes: list[RelayerStatusQuote] = []
        for entry in relayer_list:
            url = entry["url"]
            expected_addr = entry.get("address", "").lower()
            try:
                quote = cls.fetch_relayer_status(url, socks5_proxy=socks5_proxy, timeout=timeout)
                if expected_addr and quote.reward_account.lower() != expected_addr:
                    continue
                if quote.healthy:
                    quotes.append(quote)
            except Exception:
                continue
        if not quotes:
            raise ConnectionError("No healthy Tornado Cash relayers responded to /v1/status")
        return sorted(quotes, key=lambda q: q.service_fee_percent)[0]


@dataclass
class RelayerStatusQuote:
    """Live status and fee quote returned by a Tornado Cash Relayer `/v1/status` endpoint."""

    base_url: str
    reward_account: str
    service_fee_percent: float
    net_id: int = 1
    healthy: bool = True
    gas_prices: dict[str, Any] = field(default_factory=dict)
    eth_prices: dict[str, Any] = field(default_factory=dict)

    @property
    def fast_gas_gwei(self) -> float:
        if "fast" in self.gas_prices and self.gas_prices["fast"] is not None:
            return float(self.gas_prices["fast"])
        if "maxFeePerGas" in self.gas_prices and self.gas_prices["maxFeePerGas"] is not None:
            val = float(self.gas_prices["maxFeePerGas"])
            return val / 1e9 if val > 1e6 else val
        return 1.0

    def compute_fee_wei(
        self,
        amount_wei: int,
        gas_limit: int = 350_000,
    ) -> int:
        """Calculates the total relayer fee in wei (`protocol_percent_fee + gas_reimbursement`)."""
        # Service fee percentage in basis points (e.g. 0.36% -> 36 bps -> * 36 // 10_000)
        bps = int(round(self.service_fee_percent * 100))
        service_fee = (amount_wei * bps) // 10_000
        gas_fee_wei = int(self.fast_gas_gwei * 1e9) * gas_limit
        return service_fee + gas_fee_wei



DEFAULT_ACTIVE_MAINNET_RELAYERS: tuple[dict[str, Any], ...] = (
    {
        "ens": "00relayer.eth",
        "address": "0xda0b76cc92e94a6f972ed29c104bbe8d73c2f753",
        "url": "https://eth.00relayer.xyz",
        "stake_torn": 17096.47,
    },
    {
        "ens": "safe-torn.eth",
        "address": "0x0a5b2bf3ccfb44c1d22f07eed9553ecba752d4ad",
        "url": "https://eth3.safetorn.ovh",
        "stake_torn": 26388.00,
    },
    {
        "ens": "dieguis-and-martis.eth",
        "address": "0x9edde74078fba110c22922a925f653bcf1f60121",
        "url": "https://mainnet.dieguis-and-martis.xyz",
        "stake_torn": 993.69,
    },
    {
        "ens": "tor-relay.eth",
        "address": "0x7d2a66f05d2bb0ff4dc856eb317196c59ac3e932",
        "url": "https://tor.fakkk.vin",
        "stake_torn": 1464.19,
    },
    {
        "ens": "sky-relayer.eth",
        "address": "0xee4c45cc5eaa535cb8a8ffdc92f2839a601fe226",
        "url": "https://sky-relayer.xyz",
        "stake_torn": 14083.79,
    },
    {
        "ens": "reltor.eth",
        "address": "0x4750bcfcc340aa4b31be7e71fa072716d28c29c5",
        "url": "https://eth.reltor.su",
        "stake_torn": 5714.80,
    },
)


