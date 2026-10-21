from __future__ import annotations

import csv
import gzip
import hashlib
import json
import sqlite3
import urllib.error
import urllib.request
from collections.abc import Iterator
from typing import Any

from kohaku.sync.exceptions import (
    ChecksumMismatchError,
    ChunkDownloadError,
    ManifestError,
    ProtocolNotFoundError,
)
from kohaku.sync.models import Chunk, Event, Manifest, ProtocolInfo

DEFAULT_SAGA_URL = "https://saga.gordosoluciones.xyz"
USER_AGENT = "saga-sync-py/0.1.0"


class SagaClient:
    """Client for fetching and verifying blockchain event logs from a Saga CDN."""

    def __init__(
        self,
        base_url: str = DEFAULT_SAGA_URL,
        timeout: float = 30.0,
        verify_checksum: bool = True,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.verify_checksum = verify_checksum
        self._manifest: Manifest | None = None

    def _http_get(self, path_or_url: str) -> bytes:
        if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
            url = path_or_url
        else:
            url = f"{self.base_url}/{path_or_url.lstrip('/')}"

        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            raise ChunkDownloadError(
                f"HTTP {e.code} while fetching {url}: {e.reason}"
            ) from e
        except urllib.error.URLError as e:
            raise ChunkDownloadError(
                f"Network error while fetching {url}: {e.reason}"
            ) from e

    def get_manifest(self, force_refresh: bool = False) -> Manifest:
        """Fetches and parses the manifest (index.json)."""
        if self._manifest is not None and not force_refresh:
            return self._manifest

        try:
            raw_data = self._http_get("index.json")
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
        """Downloads a chunk file, decompresses it, and verifies its sha256 checksum."""
        if isinstance(chunk, str):
            filename = chunk
            expected_digest = None
        else:
            filename = chunk.file
            expected_digest = chunk.digest.data.lower()

        compressed = self._http_get(filename)
        decompressed = gzip.decompress(compressed)

        if self.verify_checksum and expected_digest:
            actual_digest = f"0x{hashlib.sha256(decompressed).hexdigest()}"
            if actual_digest != expected_digest:
                raise ChecksumMismatchError(filename, expected_digest, actual_digest)

        return decompressed

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
