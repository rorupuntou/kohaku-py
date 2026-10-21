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
