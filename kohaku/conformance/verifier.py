"""Cross-client conformance test vector verifier."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ConformanceResult:
    suite_name: str
    passed: bool
    cases_run: int
    errors: List[str] = field(default_factory=list)


def get_default_vectors_dir() -> Path:
    # 1. Check relative to this source file: ../../../conformance/v1
    pkg_dir = Path(__file__).resolve().parent
    candidate_1 = pkg_dir.parent.parent / "conformance" / "v1"
    if candidate_1.exists() and candidate_1.is_dir():
        return candidate_1

    # 2. Check current working directory: ./conformance/v1
    candidate_2 = Path.cwd() / "conformance" / "v1"
    if candidate_2.exists() and candidate_2.is_dir():
        return candidate_2

    raise FileNotFoundError(f"Could not locate conformance vectors directory. Checked {candidate_1} and {candidate_2}")


def verify_crypto_primitives(vectors_dir: Optional[Path] = None) -> ConformanceResult:
    dir_path = vectors_dir or get_default_vectors_dir()
    data = json.loads((dir_path / "crypto_primitives.json").read_text(encoding="utf-8"))

    errors = []
    cases_run = 0

    # MiMC-7
    from kohaku.crypto.mimc import MIMC_CONSTANTS, mimc_hash2
    cases_run += 1
    if len(MIMC_CONSTANTS) != data["mimc7"]["constants_count"]:
        errors.append(f"MiMC constants count mismatch: expected {data['mimc7']['constants_count']}, got {len(MIMC_CONSTANTS)}")

    for tv in data["mimc7"]["test_vectors"]:
        cases_run += 1
        x = int(tv["inputs_hex"][0], 16)
        k = int(tv["inputs_hex"][1], 16)
        h = mimc_hash2(x, k)
        expected = int(tv["expected_hash_hex"], 16)
        if h != expected:
            errors.append(f"MiMC hash mismatch: expected {hex(expected)}, got {hex(h)}")

    # Poseidon
    from kohaku.crypto.poseidon import poseidon_hash, poseidon_hash2
    for tv in data["poseidon"]["test_vectors"]:
        cases_run += 1
        inputs = tv["inputs"]
        if len(inputs) == 2:
            h = poseidon_hash2(inputs[0], inputs[1])
        else:
            h = poseidon_hash(inputs)
        expected = int(tv["expected_hash_hex"], 16)
        if h != expected:
            errors.append(f"Poseidon hash mismatch for {inputs}: expected {hex(expected)}, got {hex(h)}")

    # Pedersen
    from kohaku.crypto.pedersen import babyjub_pack_point, get_base_point, pedersen_hash
    cases_run += 1
    bp0 = get_base_point(0)
    packed_bp0 = babyjub_pack_point(bp0).hex()
    if packed_bp0 != data["pedersen_babyjubjub"]["generator_0_compressed_point_hex"]:
        errors.append(f"Generator 0 point mismatch: expected {data['pedersen_babyjubjub']['generator_0_compressed_point_hex']}, got {packed_bp0}")

    for tv in data["pedersen_babyjubjub"]["test_vectors"]:
        cases_run += 1
        preimage = tv["preimage_ascii"].encode("utf-8")
        h = pedersen_hash(preimage)
        expected = int(tv["expected_hash_hex"], 16)
        if h != expected:
            errors.append(f"Pedersen hash mismatch: expected {hex(expected)}, got {hex(h)}")

    # LeanIMT
    from kohaku.merkle.tree import LeanIMT
    for tv in data["leanimt"]["test_vectors"]:
        cases_run += 1
        tree = LeanIMT(hash_fn=poseidon_hash2)
        for idx, leaf in enumerate(tv["leaves"]):
            tree.insert(leaf)
            expected_root = int(tv["intermediate_roots_hex"][idx], 16)
            if tree.root() != expected_root:
                errors.append(f"LeanIMT intermediate root {idx} mismatch: expected {hex(expected_root)}, got {hex(tree.root())}")

        proof = tree.generate_proof(0)
        valid = proof.verify(hash_fn=poseidon_hash2)
        if valid != tv["leaf_0_inclusion_proof_valid"]:
            errors.append("LeanIMT proof verification mismatch")

    return ConformanceResult("crypto_primitives", len(errors) == 0, cases_run, errors)


def verify_tornado_notes(vectors_dir: Optional[Path] = None) -> ConformanceResult:
    dir_path = vectors_dir or get_default_vectors_dir()
    data = json.loads((dir_path / "tornado_notes.json").read_text(encoding="utf-8"))

    errors = []
    cases_run = 0

    from kohaku.tornado import TornadoNote
    secret = bytes.fromhex(data["fixed_secrets"]["secret_hex"])
    nullifier = bytes.fromhex(data["fixed_secrets"]["nullifier_hex"])
    expected_com = data["fixed_secrets"]["expected_commitment_hex"]
    expected_null = data["fixed_secrets"]["expected_nullifier_hash_hex"]

    for tv in data["test_vectors"]:
        cases_run += 1
        note = TornadoNote(
            currency=tv["currency"],
            amount=tv["amount"],
            chain_id=tv["chain_id"],
            secret=secret,
            nullifier=nullifier,
        )
        if note.commitment_hex != expected_com:
            errors.append(f"Commitment mismatch for {tv['currency']}_{tv['amount']}: expected {expected_com}, got {note.commitment_hex}")
        if note.nullifier_hash_hex != expected_null:
            errors.append(f"Nullifier mismatch for {tv['currency']}_{tv['amount']}: expected {expected_null}, got {note.nullifier_hash_hex}")
        if note.to_note_string() != tv["expected_note_string"]:
            errors.append(f"Note string mismatch for {tv['currency']}_{tv['amount']}: expected {tv['expected_note_string']}, got {note.to_note_string()}")

        # Roundtrip parsing
        parsed = TornadoNote.from_note_string(tv["expected_note_string"])
        if parsed.commitment_hex != expected_com or parsed.nullifier_hash_hex != expected_null:
            errors.append(f"Note string parsing mismatch for {tv['expected_note_string']}")

    return ConformanceResult("tornado_notes", len(errors) == 0, cases_run, errors)


def verify_invoices(vectors_dir: Optional[Path] = None) -> ConformanceResult:
    dir_path = vectors_dir or get_default_vectors_dir()
    data = json.loads((dir_path / "invoices.json").read_text(encoding="utf-8"))

    errors = []
    cases_run = 0

    from kohaku.edw.tickets import TicketInvoice

    for tv in data["test_vectors"]:
        cases_run += 1
        inv = TicketInvoice(
            version=1,
            chain_id=tv["chain_id"],
            currency=tv["currency"],
            amount=tv["amount"],
            pool_id=f"tornado-cash-{tv['chain_id']}-{tv['currency'].lower()}-{tv['amount']}",
            contract_address=tv["pool_contract"],
            commitment=tv["commitment"],
        )
        uri = inv.to_uri()
        if uri != tv["expected_uri"]:
            errors.append(f"Invoice URI mismatch: expected {tv['expected_uri']}, got {uri}")

        parsed = TicketInvoice.from_uri(tv["expected_uri"])
        if parsed.chain_id != tv["chain_id"] or parsed.currency != tv["currency"] or parsed.amount != tv["amount"]:
            errors.append(f"Invoice parsing mismatch for {tv['expected_uri']}")

    return ConformanceResult("invoices", len(errors) == 0, cases_run, errors)


def verify_multishield_userop(vectors_dir: Optional[Path] = None) -> ConformanceResult:
    dir_path = vectors_dir or get_default_vectors_dir()
    data = json.loads((dir_path / "multishield_userop.json").read_text(encoding="utf-8"))

    errors = []
    cases_run = 0

    from kohaku.edw.tx_builder import compute_packed_user_op_hash_v08
    from kohaku.tornado.pools import deposit_pools_for_asset, parse_amount

    # Greedy decomposition
    for tv in data["greedy_decomposition"]:
        cases_run += 1
        decimals = 18 if tv["currency"] in ("ETH", "DAI") else (6 if tv["currency"] in ("USDC", "USDT") else 8)
        raw_amt = parse_amount(tv["amount"], decimals)
        pools = deposit_pools_for_asset(raw_amt, tv["chain_id"], tv["currency"])
        denoms = [p.amount for p in pools]
        if denoms != tv["expected_denominations"]:
            errors.append(f"Greedy decomposition mismatch for {tv['currency']} {tv['amount']}: expected {tv['expected_denominations']}, got {denoms}")

    # Packed UserOp v0.8 hash
    cases_run += 1
    uop = data["packed_user_operation_v08"]
    op_hash = compute_packed_user_op_hash_v08(
        sender=uop["sender"],
        nonce=uop["nonce"],
        init_code=bytes.fromhex(uop["init_code_hex"][2:]),
        call_data=bytes.fromhex(uop["call_data_hex"][2:]),
        verification_gas_limit=uop["verification_gas_limit"],
        call_gas_limit=uop["call_gas_limit"],
        pre_verification_gas=uop["pre_verification_gas"],
        max_priority_fee_per_gas=uop["max_priority_fee_per_gas"],
        max_fee_per_gas=uop["max_fee_per_gas"],
        paymaster_and_data=bytes.fromhex(uop["paymaster_and_data_hex"][2:]),
        chain_id=uop["chain_id"],
        entry_point=uop["entry_point"],
    )
    op_hash_hex = "0x" + op_hash.hex()
    if op_hash_hex != uop["expected_user_op_hash_hex"]:
        errors.append(f"UserOp hash mismatch: expected {uop['expected_user_op_hash_hex']}, got {op_hash_hex}")

    return ConformanceResult("multishield_userop", len(errors) == 0, cases_run, errors)


def verify_railgun(vectors_dir: Optional[Path] = None) -> ConformanceResult:
    dir_path = vectors_dir or get_default_vectors_dir()
    data = json.loads((dir_path / "railgun.json").read_text(encoding="utf-8"))

    errors = []
    cases_run = 0

    from kohaku.railgun.address import RailgunAddress
    mpk = int(data["master_public_key_hex"], 16)
    vpk = bytes.fromhex(data["viewing_public_key_hex"][2:])

    for tv in data["test_vectors"]:
        cases_run += 1
        addr = RailgunAddress(
            master_public_key=mpk,
            viewing_public_key=vpk,
            chain_type=tv["chain_type"],
            chain_id=tv["chain_id"],
            version=tv["version"],
        )
        encoded = addr.to_0zk()
        if encoded != tv["expected_0zk"]:
            errors.append(f"Railgun 0zk mismatch for {tv['description']}: expected {tv['expected_0zk']}, got {encoded}")

        parsed = RailgunAddress.from_0zk(tv["expected_0zk"])
        if parsed.master_public_key != mpk or parsed.viewing_public_key != vpk:
            errors.append(f"Railgun parsing mismatch for {tv['description']}")

    return ConformanceResult("railgun", len(errors) == 0, cases_run, errors)


def verify_blinded_storage(vectors_dir: Optional[Path] = None) -> ConformanceResult:
    dir_path = vectors_dir or get_default_vectors_dir()
    data = json.loads((dir_path / "blinded_storage.json").read_text(encoding="utf-8"))

    errors = []
    cases_run = 0

    from kohaku.edw.storage.cipher import BlindedCipher

    # Argon2id KDF vector
    cases_run += 1
    kdf_vec = data["key_derivation_vector"]
    salt = bytes.fromhex(kdf_vec["salt_hex"])
    derived = BlindedCipher.derive_password_key(kdf_vec["password"], salt).hex()
    if derived != kdf_vec["expected_key_hex"]:
        errors.append(f"Argon2id key derivation mismatch: expected {kdf_vec['expected_key_hex']}, got {derived}")

    # Blinded path vector
    cases_run += 1
    bp_vec = data["blinded_path_vector"]
    root_key = bytes.fromhex(bp_vec["root_data_key_hex"])
    cipher = BlindedCipher(root_key)
    blinded_fn = cipher.derive_blinded_name(bp_vec["logical_key"])
    if blinded_fn != bp_vec["expected_blinded_filename"]:
        errors.append(f"Blinded filename mismatch: expected {bp_vec['expected_blinded_filename']}, got {blinded_fn}")

    cases_run += 1
    rec_key = cipher.derive_record_key(bp_vec["logical_key"]).hex()
    if rec_key != bp_vec["expected_record_encryption_key_hex"]:
        errors.append(f"Record key mismatch: expected {bp_vec['expected_record_encryption_key_hex']}, got {rec_key}")

    return ConformanceResult("blinded_storage", len(errors) == 0, cases_run, errors)


def verify_all(vectors_dir: Optional[Path] = None) -> Dict[str, ConformanceResult]:
    """Run all conformance verification suites against canonical JSON vectors."""
    vdir = vectors_dir or get_default_vectors_dir()
    return {
        "crypto_primitives": verify_crypto_primitives(vdir),
        "tornado_notes": verify_tornado_notes(vdir),
        "invoices": verify_invoices(vdir),
        "multishield_userop": verify_multishield_userop(vdir),
        "railgun": verify_railgun(vdir),
        "blinded_storage": verify_blinded_storage(vdir),
    }
