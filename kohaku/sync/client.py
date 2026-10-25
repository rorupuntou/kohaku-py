from __future__ import annotations

import csv
import gzip
import hashlib
import json
import sqlite3
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from kohaku.sync.exceptions import (
    ChecksumMismatchError,
    ChunkDownloadError,
    ManifestError,
    ProtocolNotFoundError,
)
from kohaku.sync.models import Chunk, Event, Manifest, ProtocolInfo

DEFAULT_SAGA_URL = "https://saga.gordosoluciones.xyz"
FASTLY_SAGA_URL = "https://saga-pp-state.global.ssl.fastly.net"
GCS_ORIGIN_SAGA_URL = "https://storage.googleapis.com/pp-state"

SAGA_V2_URL = "https://saga.gordosoluciones.xyz/v2"
FASTLY_SAGA_V2_URL = "https://saga-pp-state.global.ssl.fastly.net/v2"
GCS_ORIGIN_SAGA_V2_URL = "https://storage.googleapis.com/pp-state/v2"

SAGA_V1_MIRRORS: tuple[str, ...] = (
    DEFAULT_SAGA_URL,
    FASTLY_SAGA_URL,
    GCS_ORIGIN_SAGA_URL,
)
SAGA_V2_MIRRORS: tuple[str, ...] = (
    SAGA_V2_URL,
    FASTLY_SAGA_V2_URL,
    GCS_ORIGIN_SAGA_V2_URL,
)

SAGA_PUBLISHER_ED25519_PUBKEY = (
    "0x03778175990200a844f375d7c6e13e2ae0dc67a4ce610b04afb77c0ebb46b115"
)
USER_AGENT = "saga-sync-py/0.1.0"


def verify_manifest_ed25519(
    raw_manifest_bytes: bytes,
    signature_hex: str,
    pubkey_hex: str = SAGA_PUBLISHER_ED25519_PUBKEY,
) -> bool:
    """Verify the Ed25519 signature (`index.json.sig` or `index.json.sigs`) over raw `index.json` bytes."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    clean_pub = pubkey_hex.strip().lower().removeprefix("0x")
    clean_sig = signature_hex.strip().lower().removeprefix("0x")
    pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(clean_pub))
    try:
        pub.verify(bytes.fromhex(clean_sig), raw_manifest_bytes)
        return True
    except InvalidSignature:
        return False


class SagaClient:
    """Client for fetching and verifying blockchain event logs from a local directory,
    multi-mirror Saga CDN (Custom Domain -> Fastly CDN -> GCS Origin), or direct Ethereum RPC.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_SAGA_URL,
        timeout: float = 30.0,
        verify_checksum: bool = True,
        verify_signature: bool = False,
        local_dir: str | Path | None = None,
        fallback_urls: list[str] | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.verify_checksum = verify_checksum
        self.verify_signature = verify_signature
        self.local_dir = Path(local_dir) if local_dir is not None else None
        if fallback_urls is not None:
            self.fallback_urls = [u.rstrip("/") for u in fallback_urls]
        elif self.base_url == DEFAULT_SAGA_URL:
            self.fallback_urls = [FASTLY_SAGA_URL, GCS_ORIGIN_SAGA_URL]
        elif self.base_url == SAGA_V2_URL:
            self.fallback_urls = [FASTLY_SAGA_V2_URL, GCS_ORIGIN_SAGA_V2_URL]
        else:
            self.fallback_urls = []
        self._manifest: Manifest | None = None

    def _read_local(self, relative_path: str) -> bytes | None:
        """Attempts to read a file from `self.local_dir` if configured."""
        if self.local_dir is None:
            return None
        clean_rel = relative_path.lstrip("/")
        candidate = self.local_dir / clean_rel
        if candidate.is_file():
            return candidate.read_bytes()
        return None

    def _http_get(self, path_or_url: str) -> bytes:
        if not (path_or_url.startswith("http://") or path_or_url.startswith("https://")):
            local_bytes = self._read_local(path_or_url)
            if local_bytes is not None:
                return local_bytes

        if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
            urls = [path_or_url]
        else:
            rel = path_or_url.lstrip("/")
            bases = [self.base_url] + [
                u for u in self.fallback_urls if u != self.base_url
            ]
            urls = [f"{base}/{rel}" for base in bases]

        last_err: Exception | None = None
        for url in urls:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return resp.read()
            except urllib.error.HTTPError as e:
                last_err = ChunkDownloadError(
                    f"HTTP {e.code} while fetching {url}: {e.reason}"
                )
            except urllib.error.URLError as e:
                last_err = ChunkDownloadError(
                    f"Network error while fetching {url}: {e.reason}"
                )

        assert last_err is not None
        raise last_err

    def get_manifest(
        self, force_refresh: bool = False, verify_signature: bool | None = None
    ) -> Manifest:
        """Fetches and parses the manifest (index.json), optionally verifying Ed25519 signature."""
        if self._manifest is not None and not force_refresh:
            return self._manifest

        should_verify = (
            self.verify_signature if verify_signature is None else verify_signature
        )
        try:
            raw_data = self._http_get("index.json")
            if should_verify:
                sig_raw = self._http_get("index.json.sig").decode("utf-8").strip()
                if not verify_manifest_ed25519(raw_data, sig_raw):
                    raise ManifestError(
                        f"Invalid Ed25519 signature on index.json from {self.base_url}"
                    )
            data = json.loads(raw_data.decode("utf-8"))
            self._manifest = Manifest.from_dict(data)
            return self._manifest
        except (json.JSONDecodeError, ChunkDownloadError) as e:
            raise ManifestError(f"Failed to load manifest from {self.base_url}: {e}") from e

    def list_protocols(self) -> list[str]:
        """Returns the list of available protocol IDs."""
        manifest = self.get_manifest()
        return sorted(manifest.available_protocols.keys())

    def get_protocol(self, protocol_id: str) -> ProtocolInfo:
        """Returns metadata and chunk list for a given protocol ID."""
        manifest = self.get_manifest()
        if protocol_id not in manifest.available_protocols:
            raise ProtocolNotFoundError(
                f"Protocol '{protocol_id}' not found. Available: {', '.join(self.list_protocols())}"
            )
        return manifest.available_protocols[protocol_id]

    def fetch_chunk_bytes(self, chunk: Chunk | str) -> bytes:
        """Downloads a chunk file (or reads from local_dir), decompresses it, and verifies its sha256 checksum."""
        if isinstance(chunk, str):
            filename = chunk
            expected_digest = None
        else:
            filename = chunk.file
            expected_digest = chunk.digest.data.lower()

        # Support reading pre-decompressed .jsonl from local_dir if present
        if self.local_dir is not None and filename.endswith(".gz"):
            decompressed_local = self._read_local(filename[:-3])
            if decompressed_local is not None:
                if self.verify_checksum and expected_digest:
                    actual_digest = f"0x{hashlib.sha256(decompressed_local).hexdigest()}"
                    if actual_digest != expected_digest:
                        raise ChecksumMismatchError(filename, expected_digest, actual_digest)
                return decompressed_local

        compressed = self._http_get(filename)
        decompressed = gzip.decompress(compressed)

        if self.verify_checksum and expected_digest:
            actual_digest = f"0x{hashlib.sha256(decompressed).hexdigest()}"
            if actual_digest != expected_digest:
                raise ChecksumMismatchError(filename, expected_digest, actual_digest)

        return decompressed

    @staticmethod
    def fetch_rpc_logs(
        rpc_url: str,
        contract_address: str,
        topics: list[str | list[str] | None] | None = None,
        from_block: int = 0,
        to_block: int | str = "latest",
        socks5_proxy: str | None = None,
    ) -> list[Event]:
        """Fetches event logs directly from an Ethereum RPC node via `eth_getLogs`
        (supporting Tor SOCKS5 when `socks5_proxy` is provided), bypassing Saga CDN completely.
        """
        from kohaku.edw.p2p import P2PBroadcaster

        to_block_hex = (
            hex(to_block) if isinstance(to_block, int) else to_block
        )
        filter_params: dict[str, Any] = {
            "address": contract_address,
            "fromBlock": hex(from_block),
            "toBlock": to_block_hex,
        }
        if topics is not None:
            filter_params["topics"] = topics

        broadcaster = P2PBroadcaster(
            rpc_urls=[rpc_url], socks5_proxy=socks5_proxy
        )
        raw_logs = broadcaster.rpc_call("eth_getLogs", [filter_params])
        events: list[Event] = []
        for log in raw_logs or []:
            log_topics = log.get("topics", [])
            event_topic = log_topics[0] if log_topics else ""
            events.append(
                Event(
                    contract_address=log.get("address", contract_address),
                    event_topic=event_topic,
                    topics=log_topics,
                    data=log.get("data", "0x"),
                    block_number=int(log.get("blockNumber", "0x0"), 16),
                    log_index=int(log.get("logIndex", "0x0"), 16),
                    transaction_hash=log.get("transactionHash"),
                )
            )
        return events

    def stream_chunk_events(self, chunk: Chunk | str) -> Iterator[Event]:
        """Yields deserialized Event objects from a single chunk."""
        decompressed = self.fetch_chunk_bytes(chunk)
        for line in decompressed.splitlines():
            line_str = line.strip()
            if not line_str:
                continue
            event_dict = json.loads(line_str.decode("utf-8"))
            yield Event.from_dict(event_dict)

    def stream_events(
        self,
        protocol_id: str,
        from_block: int | None = None,
        to_block: int | None = None,
        include_hot: bool = True,
    ) -> Iterator[Event]:
        """Streams events across chunks for a protocol within an optional block range.

        Args:
            protocol_id: Protocol identifier (e.g. 'tornado-cash-1-eth-0.1').
            from_block: Optional starting block height (inclusive).
            to_block: Optional ending block height (exclusive).
            include_hot: Whether to include the unsealed hotHead chunk at the tip.
        """
        proto = self.get_protocol(protocol_id)
        all_chunks = list(proto.chunks)
        if include_hot and proto.hot_head:
            all_chunks.append(proto.hot_head)

        for chunk in all_chunks:
            # Skip chunks completely outside requested range
            if to_block is not None and chunk.from_block >= to_block:
                continue
            if from_block is not None and chunk.to_block <= from_block:
                continue

            for event in self.stream_chunk_events(chunk):
                if from_block is not None and event.block_number < from_block:
                    continue
                if to_block is not None and event.block_number >= to_block:
                    continue
                yield event

    def export_sqlite(
        self,
        protocol_id: str,
        db_path: str,
        table_name: str | None = None,
        from_block: int | None = None,
        to_block: int | None = None,
        batch_size: int = 1000,
    ) -> int:
        """Exports protocol events into a SQLite database.

        Returns total count of events inserted.
        """
        table = table_name or protocol_id.replace("-", "_").replace(".", "_")
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS "{table}" (
                block_number INTEGER,
                log_index INTEGER,
                contract_address TEXT,
                event_topic TEXT,
                topics TEXT,
                data TEXT,
                PRIMARY KEY (block_number, log_index)
            )
            """
        )

        batch: list[tuple[Any, ...]] = []
        count = 0

        for event in self.stream_events(protocol_id, from_block, to_block):
            batch.append(
                (
                    event.block_number,
                    event.log_index,
                    event.contract_address,
                    event.event_topic,
                    json.dumps(event.topics),
                    event.data,
                )
            )
            if len(batch) >= batch_size:
                cur.executemany(
                    f"""
                    INSERT OR REPLACE INTO "{table}"
                    (block_number, log_index, contract_address, event_topic, topics, data)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    batch,
                )
                conn.commit()
                count += len(batch)
                batch = []

        if batch:
            cur.executemany(
                f"""
                INSERT OR REPLACE INTO "{table}"
                (block_number, log_index, contract_address, event_topic, topics, data)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                batch,
            )
            conn.commit()
            count += len(batch)

        conn.close()
        return count

    def export_csv(
        self,
        protocol_id: str,
        csv_path: str,
        from_block: int | None = None,
        to_block: int | None = None,
    ) -> int:
        """Exports protocol events into a CSV file.

        Returns total count of events written.
        """
        count = 0
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "block_number",
                    "log_index",
                    "contract_address",
                    "event_topic",
                    "topics",
                    "data",
                ]
            )
            for event in self.stream_events(protocol_id, from_block, to_block):
                writer.writerow(
                    [
                        event.block_number,
                        event.log_index,
                        event.contract_address,
                        event.event_topic,
                        json.dumps(event.topics),
                        event.data,
                    ]
                )
                count += 1
        return count
