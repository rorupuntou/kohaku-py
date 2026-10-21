"""Tornado Cash vault and Merkle state synchronizer."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from kohaku.merkle.tree import MerkleProof, MerkleTree
from kohaku.sync.client import SagaClient
from kohaku.tornado.note import TornadoNote
from kohaku.tornado.pools import ALL_POOLS, TornadoPool, get_pool

DEPOSIT_TOPIC = "0xa945e51eec50ab98c161376f0db4cf2aeba3ec92755fe2fcd388bdbbb80ff196"
WITHDRAWAL_TOPIC = "0xe9e508bad6d4c3227e881ca19068f099da81b5164dd6d62b2eaf1e8bc6c34931"


class TornadoVault:
    """Manages note scanning, state synchronization, and Merkle tree reconstruction

    for a Tornado Cash pool using Saga CDN snapshots.
    """

    def __init__(self, pool_id_or_pool: str | TornadoPool, client: SagaClient | None = None):
        if isinstance(pool_id_or_pool, str):
            self.pool = get_pool(pool_id_or_pool)
        else:
            self.pool = pool_id_or_pool

        self.client = client or SagaClient()
        self._tree: MerkleTree | None = None
        self.commitments: list[int] = []
        self._commitments_set: set[int] = set()
        self.spent_nullifiers: set[int] = set()
        self.synced = False

    def sync(self, on_chunk: Callable[[str, int, int], None] | None = None) -> None:
        """Synchronizes all historical deposits and withdrawals for this pool from Saga CDN.

        Fast I/O and index collection without computing millions of intermediate Merkle hashes.
        """
        self.commitments.clear()
        self._commitments_set.clear()
        self.spent_nullifiers.clear()
        self._tree = None

        proto = self.client.get_protocol(self.pool.id)
        all_chunks = list(proto.chunks)
        if proto.hot_head:
            all_chunks.append(proto.hot_head)

        total_chunks = len(all_chunks)

        for idx, chunk in enumerate(all_chunks, 1):
            if on_chunk:
                on_chunk(chunk.file, idx, total_chunks)

            for event in self.client.stream_chunk_events(chunk):
                topic = event.event_topic.lower()

                if topic == DEPOSIT_TOPIC:
                    # topics[1] is the commitment
                    if len(event.topics) > 1:
                        comm_hex = event.topics[1]
                        comm_int = int(comm_hex, 16)
                        self.commitments.append(comm_int)
                        self._commitments_set.add(comm_int)

                elif topic == WITHDRAWAL_TOPIC:
                    # In Tornado withdrawal: data contains to (32B), nullifierHash (32B), fee (32B)
                    data_hex = event.data
                    if data_hex.startswith("0x"):
                        data_hex = data_hex[2:]
                    if len(data_hex) >= 128:  # 64 hex chars * 2 = 128
                        nullifier_hex = "0x" + data_hex[64:128]
                        self.spent_nullifiers.add(int(nullifier_hex, 16))

        self.synced = True

    @property
    def tree(self) -> MerkleTree:
        """Lazily builds the full Merkle Tree only when required."""
        if not self.synced:
            self.sync()
        if self._tree is None:
            self._tree = MerkleTree(height=20)
            self._tree.insert_batch(self.commitments)
        return self._tree

    def get_root(self) -> int:
        return self.tree.root()

    def check_note(
        self,
        note: TornadoNote,
        on_chunk: Callable[[str, int, int], None] | None = None,
        build_proof: bool = False,
    ) -> dict[str, Any]:
        """Checks on-chain status of a note: mined index, spent status, and optional Merkle proof."""
        if not self.synced:
            self.sync(on_chunk=on_chunk)

        comm = note.commitment
        null_h = note.nullifier_hash

        is_mined = comm in self._commitments_set
        leaf_index = self.commitments.index(comm) if is_mined else None
        proof: MerkleProof | None = None

        if is_mined and build_proof and leaf_index is not None:
            proof = self.tree.generate_proof(leaf_index)

        is_spent = null_h in self.spent_nullifiers

        return {
            "mined": is_mined,
            "leaf_index": leaf_index,
            "spent": is_spent,
            "spendable": is_mined and not is_spent,
            "commitment": note.commitment_hex,
            "nullifier_hash": note.nullifier_hash_hex,
            "total_deposits": len(self.commitments),
            "total_withdrawals": len(self.spent_nullifiers),
            "merkle_proof": proof,
        }
