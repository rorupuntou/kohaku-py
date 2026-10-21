"""Tornado Cash note derivation, serialization, and commitment hashing."""

from __future__ import annotations

import os
from dataclasses import dataclass

from kohaku.crypto.bn254 import to_field
from kohaku.crypto.mimc import mimc_sponge


@dataclass
class TornadoNote:
    currency: str
    amount: str
    chain_id: int
    nullifier: bytes
    secret: bytes
    leaf_index: int | None = None
    spent: bool = False

    def __post_init__(self) -> None:
        if len(self.nullifier) != 31:
            raise ValueError(f"Nullifier must be 31 bytes, got {len(self.nullifier)}")
        if len(self.secret) != 31:
            raise ValueError(f"Secret must be 31 bytes, got {len(self.secret)}")

    @property
    def commitment(self) -> int:
        """Computes the on-chain deposit commitment: mimc_sponge([nullifier, secret])."""
        nullifier_int = int.from_bytes(self.nullifier, byteorder="big")
        secret_int = int.from_bytes(self.secret, byteorder="big")
        return mimc_sponge([to_field(nullifier_int), to_field(secret_int)])

    @property
    def commitment_hex(self) -> str:
        return f"0x{self.commitment:064x}"

    @property
    def nullifier_hash(self) -> int:
        """Computes the on-chain nullifier hash revealed on withdrawal: mimc_sponge([nullifier])."""
        nullifier_int = int.from_bytes(self.nullifier, byteorder="big")
        return mimc_sponge([to_field(nullifier_int)])

    @property
    def nullifier_hash_hex(self) -> str:
        return f"0x{self.nullifier_hash:064x}"

    def to_note_string(self) -> str:
        """Formats the note in standard Tornado Cash URI string format:

        tornado-<currency>-<amount>-<chainId>-0x<nullifier><secret>
        """
        combined = (self.nullifier + self.secret).hex()
        return f"tornado-{self.currency.lower()}-{self.amount}-{self.chain_id}-0x{combined}"

    @classmethod
    def from_note_string(cls, note_str: str) -> TornadoNote:
        """Parses a standard Tornado Cash note string."""
        parts = note_str.strip().split("-")
        if len(parts) != 5 or parts[0] != "tornado":
            raise ValueError(
                f"Invalid note format. Expected 'tornado-<currency>-<amount>-<chainId>-0x<hex>', got: {note_str}"
            )

        currency = parts[1].upper()
        amount = parts[2]
        chain_id = int(parts[3])
        raw_hex = parts[4]
        if raw_hex.startswith("0x") or raw_hex.startswith("0X"):
            raw_hex = raw_hex[2:]

        data = bytes.fromhex(raw_hex)
        if len(data) != 62:
            raise ValueError(f"Expected 62 bytes (31 nullifier + 31 secret), got {len(data)}")

        nullifier = data[:31]
        secret = data[31:]

        return cls(
            currency=currency,
            amount=amount,
            chain_id=chain_id,
            nullifier=nullifier,
            secret=secret,
        )

    @classmethod
    def create(cls, currency: str = "ETH", amount: str = "0.1", chain_id: int = 1) -> TornadoNote:
        """Generates a new secure random note."""
        nullifier = os.urandom(31)
        secret = os.urandom(31)
        return cls(
            currency=currency.upper(),
            amount=str(amount),
            chain_id=chain_id,
            nullifier=nullifier,
            secret=secret,
        )
