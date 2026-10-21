"""Privacy Pools vault state synchronizer using Poseidon Merkle trees."""

from __future__ import annotations

from typing import Any

from kohaku.crypto.poseidon import poseidon_hash2
from kohaku.merkle.tree import MerkleProof, MerkleTree
from kohaku.privacy_pools.note import PrivacyPoolNote
from kohaku.sync.client import SagaClient


class PrivacyPoolsVault:
    """Manages state synchronization and Poseidon Merkle tree verification

    for Privacy Pools (e.g. privacy-pools-1-eth).
    """

    def __init__(self, protocol_id: str = "privacy-pools-1-eth", client: SagaClient | None = None):
        self.protocol_id = protocol_id
        self.client = client or SagaClient()
        self.tree = MerkleTree(height=20, hash_fn=poseidon_hash2, zero_value=0)
        self.commitments: list[int] = []
        self.synced = False

    def sync(self) -> None:
        """Streams deposits from Saga CDN and populates the Poseidon Merkle Tree."""
        self.tree = MerkleTree(height=20, hash_fn=poseidon_hash2, zero_value=0)
        self.commitments.clear()

        for event in self.client.stream_events(self.protocol_id):
            # Extract commitment from event (first topic or data payload depending on contract ABI)
            if len(event.topics) > 1:
                comm_int = int(event.topics[1], 16)
                self.commitments.append(comm_int)
                self.tree.insert(comm_int)

        self.synced = True

    def get_root(self) -> int:
        if not self.synced:
            self.sync()
        return self.tree.root()

    def check_note(self, note: PrivacyPoolNote) -> dict[str, Any]:
        if not self.synced:
            self.sync()

        comm = note.commitment
        is_mined = comm in self.commitments
        leaf_index = self.commitments.index(comm) if is_mined else None
        proof: MerkleProof | None = (
            self.tree.generate_proof(leaf_index) if leaf_index is not None else None
        )

        return {
            "mined": is_mined,
            "leaf_index": leaf_index,
            "commitment": note.commitment_hex,
            "merkle_proof": proof,
            "root": hex(self.tree.root()),
        }
