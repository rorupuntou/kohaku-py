"""Privacy Pools note derivation and commitment hashing using Poseidon."""

from __future__ import annotations

import os
from dataclasses import dataclass

from kohaku.crypto.bn254 import to_field
from kohaku.crypto.poseidon import poseidon_hash


@dataclass
class PrivacyPoolNote:
    """A Privacy Pools deposit note supporting arbitrary amounts and association sets."""

    value: int  # amount in base units (e.g. wei)
    label: int  # pool or asset label (default: 0)
    precommitment: int  # private secret scalar
    nullifier: int  # nullifier secret scalar
    leaf_index: int | None = None
    spent: bool = False

    @property
    def commitment(self) -> int:
        """Computes the on-chain commitment: poseidon([value, label, precommitment])."""
        return poseidon_hash([self.value, self.label, self.precommitment])

    @property
    def commitment_hex(self) -> str:
        return f"0x{self.commitment:064x}"

    @property
    def nullifier_hash(self) -> int:
        """Computes the nullifier hash revealed on withdrawal: poseidon([nullifier, precommitment])."""
        return poseidon_hash([self.nullifier, self.precommitment])

    @property
    def nullifier_hash_hex(self) -> str:
        return f"0x{self.nullifier_hash:064x}"

    @classmethod
    def create(cls, value: int, label: int = 0) -> PrivacyPoolNote:
        """Generates a fresh random note for Privacy Pools."""
        precommit_bytes = os.urandom(31)
        nullifier_bytes = os.urandom(31)
        precommitment = to_field(int.from_bytes(precommit_bytes, "big"))
        nullifier = to_field(int.from_bytes(nullifier_bytes, "big"))
        return cls(
            value=value,
            label=label,
            precommitment=precommitment,
            nullifier=nullifier,
        )
