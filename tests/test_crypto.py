from kohaku.crypto.bn254 import P, to_field
from kohaku.crypto.mimc import (
    MIMC_CONSTANTS,
    TORNADO_ZERO_VALUE,
    mimc_hash2,
    mimc_sponge,
)
from kohaku.crypto.poseidon import poseidon_hash, poseidon_hash2


def test_mimc_constants():
    assert len(MIMC_CONSTANTS) == 220
    assert MIMC_CONSTANTS[0] == 0
    assert MIMC_CONSTANTS[-1] == 0


def test_tornado_zero_value_propagation():
    # Level 1 zero in Tornado Cash MerkleTreeWithHistory.sol
    level_1_expected = 5041291608743866145624243161007933932820125783648393807549403023501038405412
    computed = mimc_hash2(TORNADO_ZERO_VALUE, TORNADO_ZERO_VALUE)
    assert computed == level_1_expected


def test_poseidon():
    h2 = poseidon_hash2(1, 2)
    assert h2 < P
    h3 = poseidon_hash([1, 2, 3])
    assert h3 < P


def test_pedersen_hash_kohaku_rs_parity():
    from kohaku.crypto.pedersen import (
        babyjub_pack_point,
        babyjub_unpack_point,
        get_base_point,
        pedersen_hash,
    )

    # Golden vector from kohaku-rs (crates/tornadocash/src/crypto/pedersen.rs) & circomlib
    expected = (
        13491600061712299675396441404596955294388976214662355192405913840310160783842
    )
    assert pedersen_hash(b"Hello, world!") == expected

    # Verify point packing/unpacking roundtrip on Pedersen generator 0
    bp0 = get_base_point(0)
    packed = babyjub_pack_point(bp0)
    assert len(packed) == 32
    assert babyjub_unpack_point(packed) == bp0

