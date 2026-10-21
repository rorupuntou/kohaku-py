"""Privacy Pools vault state synchronizer using Saga CDN events."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from kohaku.crypto.poseidon import poseidon_hash2
from kohaku.merkle.tree import MerkleProof, MerkleTree
from kohaku.privacy_pools.note import PrivacyPoolNote
from kohaku.privacy_pools.pools import PrivacyPool, get_privacy_pool
from kohaku.sync.client import SagaClient

DEPOSITED_TOPIC = "0xe3b53cd1a44fbf11535e145d80b8ef1ed6d57a73bf5daa7e939b6b01657d6549"
WITHDRAWN_TOPIC = "0x75e161b3e824b114fc1a33274bd7091918dd4e639cede50b78b15a4eea956a21"
RAGEQUIT_TOPIC = "0xd2b3e868ae101106371f2bd93abc8d5a4de488b9fe47ed122c23625aa7172f13"


class PrivacyPoolsVault:
    """Manages state synchronization, note tracking, and Merkle tree generation

    for 0xBow Privacy Pools using Saga CDN.
    """

    def __init__(self, pool_id_or_pool: str | PrivacyPool = "privacy-pools-1-eth", client: SagaClient | None = None):
        if isinstance(pool_id_or_pool, str):
            self.pool = get_privacy_pool(pool_id_or_pool)
        else:
            self.pool = pool_id_or_pool

        self.client = client or SagaClient()
        self.commitments: list[int] = []
        self._commitments_set: set[int] = set()
        self.commitments_to_amounts: dict[int, int] = {}
        self.spent_nullifiers: set[int] = set()
        self.synced = False
        self._tree: MerkleTree | None = None

    def sync(self, on_chunk: Callable[[str, int, int], None] | None = None) -> None:
        """Streams deposits and withdrawals from Saga CDN into memory sets."""
        self.commitments.clear()
        self._commitments_set.clear()
        self.commitments_to_amounts.clear()
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

                if topic == DEPOSITED_TOPIC:
                    # Deposited(address depositor, uint256 leaf, uint256 precommitment, uint256 amount, uint256 index)
                    raw = bytes.fromhex(event.data[2:])
                    if len(raw) >= 96:
                        leaf = int.from_bytes(raw[0:32], "big")
                        amount = int.from_bytes(raw[64:96], "big")
                        self.commitments.append(leaf)
                        self._commitments_set.add(leaf)
                        self.commitments_to_amounts[leaf] = amount

                elif topic == WITHDRAWN_TOPIC:
                    # Withdrawn(address recipient, uint256 amount, uint256 nullifier, uint256 fee)
                    raw = bytes.fromhex(event.data[2:])
                    if len(raw) >= 64:
                        nullifier_hash = int.from_bytes(raw[32:64], "big")
                        self.spent_nullifiers.add(nullifier_hash)

                elif topic == RAGEQUIT_TOPIC:
                    raw = bytes.fromhex(event.data[2:])
                    if len(raw) >= 32:
                        leaf = int.from_bytes(raw[0:32], "big")
                        # Nullify by tracking spent leaf
                        self.spent_nullifiers.add(leaf)

        self.synced = True

    def check_note(
        self, note: PrivacyPoolNote, on_chunk: Callable[[str, int, int], None] | None = None
    ) -> dict[str, Any]:
        """Fast O(1) membership check for a note."""
        if not self.synced:
            self.sync(on_chunk=on_chunk)

        comm = note.commitment
        is_mined = comm in self._commitments_set
        leaf_index = self.commitments.index(comm) if is_mined else None
        is_spent = note.nullifier_hash in self.spent_nullifiers

        return {
            "commitment": note.commitment_hex,
            "nullifier_hash": note.nullifier_hash_hex,
            "mined": is_mined,
            "leaf_index": leaf_index,
            "spent": is_spent,
            "spendable": is_mined and not is_spent,
            "total_deposits": len(self.commitments),
            "total_withdrawals": len(self.spent_nullifiers),
        }

    def tree(self) -> MerkleTree:
        """Builds or returns cached 20-level Poseidon Merkle tree."""
        if not self.synced:
            self.sync()

        if self._tree is None:
            t = MerkleTree(height=20, hash_fn=poseidon_hash2, zero_value=0)
            for leaf in self.commitments:
                t.insert(leaf)
            self._tree = t
        return self._tree

    def get_merkle_proof(self, leaf_index: int) -> MerkleProof:
        return self.tree().generate_proof(leaf_index)
