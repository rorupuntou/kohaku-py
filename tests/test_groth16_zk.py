"""Tests for pure Python Groth16 codec and BN128 verifier."""

import json
from pathlib import Path
import pytest

from kohaku.tornado.pools import get_pool
from kohaku.tornado.withdraw import WITHDRAW_SELECTOR, build_withdraw_transaction
from kohaku.tornado.zk.codec import Groth16Proof, pad32, pad64, pad128
from kohaku.tornado.zk.verifier import parse_g1_point, parse_g2_point, verify_groth16_proof


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "groth16_snarkjs_bn254.json"


def test_point_padding():
    # pad32
    assert pad32(42) == "0x" + "2a".zfill(64)
    assert pad32(b"\x01") == "0x" + "01".zfill(64)
    assert pad32("0xabc") == "0x" + "abc".zfill(64)
    assert len(pad32(123456789)) == 66  # "0x" + 64 hex chars

    # pad64
    assert len(pad64("0x1234")) == 130  # "0x" + 128 hex chars (64 bytes)
    assert len(pad64(b"\xaa" * 64)) == 130

    # pad128
    assert len(pad128("0xabcd")) == 258  # "0x" + 256 hex chars (128 bytes)
    assert len(pad128(b"\xbb" * 128)) == 258


def test_groth16_proof_serialization():
    mock_proof = Groth16Proof.mock()
    assert len(mock_proof.a_hex) == 130  # 0x + 128 chars = 64 bytes
    assert len(mock_proof.b_hex) == 258  # 0x + 256 chars = 128 bytes
    assert len(mock_proof.c_hex) == 130  # 0x + 128 chars = 64 bytes

    raw = mock_proof.to_bytes()
    assert len(raw) == 256
    hex_str = mock_proof.to_hex()
    assert len(hex_str) == 514  # 0x + 512 chars

    # Roundtrip from_bytes
    restored = Groth16Proof.from_bytes(raw)
    assert restored.to_bytes() == raw
    assert restored.to_hex() == hex_str

    # Roundtrip from_hex
    restored_hex = Groth16Proof.from_hex(hex_str)
    assert restored_hex.to_bytes() == raw

    # Error on invalid byte count
    with pytest.raises(ValueError, match="Expected 256 bytes"):
        Groth16Proof.from_bytes(b"\x00" * 255)


def test_groth16_snarkjs_parsing_and_equivalence():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    proof = Groth16Proof.from_snarkjs_dict(data["proof"])
    raw_bytes = proof.to_bytes()
    assert len(raw_bytes) == 256

    # Verify that each segment matches EVM packing
    assert len(proof.a_hex) == 130
    assert len(proof.b_hex) == 258
    assert len(proof.c_hex) == 130


def test_groth16_arkworks_parsing():
    arkworks_data = {
        "curve": "Bn254",
        "proof": {
            "a": "0x" + "01" * 64,
            "b": "0x" + "02" * 128,
            "c": "0x" + "03" * 64,
        },
    }
    proof = Groth16Proof.from_arkworks_dict(arkworks_data)
    assert len(proof.to_bytes()) == 256
    assert proof.a_hex == "0x" + "01" * 64


def test_groth16_pure_python_verification():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    proof = Groth16Proof.from_snarkjs_dict(data["proof"])
    public_signals = data["publicSignals"]
    vk = data["vk"]

    # 1. Valid proof verification
    assert verify_groth16_proof(proof, public_signals, vk) is True

    # 2. Direct dict format verification
    assert verify_groth16_proof(data["proof"], public_signals, vk) is True

    # 3. Tampered public signal must fail
    tampered_signals = list(public_signals)
    tampered_signals[0] = str(int(tampered_signals[0]) + 1)
    assert verify_groth16_proof(proof, tampered_signals, vk) is False

    # 4. Mock / invalid proof must fail
    assert verify_groth16_proof(Groth16Proof.mock(), public_signals, vk) is False


def test_build_withdraw_transaction_with_groth16_proof():
    pool = get_pool("tornado-cash-1-eth-0.1")
    proof = Groth16Proof.mock()

    tx = build_withdraw_transaction(
        pool=pool,
        proof_bytes=proof,
        root=12345,
        nullifier_hash=67890,
        recipient="0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
    )

    assert tx.to == pool.contract_address
    assert tx.value == 0
    assert tx.data.startswith("0x" + WITHDRAW_SELECTOR.hex())

    # Ensure default mock is used when proof_bytes is None
    tx_default = build_withdraw_transaction(
        pool=pool,
        proof_bytes=None,
        root=12345,
        nullifier_hash=67890,
        recipient="0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
    )
    assert tx_default.data == tx.data

    # Error on invalid length
    with pytest.raises(ValueError, match="must be exactly 256 bytes"):
        build_withdraw_transaction(pool=pool, proof_bytes=b"\x00" * 128)
