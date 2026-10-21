"""Pure Python MiMC Sponge hash implementation matching Tornado Cash (BN254, 220 rounds)."""

from __future__ import annotations

from eth_hash.auto import keccak
from kohaku.crypto.bn254 import P

NROUNDS = 220
SEED = b"mimcsponge"
TORNADO_ZERO_VALUE = (
    21663839004416932945382355908790599225266501822907911457504978515578255421292
)


def _generate_constants(seed: bytes = SEED, n_rounds: int = NROUNDS) -> list[int]:
    cts = [0]
    c = keccak(seed)
    for _ in range(n_rounds - 2):
        c = keccak(c)
        cts.append(int.from_bytes(c, byteorder="little") % P)
    cts.append(0)
    return cts


# Precomputed constants table
MIMC_CONSTANTS = _generate_constants(SEED, NROUNDS)


def mimc_round(l_val: int, r_val: int, k: int = 0) -> tuple[int, int]:
    """Runs one MiMC sponge sequence of 220 rounds."""
    l_cur = l_val
    r_cur = r_val
    for i in range(NROUNDS):
        t = (l_cur + k) % P if i == 0 else (l_cur + k + MIMC_CONSTANTS[i]) % P
        tmp = (r_cur + pow(t, 5, P)) % P
        if i < NROUNDS - 1:
            r_cur, l_cur = l_cur, tmp
        else:
            r_cur = tmp
    return l_cur, r_cur


def mimc_sponge(elements: list[int] | tuple[int, ...], key: int = 0) -> int:
    """Hashes a sequence of field elements using the MiMC sponge (absorbing into R)."""
    r_cur = 0
    c_cur = 0
    for x in elements:
        r_cur, c_cur = mimc_round((r_cur + x) % P, c_cur, key)
    return r_cur


def mimc_hash2(left: int, right: int) -> int:
    """Hashes two field elements (standard binary Merkle tree node hash in Tornado Cash)."""
    return mimc_sponge([left, right])
