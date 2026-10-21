from kohaku.crypto.bn254 import P
from kohaku.privacy_pools.asp import AssociationSet
from kohaku.privacy_pools.note import PrivacyPoolNote
from kohaku.privacy_pools.pools import ALL_PRIVACY_POOLS, get_privacy_pool
from kohaku.privacy_pools.vault import DEPOSITED_TOPIC, PrivacyPoolsVault


def test_privacy_pool_note():
    note = PrivacyPoolNote.create(value=10**18, label=0)

    assert note.value == 10**18
    assert note.label == 0
    assert note.commitment < P
    assert note.nullifier_hash < P


def test_association_set():
    note1 = PrivacyPoolNote.create(value=10**18)
    note2 = PrivacyPoolNote.create(value=2 * 10**18)

    asp = AssociationSet.from_deposits("0xbow", [note1.commitment, note2.commitment])

    assert asp.is_included(note1.commitment) is True
    assert asp.is_included(note2.commitment) is True
    assert asp.is_included(0x12345) is False

    proof = asp.generate_proof(0)
    assert proof.leaf == note1.commitment


def test_privacy_pools_registry():
    assert "privacy-pools-1-eth" in ALL_PRIVACY_POOLS
    pool = get_privacy_pool("privacy-pools-1-eth")
    assert pool.asset == "ETH"
    assert pool.contract_address.lower() == "0xf241d57c6debae225c0f2e6ea1529373c9a9c9fb"
    assert pool.is_native is True

    dai_pool = get_privacy_pool("privacy-pools-1-dai")
    assert dai_pool.is_native is False
    assert dai_pool.decimals == 18
