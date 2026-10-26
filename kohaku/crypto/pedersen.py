"""Circomlib-compatible Pedersen Hash over BabyJubJub twisted Edwards curve (`BN254` scalar field).

Matches `kohaku-rs` (`crates/tornadocash/src/crypto/pedersen.rs` & `babyjubjub.rs`) and `circomlib`
bit-for-bit without external native dependencies:
- Generator points `PedersenGenerator_{s:032}_{try:032}` derived via BLAKE-256 (SHA-3 finalist).
- 200-bit segments (50 signed 4-bit windows per segment).
- Returns the affine `x`-coordinate (`Fr`) of the accumulated BabyJubJub point.
"""

from __future__ import annotations

import struct

from kohaku.crypto.bn254 import P

# BabyJubJub twisted Edwards curve parameters over BN254 scalar field P:
# A * x^2 + y^2 = 1 + D * x^2 * y^2 (mod P)
BABYJUB_A: int = 168_700
BABYJUB_D: int = 168_696
BABYJUB_ORDER: int = (
    21888242871839275222246405745257275088614511777268538073601725287587578984328
)
BABYJUB_SUBORDER: int = BABYJUB_ORDER >> 3

WINDOW_SIZE: int = 4
N_WINDOWS_PER_SEGMENT: int = 50
BITS_PER_SEGMENT: int = WINDOW_SIZE * N_WINDOWS_PER_SEGMENT  # 200 bits

# Precomputed first 4 circomlib Pedersen generator points (x, y) after cofactor clearing (* 8)
# for instant O(1) lookup on 31-byte nullifiers (1 segment) and 62-byte preimages (3 segments).
_BASE_POINT_CACHE: dict[int, tuple[int, int]] = {
    0: (
        10457101036533406547632367118273992217979173478358440826365724437999023779287,
        19824078218392094440610104313265183977899662750282163392862422243483260492317,
    ),
    1: (
        2671756056509184035029146175565761955751135805354291559563293617232983272177,
        2663205510731142763556352975002641716101654201788071096152948830924149045094,
    ),
    2: (
        5802099305472655231388284418920769829666717045250560929368476121199858275951,
        5980429700218124965372158798884772646841287887664001482443826541541529227896,
    ),
    3: (
        7107336197374528537877327281242680114152313102022415488494307685842428166594,
        2857869773864086953506483169737724679646433914307247183624878062391496185654,
    ),
}

# ---------------------------------------------------------------------------
# Pure-Python BLAKE-256 (SHA-3 finalist used by circomlib PedersenGenerator)
# ---------------------------------------------------------------------------

_BLAKE256_IV = (
    0x6A09E667,
    0xBB67AE85,
    0x3C6EF372,
    0xA54FF53A,
    0x510E527F,
    0x9B05688C,
    0x1F83D9AB,
    0x5BE0CD19,
)

_BLAKE256_CONST = (
    0x243F6A88,
    0x85A308D3,
    0x13198A2E,
    0x03707344,
    0xA4093822,
    0x299F31D0,
    0x082EFA98,
    0xEC4E6C89,
    0x452821E6,
    0x38D01377,
    0xBE5466CF,
    0x34E90C6C,
    0xC0AC29B7,
    0xC97C50DD,
    0x3F84D5B5,
    0xB5470917,
)

_BLAKE256_SIGMA = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15),
    (14, 10, 4, 8, 9, 15, 13, 6, 1, 12, 0, 2, 11, 7, 5, 3),
    (11, 8, 12, 0, 5, 2, 15, 13, 10, 14, 3, 6, 7, 1, 9, 4),
    (7, 9, 3, 1, 13, 12, 11, 14, 2, 6, 5, 10, 4, 0, 15, 8),
    (9, 0, 5, 7, 2, 4, 10, 15, 14, 1, 11, 12, 6, 8, 3, 13),
    (2, 12, 6, 10, 0, 11, 8, 3, 4, 13, 7, 5, 15, 14, 1, 9),
    (12, 5, 1, 15, 14, 13, 4, 10, 0, 7, 6, 3, 9, 2, 8, 11),
    (13, 11, 7, 14, 12, 1, 3, 9, 5, 0, 15, 4, 8, 6, 2, 10),
    (6, 15, 14, 9, 11, 3, 0, 8, 12, 2, 13, 7, 1, 4, 10, 5),
    (10, 2, 8, 4, 7, 6, 1, 5, 15, 11, 9, 14, 3, 12, 13, 0),
)


def _rotr32(x: int, n: int) -> int:
    return ((x >> n) | ((x << (32 - n)) & 0xFFFFFFFF)) & 0xFFFFFFFF


def blake256(data: bytes) -> bytes:
    """Computes the 32-byte BLAKE-256 digest of `data`."""
    h = list(_BLAKE256_IV)
    bit_len = len(data) * 8
    msg = bytearray(data)
    msg.append(0x80)
    while (len(msg) % 64) != 56:
        msg.append(0x00)
    msg[-1] |= 0x01
    msg.extend(struct.pack(">Q", bit_len))

    for blk_idx in range(0, len(msg), 64):
        block = msg[blk_idx : blk_idx + 64]
        m = list(struct.unpack(">16I", block))
        end_byte = blk_idx + 64
        if bit_len == 0 or (blk_idx * 8 >= bit_len):
            t0 = t1 = 0
        elif end_byte * 8 <= bit_len:
            t = end_byte * 8
            t0, t1 = t & 0xFFFFFFFF, (t >> 32) & 0xFFFFFFFF
        else:
            t0, t1 = bit_len & 0xFFFFFFFF, (bit_len >> 32) & 0xFFFFFFFF

        v = h + list(_BLAKE256_CONST[:8])
        v[12] ^= t0
        v[13] ^= t0
        v[14] ^= t1
        v[15] ^= t1

        for r in range(14):
            s = _BLAKE256_SIGMA[r % 10]
            for i, (a, b, c, d) in enumerate(
                (
                    (0, 4, 8, 12),
                    (1, 5, 9, 13),
                    (2, 6, 10, 14),
                    (3, 7, 11, 15),
                    (0, 5, 10, 15),
                    (1, 6, 11, 12),
                    (2, 7, 8, 13),
                    (3, 4, 9, 14),
                )
            ):
                v[a] = (v[a] + v[b] + (m[s[2 * i]] ^ _BLAKE256_CONST[s[2 * i + 1]])) & 0xFFFFFFFF
                v[d] = _rotr32(v[d] ^ v[a], 16)
                v[c] = (v[c] + v[d]) & 0xFFFFFFFF
                v[b] = _rotr32(v[b] ^ v[c], 12)
                v[a] = (v[a] + v[b] + (m[s[2 * i + 1]] ^ _BLAKE256_CONST[s[2 * i]])) & 0xFFFFFFFF
                v[d] = _rotr32(v[d] ^ v[a], 8)
                v[c] = (v[c] + v[d]) & 0xFFFFFFFF
                v[b] = _rotr32(v[b] ^ v[c], 7)

        for i in range(8):
            h[i] ^= v[i] ^ v[i + 8]

    return struct.pack(">8I", *h)


# ---------------------------------------------------------------------------
# BabyJubJub Projective & Affine Point Arithmetic (`add-2008-bbjlp`)
# ---------------------------------------------------------------------------


def _tonelli_shanks(n: int, p: int = P) -> int | None:
    if n == 0:
        return 0
    if pow(n, (p - 1) // 2, p) != 1:
        return None
    q = p - 1
    s = 0
    while q % 2 == 0:
        q //= 2
        s += 1
    z = 2
    while pow(z, (p - 1) // 2, p) != p - 1:
        z += 1
    m = s
    c = pow(z, q, p)
    t = pow(n, q, p)
    r = pow(n, (q + 1) // 2, p)
    while t != 1:
        i = 1
        temp = (t * t) % p
        while temp != 1:
            temp = (temp * temp) % p
            i += 1
        b = pow(c, 1 << (m - i - 1), p)
        m = i
        c = (b * b) % p
        t = (t * c) % p
        r = (r * b) % p
    return r


def babyjub_add_proj(
    p1: tuple[int, int, int], p2: tuple[int, int, int]
) -> tuple[int, int, int]:
    """Projective point addition (`add-2008-bbjlp`) on BabyJubJub."""
    x1, y1, z1 = p1
    x2, y2, z2 = p2
    a = (z1 * z2) % P
    b = (a * a) % P
    c = (x1 * x2) % P
    dxy = (y1 * y2) % P
    e = (BABYJUB_D * c % P) * dxy % P
    f = (b - e) % P
    g = (b + e) % P
    aux = ((x1 + y1) * (x2 + y2) - c - dxy) % P
    x3 = a * f % P * aux % P
    ac = BABYJUB_A * c % P
    dac = (dxy - ac) % P
    y3 = a * g % P * dac % P
    z3 = f * g % P
    return (x3, y3, z3)


def babyjub_to_affine(p: tuple[int, int, int]) -> tuple[int, int]:
    x, y, z = p
    if z == 0:
        return (0, 0)
    zinv = pow(z, P - 2, P)
    return (x * zinv % P, y * zinv % P)


def babyjub_mul_scalar(pt: tuple[int, int], n: int) -> tuple[int, int]:
    r = (0, 1, 1)
    exp = (pt[0], pt[1], 1)
    scalar = n
    while scalar > 0:
        if scalar & 1:
            r = babyjub_add_proj(r, exp)
        exp = babyjub_add_proj(exp, exp)
        scalar >>= 1
    return babyjub_to_affine(r)


def babyjub_pack_point(pt: tuple[int, int]) -> bytes:
    """Packs an affine BabyJubJub point `(x, y)` into 32 bytes (circomlib convention)."""
    x, y = pt
    raw = bytearray(y.to_bytes(32, "little"))
    if x > (P >> 1):
        raw[31] |= 0x80
    return bytes(raw)


def babyjub_unpack_point(buff: bytes) -> tuple[int, int] | None:
    """Unpacks a 32-byte compressed BabyJubJub point."""
    if len(buff) != 32:
        return None
    y_bytes = bytearray(buff)
    sign = (y_bytes[31] & 0x80) != 0
    y_bytes[31] &= 0x7F
    y = int.from_bytes(y_bytes, "little")
    if y >= P:
        return None
    y2 = (y * y) % P
    denom = (BABYJUB_A - BABYJUB_D * y2) % P
    if denom == 0:
        return None
    x2 = (1 - y2) * pow(denom, P - 2, P) % P
    x = _tonelli_shanks(x2, P)
    if x is None:
        return None
    if x > (P >> 1):
        x = (P - x) % P
    if sign:
        x = (P - x) % P
    return (x, y)


def get_base_point(point_idx: int) -> tuple[int, int]:
    """Returns the `point_idx`-th Pedersen generator point on BabyJubJub."""
    cached = _BASE_POINT_CACHE.get(point_idx)
    if cached is not None:
        return cached

    try_idx = 0
    while True:
        seed = f"PedersenGenerator_{point_idx:032d}_{try_idx:032d}".encode("ascii")
        h = bytearray(blake256(seed))
        h[31] &= 0xBF  # clear bit 254 (circomlib convention)
        pt = babyjub_unpack_point(h)
        if pt is not None:
            p8 = babyjub_mul_scalar(pt, 8)
            if babyjub_mul_scalar(p8, BABYJUB_SUBORDER) == (0, 1):
                _BASE_POINT_CACHE[point_idx] = p8
                return p8
        try_idx += 1


def pedersen_hash_point(data: bytes) -> tuple[int, int]:
    """Computes the accumulated BabyJubJub point `(x, y)` for `data`."""
    bits: list[int] = []
    for b in data:
        for i in range(8):
            bits.append((b >> i) & 1)

    n_segments = ((max(len(bits), 1) - 1) // BITS_PER_SEGMENT) + 1
    acc = (0, 1, 1)

    for s in range(n_segments):
        seg = bits[s * BITS_PER_SEGMENT : min((s + 1) * BITS_PER_SEGMENT, len(bits))]
        escalar = 0
        exp = 1
        i = 0
        for _ in range(N_WINDOWS_PER_SEGMENT):
            if i >= len(seg):
                break
            w_acc = 1
            for b in range(WINDOW_SIZE - 1):
                if i < len(seg) and seg[i]:
                    w_acc += 1 << b
                i += 1
            if i < len(seg) and seg[i]:
                w_acc = -w_acc
            i += 1
            escalar += w_acc * exp
            exp <<= WINDOW_SIZE + 1

        if escalar < 0:
            escalar += BABYJUB_SUBORDER

        bp = get_base_point(s)
        contrib = babyjub_mul_scalar(bp, escalar)
        acc = babyjub_add_proj(acc, (contrib[0], contrib[1], 1))

    return babyjub_to_affine(acc)


def pedersen_hash(data: bytes) -> int:
    """Computes the circomlib-compatible BabyJubJub Pedersen hash `x`-coordinate (`Fr`).

    Matches `kohaku_tornadocash::crypto::pedersen::pedersen_hash(data)` in `kohaku-rs`.
    """
    return pedersen_hash_point(data)[0]


def pedersen_hash_bytes(data: bytes) -> bytes:
    """Computes the 32-byte packed BabyJubJub point matching `circomlibjs` `pedersenHash.hash(msg)`."""
    return babyjub_pack_point(pedersen_hash_point(data))
