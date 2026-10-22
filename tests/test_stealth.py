from eth_keys import keys

from kohaku.stealth import (
    derive_stealth_keypair,
    generate_stealth_address,
    recover_stealth_private_key,
)


def test_stealth_keypair_derivation():
    mnemonic = "test test test test test test test test test test test junk"
    pair = derive_stealth_keypair(mnemonic, chain_id=1)

    assert pair.spending_public_key.startswith("0x")
    assert pair.viewing_public_key.startswith("0x")
    assert pair.stealth_meta_address.startswith("0x")
    assert len(pair.stealth_meta_address) == 134  # 0x + 132 hex chars
    assert pair.stealth_meta_address_uri.startswith("st:eth:0x")

    # Sepolia prefix test
    sep_pair = derive_stealth_keypair(mnemonic, chain_id=11155111)
    assert sep_pair.stealth_meta_address_uri.startswith("st:sep:0x")


def test_erc5564_scheme1_lifecycle():
    mnemonic = "test test test test test test test test test test test junk"
    alice = derive_stealth_keypair(mnemonic, chain_id=1)

    # Bob sends to Alice's stealth meta-address
    result = generate_stealth_address(alice.stealth_meta_address_uri)
    stealth_addr = result["stealth_address"]
    eph_pub = result["ephemeral_public_key"]

    assert stealth_addr.startswith("0x")
    assert len(stealth_addr) == 42
    assert eph_pub.startswith("0x")
    assert len(eph_pub) == 68  # 0x + 66 hex chars (33 bytes)

    # Alice recovers the private key for the stealth address
    recovered_priv_hex = recover_stealth_private_key(
        spending_private_key=alice.spending_private_key,
        viewing_private_key=alice.viewing_private_key,
        ephemeral_public_key=eph_pub,
    )

    # Verify that the address of recovered_priv matches stealth_addr
    priv_bytes = bytes.fromhex(recovered_priv_hex[2:])
    derived_addr = keys.PrivateKey(priv_bytes).public_key.to_checksum_address().lower()
    assert derived_addr == stealth_addr.lower()
