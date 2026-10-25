"""Railgun 0zk Bech32m address encoding and decoding.

Adapted from the pure-Python Bech32 polynomial engine in `bitcoin_satoshi2/segwit_engine.py`,
upgraded to Bech32m (`0x2bc830a3`) with the `"0zk"` human-readable prefix used by Railgun.
"""

from __future__ import annotations

from dataclasses import dataclass

CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
BECH32M_CONST = 0x2BC830A3
ALL_CHAINS_XOR_MASK = 0xFFFFFFFFFFFFFFFF


def _bech32_polymod(values: list[int]) -> int:
    generator = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]
    chk = 1
    for value in values:
        top = chk >> 25
        chk = ((chk & 0x1FFFFFF) << 5) ^ value
        for i in range(5):
            chk ^= generator[i] if ((top >> i) & 1) else 0
    return chk


def _bech32_hrp_expand(hrp: str) -> list[int]:
    return [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]


def _bech32m_create_checksum(hrp: str, data: list[int]) -> list[int]:
    values = _bech32_hrp_expand(hrp) + data
    polymod = _bech32_polymod(values + [0, 0, 0, 0, 0, 0]) ^ BECH32M_CONST
    return [(polymod >> 5 * (5 - i)) & 31 for i in range(6)]


def _bech32m_verify_checksum(hrp: str, data: list[int]) -> bool:
    return _bech32_polymod(_bech32_hrp_expand(hrp) + data) == BECH32M_CONST


def _convertbits(data: bytes | list[int], frombits: int, tobits: int, pad: bool = True) -> list[int]:
    acc = 0
    bits = 0
    ret: list[int] = []
    maxv = (1 << tobits) - 1
    max_acc = (1 << (frombits + tobits - 1)) - 1
    for value in data:
        if value < 0 or (value >> frombits):
            raise ValueError("Invalid bit group value")
        acc = ((acc << frombits) | value) & max_acc
        bits += frombits
        while bits >= tobits:
            bits -= tobits
            ret.append((acc >> bits) & maxv)
    if pad:
        if bits:
            ret.append((acc << (tobits - bits)) & maxv)
    elif bits >= frombits or ((acc << (tobits - bits)) & maxv):
        raise ValueError("Invalid incomplete bit group padding")
    return ret


def encode_network_id(chain_type: int | None, chain_id: int | None) -> bytes:
    """Encodes `(chain_type, chain_id)` into the 8-byte XOR-masked Railgun network block."""
    if chain_type is None or chain_id is None:
        return (0).to_bytes(8, "big")
    raw = ((chain_type & 0xFF) << 56) | (chain_id & 0x00FFFFFFFFFFFFFF)
    masked = raw ^ ALL_CHAINS_XOR_MASK
    return masked.to_bytes(8, "big")


def decode_network_id(net_bytes: bytes) -> tuple[int | None, int | None]:
    """Decodes the 8-byte XOR-masked Railgun network block into `(chain_type, chain_id)`."""
    if len(net_bytes) != 8:
        raise ValueError("Railgun network block must be 8 bytes")
    val = int.from_bytes(net_bytes, "big")
    if val == 0:
        return None, None
    unmasked = val ^ ALL_CHAINS_XOR_MASK
    chain_type = (unmasked >> 56) & 0xFF
    chain_id = unmasked & 0x00FFFFFFFFFFFFFF
    return chain_type, chain_id


@dataclass(frozen=True)
class RailgunAddress:
    """Represents a Railgun `0zk1...` Bech32m shielded address (73-byte payload)."""

    master_public_key: int
    viewing_public_key: bytes
    chain_type: int | None = 0
    chain_id: int | None = 1
    version: int = 1

    def to_payload_bytes(self) -> bytes:
        if len(self.viewing_public_key) != 32:
            raise ValueError("viewing_public_key must be exactly 32 bytes")
        ver_byte = bytes([self.version & 0xFF])
        mpk_bytes = self.master_public_key.to_bytes(32, "big")
        net_bytes = encode_network_id(self.chain_type, self.chain_id)
        return ver_byte + mpk_bytes + net_bytes + self.viewing_public_key

    def to_0zk(self, hrp: str = "0zk") -> str:
        payload = self.to_payload_bytes()
        five_bit = _convertbits(payload, 8, 5, pad=True)
        checksum = _bech32m_create_checksum(hrp, five_bit)
        return hrp + "1" + "".join(CHARSET[d] for d in (five_bit + checksum))

    @classmethod
    def from_0zk(cls, addr: str) -> RailgunAddress:
        clean = addr.strip().lower()
        pos = clean.rfind("1")
        if pos < 1 or pos + 7 > len(clean):
            raise ValueError(f"Invalid Railgun 0zk address format: {addr}")
        hrp = clean[:pos]
        if hrp != "0zk":
            raise ValueError(f"Invalid Railgun HRP '{hrp}', expected '0zk'")
        data = [CHARSET.find(c) for c in clean[pos + 1 :]]
        if any(d == -1 for d in data):
            raise ValueError("Invalid character in Bech32m address")
        if not _bech32m_verify_checksum(hrp, data):
            raise ValueError("Invalid Bech32m checksum in Railgun address")
        raw_bytes = bytes(_convertbits(data[:-6], 5, 8, pad=False))
        if len(raw_bytes) != 73:
            raise ValueError(f"Expected 73-byte Railgun payload, got {len(raw_bytes)} bytes")
        version = raw_bytes[0]
        mpk = int.from_bytes(raw_bytes[1:33], "big")
        chain_type, chain_id = decode_network_id(raw_bytes[33:41])
        vpk = raw_bytes[41:73]
        return cls(
            master_public_key=mpk,
            viewing_public_key=vpk,
            chain_type=chain_type,
            chain_id=chain_id,
            version=version,
        )
