"""Unit tests for the Railgun UTXO privacy engine (`kohaku.railgun`)."""

import pytest

from kohaku.railgun import (
    NULLIFIED_TOPIC,
    RAILGUN_SMART_WALLET_MAINNET,
    SHIELD_TOPIC,
    TRANSACT_TOPIC,
    UNSHIELD_TOPIC,
    RailgunAddress,
    RailgunVault,
)
from kohaku.sync.models import Event


def test_railgun_0zk_bech32m_address_roundtrip():
    mpk = 0x1afd01a29faf22dcc5678694092a08d38de99fc97d07b9281fa66f956ce43579
    vpk = bytes.fromhex("26b8d803977abd16547e6b015decd1b068f2ae8c44f25e10e8d5627faff65eb2")

    addr_eth = RailgunAddress(
        master_public_key=mpk,
        viewing_public_key=vpk,
        chain_type=0,
        chain_id=1,
        version=1,
    )
    encoded = addr_eth.to_0zk()
    assert encoded.startswith("0zk1qy")

    decoded = RailgunAddress.from_0zk(encoded)
    assert decoded.master_public_key == mpk
    assert decoded.viewing_public_key == vpk
    assert decoded.chain_type == 0
    assert decoded.chain_id == 1
    assert decoded.version == 1

    # All-chains address (chain_type=None, chain_id=None)
    addr_all = RailgunAddress(
        master_public_key=mpk,
        viewing_public_key=vpk,
        chain_type=None,
        chain_id=None,
    )
    dec_all = RailgunAddress.from_0zk(addr_all.to_0zk())
    assert dec_all.chain_type is None
    assert dec_all.chain_id is None

    # Corrupt checksum should raise ValueError
    corrupted = encoded[:-1] + ("q" if encoded[-1] != "q" else "p")
    with pytest.raises(ValueError, match="checksum"):
        RailgunAddress.from_0zk(corrupted)


def test_railgun_vault_operations_and_events():
    vault = RailgunVault()

    # 1. Ingest a real 2x3 railgun-operation from Mainnet block 0xe12850
    op_dict = {
        "entity": "railgun-operation",
        "blockNumber": "0xe12850",
        "transactionIndex": "0x150",
        "opIndex": "0x0",
        "nullifiers": [
            "0x1e52cee52f67c37a468458671cddde6b56390dcbdc4cf3b770badc0e78d66401",
            "0x0ac9f5ab5bcb5a115a3efdd0475f6c22dc6a6841caf35a52ecf86a802bfce8ee",
        ],
        "commitments": [
            "0x1afd01a29faf22dcc5678694092a08d38de99fc97d07b9281fa66f956ce43579",
            "0x2ffc716d8ae767995961bbde4a208dbae438783065bbd200f51a8d4e97cc2289",
            "0x078f9824c86b2488714eb76dc15199c3fa21903517d5f3e19ab2035d264400b6",
        ],
        "boundParamsHash": "0x2c72a0bcce4f1169dd988204775483938ded5f5899cec84829b1cc667a683784",
        "utxoTreeIn": "0x0",
        "utxoTreeOut": "0x0",
        "utxoBatchStartPositionOut": "0x2",
    }
    op = vault.ingest_operation(op_dict)
    assert op.topology == "2x3"
    assert (0, 2) in vault.utxos
    assert (0, 3) in vault.utxos
    assert (0, 4) in vault.utxos
    assert len(vault.nullifiers) == 2

    # 2. Ingest a real Shield event (10.658025 WETH at leaf 0x32d4)
    shield_data = (
        "0x"
        + "00" * 31 + "00"  # treeNumber = 0
        + "00" * 30 + "32d4"  # startPosition = 0x32d4
        + "00" * 31 + "a0"  # commitments offset = 0xa0
        + "00" * 30 + "0160"  # shieldCiphertext offset
        + "00" * 30 + "0200"  # fees offset
        + "00" * 31 + "01"  # commitments.length = 1
        + "26b8d803977abd16547e6b015decd1b068f2ae8c44f25e10e8d5627faff65eb2"  # npk
        + "00" * 31 + "00"  # tokenType = 0 (ERC20)
        + "00" * 12 + "c02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"  # WETH
        + "00" * 32  # tokenSubID = 0
        + "00" * 24 + "93e8f13571acf5c0"  # value = 10,658,025,000,000,000,000 wei
    )
    shield_ev = Event(
        contract_address=RAILGUN_SMART_WALLET_MAINNET,
        event_topic=SHIELD_TOPIC,
        topics=[SHIELD_TOPIC],
        data=shield_data,
        block_number=0x10BEBDC,
        log_index=0,
    )
    vault.ingest_event(shield_ev)
    assert len(vault.shields) == 1
    sh = vault.shields[0]
    assert sh.token_address == "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
    assert sh.value == 0x93E8F13571ACF5C0
    assert sh.commitment_hex == "0x2d9aac9336b10cb2c850c84b76feb8798ca45af2a622ac62484906a6ae14cc76"
    assert vault.utxos[(0, 0x32D4)].commitment == sh.commitment

    # 3. Ingest a real Unshield event (1,995 USDT + 5 USDT fee = 2,000 USDT)
    unshield_data = (
        "0x"
        + "00" * 12 + "26629651932fbc6ee3da907fc57f8c863150ebc4"  # to
        + "00" * 32  # tokenType = 0
        + "00" * 12 + "dac17f958d2ee523a2206206994597c13d831ec7"  # USDT
        + "00" * 32  # tokenSubID = 0
        + "00" * 28 + "76e948c0"  # amount = 1,995,000,000
        + "00" * 28 + "004c4b40"  # fee = 5,000,000
    )
    unshield_ev = Event(
        contract_address=RAILGUN_SMART_WALLET_MAINNET,
        event_topic=UNSHIELD_TOPIC,
        topics=[UNSHIELD_TOPIC],
        data=unshield_data,
        block_number=0x10BEBE0,
        log_index=1,
    )
    vault.ingest_event(unshield_ev)
    assert len(vault.unshields) == 1
    un = vault.unshields[0]
    assert un.token_symbol == "USDT"
    assert un.decimal_amount == 1995.0
    assert un.gross_amount == 2_000_000_000

    summary = vault.utxo_audit_summary()
    assert summary["operations_count"] == 1
    assert summary["total_commitments_created"] == 4
    assert summary["total_tree_leaves_allocated"] == 0x32D4 + 1
    assert summary["total_nullifiers_burned"] == 2
    assert summary["net_active_utxos_estimate"] == 0x32D4 + 1 - 2

