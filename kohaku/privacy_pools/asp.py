"""Association Set Provider (ASP) integration for Privacy Pools compliance."""

from __future__ import annotations

from dataclasses import dataclass

from kohaku.crypto.poseidon import poseidon_hash2
from kohaku.merkle.tree import LeanIMT, MerkleProof


@dataclass
class AssociationSet:
    """Represents a curated association set (clean deposit roots) from an ASP (e.g. 0xBow) using LeanIMT."""

    asp_id: str
    root: int
    tree: LeanIMT

    @classmethod
    def from_deposits(cls, asp_id: str, clean_commitments: list[int]) -> AssociationSet:
        tree = LeanIMT(hash_fn=poseidon_hash2)
        tree.insert_batch(clean_commitments)
        return cls(asp_id=asp_id, root=tree.root(), tree=tree)

    def is_included(self, commitment: int) -> bool:
        """Checks if a commitment is part of this association set."""
        return commitment in self.tree.leaves

    def generate_proof(self, index: int) -> MerkleProof:
        """Generates an inclusion proof into the association set root."""
        return self.tree.generate_proof(index)
