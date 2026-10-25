"""Per-Network Service Registry for EDW (`rpc`, `bundler`, `indexer`).

Stores network endpoints inside the Argon2id + ChaCha20-Poly1305 blinded datastore,
matching `ethereum/desktop-wallet` PR #109 (`edw network rpc / bundler / indexer`).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, List, Optional

from kohaku.edw.storage.database import EncryptedDatabase
from kohaku.sync.client import DEFAULT_SAGA_URL

DEFAULT_RPC_URLS: dict[int, List[str]] = {
    1: [
        "https://ethereum-rpc.publicnode.com",
        "https://eth.drpc.org",
        "https://1rpc.io/eth",
    ],
    11155111: [
        "https://ethereum-sepolia-rpc.publicnode.com",
        "https://sepolia.drpc.org",
    ],
}

DEFAULT_INDEXER_URLS: dict[int, Optional[str]] = {
    1: DEFAULT_SAGA_URL,
    11155111: f"{DEFAULT_SAGA_URL}/sepolia",
}


@dataclass
class NetworkServices:
    """Configured endpoints for a single EVM network."""

    chain_id: int
    rpc_urls: List[str] = field(default_factory=list)
    bundler_urls: List[str] = field(default_factory=list)
    indexer_url: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> NetworkServices:
        return cls(
            chain_id=int(d["chain_id"]),
            rpc_urls=list(d.get("rpc_urls", [])),
            bundler_urls=list(d.get("bundler_urls", [])),
            indexer_url=d.get("indexer_url"),
        )


class NetworkConfigManager:
    """Manages encrypted per-chain RPC, Bundler, and Saga Indexer configurations."""

    def __init__(self, db: EncryptedDatabase, chain_id: int = 1):
        self.db = db
        self.chain_id = chain_id
        self.scope = f"network:{chain_id}"

    def load(self) -> NetworkServices:
        raw = self.db.get_json(self.scope, "services")
        if raw is None:
            return NetworkServices(
                chain_id=self.chain_id,
                rpc_urls=list(DEFAULT_RPC_URLS.get(self.chain_id, [])),
                bundler_urls=[],
                indexer_url=DEFAULT_INDEXER_URLS.get(self.chain_id),
            )
        return NetworkServices.from_dict(raw)

    def save(self, services: NetworkServices) -> None:
        self.db.set_json(self.scope, "services", services.to_dict())

    def add_rpc(self, url: str) -> NetworkServices:
        svc = self.load()
        clean = url.strip()
        if clean and clean not in svc.rpc_urls:
            svc.rpc_urls.append(clean)
            self.save(svc)
        return svc

    def remove_rpc(self, url: str) -> NetworkServices:
        svc = self.load()
        clean = url.strip()
        if clean in svc.rpc_urls:
            svc.rpc_urls.remove(clean)
            self.save(svc)
        return svc

    def add_bundler(self, url: str) -> NetworkServices:
        svc = self.load()
        clean = url.strip()
        if clean and clean not in svc.bundler_urls:
            svc.bundler_urls.append(clean)
            self.save(svc)
        return svc

    def remove_bundler(self, url: str) -> NetworkServices:
        svc = self.load()
        clean = url.strip()
        if clean in svc.bundler_urls:
            svc.bundler_urls.remove(clean)
            self.save(svc)
        return svc

    def set_indexer(self, url: Optional[str]) -> NetworkServices:
        svc = self.load()
        svc.indexer_url = url.strip() if url else None
        self.save(svc)
        return svc
