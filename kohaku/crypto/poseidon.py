"""Poseidon hash function for Privacy Pools (BN254 curve)."""

from __future__ import annotations

from circomlibpy.poseidon import PoseidonHash

_poseidon_instance = PoseidonHash()


def poseidon_hash(elements: list[int] | tuple[int, ...]) -> int:
    """Computes the Poseidon hash over a sequence of field elements (matching Circomlib / Privacy Pools)."""
    n = len(elements)
    if n == 0:
        raise ValueError("Cannot hash empty sequence with Poseidon")
    return _poseidon_instance.hash(n, list(elements))


def poseidon_hash2(left: int, right: int) -> int:
    """Hashes two field elements using Poseidon (Merkle tree branch hash for Privacy Pools)."""
    return _poseidon_instance.hash(2, [left, right])
