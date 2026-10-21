from kohaku.crypto.bn254 import P
from kohaku.tornado.circuit import CircuitInputs, solidity_proof_from_snarkjs
from kohaku.tornado.note import TornadoNote
from kohaku.tornado.pools import MAINNET_POOLS, get_pool
from kohaku.tornado.withdraw import build_withdraw_transaction


def test_tornado_note_creation_and_parsing():
    note = TornadoNote.create(currency="ETH", amount="0.1", chain_id=1)

    assert len(note.nullifier) == 31
    assert len(note.secret) == 31
    assert note.commitment < P
    assert note.nullifier_hash < P

    note_str = note.to_note_string()
    assert note_str.startswith("tornado-eth-0.1-1-0x")

    # Roundtrip parsing
    parsed = TornadoNote.from_note_string(note_str)
    assert parsed.currency == "ETH"
    assert parsed.amount == "0.1"
    assert parsed.chain_id == 1
    assert parsed.nullifier == note.nullifier
    assert parsed.secret == note.secret
    assert parsed.commitment == note.commitment
    assert parsed.nullifier_hash == note.nullifier_hash


def test_tornado_pools():
    pool = get_pool("tornado-cash-1-eth-0.1")
    assert pool.asset == "ETH"
    assert pool.amount == "0.1"
    assert pool.contract_address == "0x12d66f87a04a9e220743712ce6d9bb1b5616b8fc"


def test_keychain_derivation():
    from kohaku.tornado.keychain import TornadoKeychain

    mnemonic = "test test test test test test test test test test test junk"
    kc = TornadoKeychain.from_mnemonic(mnemonic)
    assert kc.address == "0x04fD1301f5EaAA7236c273ea00d03c8c24Ab05D7"

    # Derive note for pool at nonce 0
    note = kc.derive_note("tornado-cash-1-eth-0.1", nonce=0)
    assert note.currency == "ETH"
    assert note.amount == "0.1"
    assert len(note.secret) == 31
    assert len(note.nullifier) == 31
    assert note.commitment < P


def test_deposit_transactions():
    from kohaku.tornado.tx import build_deposit_transactions

    note = TornadoNote.create(currency="ETH", amount="0.1", chain_id=1)
    calls = build_deposit_transactions(note)

    assert len(calls) == 1
    call = calls[0]
    assert call.to == "0x12d66f87a04a9e220743712ce6d9bb1b5616b8fc"
    assert call.value == 100_000_000_000_000_000
    assert call.data.startswith("0xb214faa5")


def test_circuit_inputs_and_withdraw_transaction():
    inputs = CircuitInputs(
        root=12345,
        nullifier_hash=67890,
        recipient=int("0x70997970C51812dc3A010C7d01b50e0d17dc79C8", 16),
        relayer=0,
        fee=0,
        refund=0,
        nullifier=111,
        secret=222,
        path_elements=[0] * 20,
        path_indices=[0] * 20,
    )
    d = inputs.to_dict()
    assert d["root"] == "12345"
    assert d["nullifierHash"] == "67890"
    assert len(d["pathElements"]) == 20
    assert len(d["pathIndices"]) == 20

    # Test dummy snarkjs proof conversion
    snarkjs_proof = {
        "pi_a": ["1", "2", "1"],
        "pi_b": [["3", "4"], ["5", "6"], ["1", "0"]],
        "pi_c": ["7", "8", "1"],
        "protocol": "groth16",
    }
    proof_bytes = solidity_proof_from_snarkjs(snarkjs_proof)
    assert len(proof_bytes) == 256

    pool = get_pool("tornado-cash-1-eth-0.1")
    tx = build_withdraw_transaction(
        pool=pool,
        proof_bytes=proof_bytes,
        root=12345,
        nullifier_hash=67890,
        recipient="0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
    )
    assert tx.to == pool.contract_address
    assert tx.value == 0
    assert tx.data.startswith("0x21a0adb6")
