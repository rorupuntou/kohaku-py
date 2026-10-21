from kohaku.crypto.bn254 import P
from kohaku.tornado.note import TornadoNote
from kohaku.tornado.pools import MAINNET_POOLS, get_pool


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
    assert call.data.startswith("0xb214fa")
    assert note.commitment_hex.replace("0x", "") in call.data
