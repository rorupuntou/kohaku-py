"""Groth16 BN254 / BN128 Proof Codec for Tornado Cash and Ethereum EVM.

Normalizes elliptic curve points for G1 and G2 and packs them into the canonical
256-byte ABI-encoded layout expected by Tornado Cash Verifier.sol:
- A  in G1: 64 bytes (X, Y)
- B  in G2: 128 bytes (X [c1, c0], Y [c1, c0] with real/imag coordinate order for EVM)
- C  in G1: 64 bytes (X, Y)
Total: 256 bytes (8 words of 32 bytes)
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union


def pad32(val: Union[str, int, bytes]) -> str:
    """Ensures a 256-bit scalar / public input is exactly 32 bytes (64 hex characters with 0x prefix)."""
    if isinstance(val, int):
        h = f"{val:064x}"
    elif isinstance(val, bytes):
        h = val.hex().zfill(64)
    else:
        s = str(val).strip()
        h = s[2:] if s.startswith("0x") else s
        h = h.zfill(64)
    return "0x" + h.lower()


def pad64(val: Union[str, bytes]) -> str:
    """Ensures a G1 point (X, Y) is exactly 64 bytes (128 hex characters with 0x prefix)."""
    if isinstance(val, bytes):
        h = val.hex().zfill(128)
    else:
        s = str(val).strip()
        h = s[2:] if s.startswith("0x") else s
        h = h.zfill(128)
    return "0x" + h.lower()


def pad128(val: Union[str, bytes]) -> str:
    """Ensures a G2 point is exactly 128 bytes (256 hex characters with 0x prefix)."""
    if isinstance(val, bytes):
        h = val.hex().zfill(256)
    else:
        s = str(val).strip()
        h = s[2:] if s.startswith("0x") else s
        h = h.zfill(256)
    return "0x" + h.lower()


@dataclass
class Groth16Proof:
    """Canonical Groth16 zk-SNARK proof on BN254 / BN128."""

    a_hex: str  # 64 bytes hex
    b_hex: str  # 128 bytes hex
    c_hex: str  # 64 bytes hex

    def __post_init__(self) -> None:
        self.a_hex = pad64(self.a_hex)
        self.b_hex = pad128(self.b_hex)
        self.c_hex = pad64(self.c_hex)

    def to_bytes(self) -> bytes:
        """Concatenate A + B + C into exactly 256 bytes for Solidity bytes calldata."""
        raw_a = bytes.fromhex(self.a_hex[2:])
        raw_b = bytes.fromhex(self.b_hex[2:])
        raw_c = bytes.fromhex(self.c_hex[2:])
        return raw_a + raw_b + raw_c

    def to_hex(self) -> str:
        """Returns 0x-prefixed 512-hex-character string (256 bytes)."""
        return "0x" + self.to_bytes().hex()

    @classmethod
    def from_bytes(cls, raw: bytes) -> Groth16Proof:
        """Parse 256 bytes into a Groth16Proof."""
        if len(raw) != 256:
            raise ValueError(f"Expected 256 bytes for Groth16 proof, got {len(raw)}")
        return cls(
            a_hex="0x" + raw[0:64].hex(),
            b_hex="0x" + raw[64:192].hex(),
            c_hex="0x" + raw[192:256].hex(),
        )

    @classmethod
    def from_hex(cls, hex_str: str) -> Groth16Proof:
        clean = hex_str.strip()
        if clean.startswith("0x"):
            clean = clean[2:]
        return cls.from_bytes(bytes.fromhex(clean))

    @classmethod
    def from_snarkjs_dict(cls, data: Dict[str, Any]) -> Groth16Proof:
        """Parse from snarkjs proof.json format (pi_a, pi_b, pi_c)."""
        proof = data.get("proof", data)
        pi_a = proof["pi_a"]
        pi_b = proof["pi_b"]
        pi_c = proof["pi_c"]

        # G1: [X, Y]
        ax = int(pi_a[0])
        ay = int(pi_a[1])
        a_hex = f"{ax:064x}{ay:064x}"

        # G2: EVM Verifier.sol expects [X1_real, X0_imag, Y1_real, Y0_imag]
        # Snarkjs pi_b layout is [[imag, real], [imag, real]]
        bx_real = int(pi_b[0][1])
        bx_imag = int(pi_b[0][0])
        by_real = int(pi_b[1][1])
        by_imag = int(pi_b[1][0])
        b_hex = f"{bx_real:064x}{bx_imag:064x}{by_real:064x}{by_imag:064x}"

        # G1: [X, Y]
        cx = int(pi_c[0])
        cy = int(pi_c[1])
        c_hex = f"{cx:064x}{cy:064x}"

        return cls(a_hex="0x" + a_hex, b_hex="0x" + b_hex, c_hex="0x" + c_hex)

    @classmethod
    def from_arkworks_dict(cls, data: Dict[str, Any]) -> Groth16Proof:
        """Parse from arkworks json format (a, b, c hex strings)."""
        p = data.get("proof", data)
        if "proof" in p and isinstance(p["proof"], dict):
            p = p["proof"]
        return cls(
            a_hex=p["a"],
            b_hex=p["b"],
            c_hex=p["c"],
        )

    @classmethod
    def mock(cls) -> Groth16Proof:
        """Generate a deterministic synthetic 256-byte Groth16 proof for dry-runs / offline simulation."""
        a = "0x" + ("01" * 64)
        b = "0x" + ("02" * 128)
        c = "0x" + ("03" * 64)
        return cls(a_hex=a, b_hex=b, c_hex=c)
