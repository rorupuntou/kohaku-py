"""Tornado Cash zk-SNARK Groth16 circuit input generation and proof utilities."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any


@dataclass
class CircuitInputs:
    """Inputs required by the Tornado Cash Circom circuit to generate a Groth16 witness."""

    root: int
    nullifier_hash: int
    recipient: int
    relayer: int
    fee: int
    refund: int
    nullifier: int
    secret: int
    path_elements: list[int]
    path_indices: list[int]

    def to_dict(self) -> dict[str, Any]:
        """Converts inputs to string-formatted dictionary for snarkjs/circom witness calculators."""
        return {
            "root": str(self.root),
            "nullifierHash": str(self.nullifier_hash),
            "recipient": str(self.recipient),
            "relayer": str(self.relayer),
            "fee": str(self.fee),
            "refund": str(self.refund),
            "nullifier": str(self.nullifier),
            "secret": str(self.secret),
            "pathElements": [str(x) for x in self.path_elements],
            "pathIndices": [int(x) for x in self.path_indices],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


def solidity_proof_from_snarkjs(snarkjs_proof: dict[str, Any]) -> bytes:
    """Converts a standard SnarkJS Groth16 proof into the 256-byte Solidity format.

    Format expected by Tornado contract:
    [
        a.x, a.y,
        b.x[1], b.x[0],
        b.y[1], b.y[0],
        c.x, c.y
    ]
    Each element encoded as 32-byte big-endian uint256.
    """
    pi_a = snarkjs_proof["pi_a"]
    pi_b = snarkjs_proof["pi_b"]
    pi_c = snarkjs_proof["pi_c"]

    elements = [
        int(pi_a[0]),
        int(pi_a[1]),
        # Order of B elements are reversed to match Solidity contract expectation:
        int(pi_b[0][1]),
        int(pi_b[0][0]),
        int(pi_b[1][1]),
        int(pi_b[1][0]),
        int(pi_c[0]),
        int(pi_c[1]),
    ]

    out = bytearray()
    for elem in elements:
        out.extend(elem.to_bytes(32, "big"))
    return bytes(out)
