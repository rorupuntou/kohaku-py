from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def parse_hex_int(val: Any) -> int:
    """Parses a hex string (e.g. '0x1a') or int into an int."""
    if isinstance(val, int):
        return val
    if isinstance(val, str):
        if val.startswith("0x") or val.startswith("0X"):
            return int(val, 16)
        return int(val)
    raise ValueError(f"Cannot parse {val!r} as int")


@dataclass(frozen=True)
class Digest:
    type: str
    data: str  # lowercase hex digest, e.g. "0x0615..."

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Digest:
        return cls(
            type=data.get("type", "sha256"),
            data=data.get("data", "").lower(),
        )


@dataclass(frozen=True)
class Chunk:
    from_block: int
    to_block: int
    file: str
    size: int
    digest: Digest
    is_hot: bool = False

    @property
    def range_str(self) -> str:
        return f"[{hex(self.from_block)}, {hex(self.to_block)})"

    @classmethod
    def from_dict(cls, data: dict[str, Any], is_hot: bool = False) -> Chunk:
        return cls(
            from_block=parse_hex_int(data["fromBlock"]),
            to_block=parse_hex_int(data["toBlock"]),
            file=data["file"],
            size=parse_hex_int(data["size"]),
            digest=Digest.from_dict(data["digest"]),
            is_hot=is_hot,
        )


@dataclass
class ProtocolInfo:
    id: str
    protocol: str
    chain_id: int
    tracked_addresses: list[str]
    tracked_event_topics: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)
    chunks: list[Chunk] = field(default_factory=list)
    hot_head: Chunk | None = None

    @classmethod
    def from_dict(cls, protocol_id: str, data: dict[str, Any]) -> ProtocolInfo:
        chunks = [Chunk.from_dict(c, is_hot=False) for c in data.get("chunks", [])]
        hot_head = (
            Chunk.from_dict(data["hotHead"], is_hot=True)
            if "hotHead" in data and data["hotHead"]
            else None
        )
        return cls(
            id=protocol_id,
            protocol=data.get("protocol", ""),
            chain_id=parse_hex_int(data.get("chainId", "0x1")),
            tracked_addresses=[a.lower() for a in data.get("trackedAddresses", [])],
            tracked_event_topics=[
                t.lower() for t in data.get("trackedEventTopics", [])
            ],
            metadata=data.get("protocolMetadata", {}),
            chunks=chunks,
            hot_head=hot_head,
        )

    @property
    def total_chunks(self) -> int:
        return len(self.chunks) + (1 if self.hot_head else 0)

    @property
    def block_range(self) -> tuple[int, int] | None:
        if not self.chunks and not self.hot_head:
            return None
        start = (
            self.chunks[0].from_block
            if self.chunks
            else self.hot_head.from_block  # type: ignore[union-attr]
        )
        end = (
            self.hot_head.to_block  # type: ignore[union-attr]
            if self.hot_head
            else self.chunks[-1].to_block
        )
        return start, end


@dataclass
class Manifest:
    version: int
    updated_at: str
    compression: str
    available_protocols: dict[str, ProtocolInfo]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Manifest:
        protocols = {}
        for p_id, p_data in data.get("availableProtocols", {}).items():
            protocols[p_id] = ProtocolInfo.from_dict(p_id, p_data)
        return cls(
            version=data.get("version", 1),
            updated_at=data.get("updatedAt", ""),
            compression=data.get("compression", "gzip"),
            available_protocols=protocols,
        )


@dataclass(frozen=True)
class Event:
    contract_address: str
    event_topic: str
    topics: list[str]
    data: str
    block_number: int
    log_index: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Event:
        return cls(
            contract_address=data["contractAddress"].lower(),
            event_topic=data["eventTopic"].lower(),
            topics=[t.lower() for t in data.get("topics", [])],
            data=data.get("data", "").lower(),
            block_number=parse_hex_int(data["blockNumber"]),
            log_index=parse_hex_int(data["logIndex"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "contractAddress": self.contract_address,
            "eventTopic": self.event_topic,
            "topics": self.topics,
            "data": self.data,
            "blockNumber": hex(self.block_number),
            "logIndex": hex(self.log_index),
        }
