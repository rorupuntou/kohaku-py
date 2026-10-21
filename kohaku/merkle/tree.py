"""Generic binary Merkle Tree implementation for privacy protocols (Tornado Cash & Privacy Pools)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from kohaku.crypto.mimc import TORNADO_ZERO_VALUE, mimc_hash2


@dataclass(frozen=True)
class MerkleProof:
    index: int
    root: int
    leaf: int
    siblings: list[int]
    path_indices: list[int]  # 0 for left child, 1 for right child

    def verify(self, hash_fn: Callable[[int, int], int] = mimc_hash2) -> bool:
        """Verifies that the proof path correctly computes the root from the leaf."""
        current = self.leaf
        for sibling, path_idx in zip(self.siblings, self.path_indices, strict=True):
            if path_idx == 0:
                current = hash_fn(current, sibling)
            else:
                current = hash_fn(sibling, current)
        return current == self.root


class MerkleTree:
    """Fixed-depth binary Merkle Tree matching on-chain contracts.

    Supports incremental leaf insertion, precomputed zero branches, and
    Merkle proof generation for ZK-SNARK provers.
    """

    def __init__(
        self,
        height: int = 20,
        hash_fn: Callable[[int, int], int] = mimc_hash2,
        zero_value: int = TORNADO_ZERO_VALUE,
    ):
        self.height = height
        self.hash_fn = hash_fn
        self.zero_value = zero_value

        # Precompute zero values for each level
        self.zeros: list[int] = [zero_value]
        for i in range(height):
            self.zeros.append(self.hash_fn(self.zeros[i], self.zeros[i]))

        # Storage for populated nodes per level: level -> {index: hash}
        self.layers: list[dict[int, int]] = [{} for _ in range(height + 1)]
        self.next_index = 0

    @property
    def capacity(self) -> int:
        return 1 << self.height

    def insert(self, leaf: int) -> int:
        """Inserts a single leaf into the next free slot and returns its leaf index."""
        if self.next_index >= self.capacity:
            raise OverflowError(f"Merkle tree is full (capacity {self.capacity})")

        index = self.next_index
        self.layers[0][index] = leaf

        current_idx = index
        current_hash = leaf

        for level in range(self.height):
            is_right = (current_idx % 2) == 1
            sibling_idx = current_idx - 1 if is_right else current_idx + 1

            # Fetch sibling hash (or default zero for this level)
            sibling_hash = self.layers[level].get(
                sibling_idx, self.zeros[level]
            )

            parent_idx = current_idx // 2
            if is_right:
                current_hash = self.hash_fn(sibling_hash, current_hash)
            else:
                current_hash = self.hash_fn(current_hash, sibling_hash)

            self.layers[level + 1][parent_idx] = current_hash
            current_idx = parent_idx

        self.next_index += 1
        return index

    def insert_batch(self, leaves: list[int]) -> list[int]:
        """Inserts multiple leaves in batch and returns their indices."""
        indices = []
        for leaf in leaves:
            indices.append(self.insert(leaf))
        return indices

    def root(self) -> int:
        """Computes or returns the current Merkle root."""
        return self.layers[self.height].get(0, self.zeros[self.height])

    def generate_proof(self, index: int) -> MerkleProof:
        """Generates a Merkle membership proof for the leaf at `index`."""
        if index < 0 or index >= self.next_index:
            raise IndexError(f"Leaf index {index} out of bounds (0..{self.next_index})")

        leaf = self.layers[0].get(index, self.zeros[0])
        siblings: list[int] = []
        path_indices: list[int] = []

        current_idx = index
        for level in range(self.height):
            is_right = (current_idx % 2) == 1
            sibling_idx = current_idx - 1 if is_right else current_idx + 1

            sibling_hash = self.layers[level].get(
                sibling_idx, self.zeros[level]
            )
            siblings.append(sibling_hash)
            path_indices.append(1 if is_right else 0)

            current_idx //= 2

        return MerkleProof(
            index=index,
            root=self.root(),
            leaf=leaf,
            siblings=siblings,
            path_indices=path_indices,
        )
