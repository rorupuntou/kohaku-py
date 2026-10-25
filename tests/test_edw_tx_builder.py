from eth_account import Account
import pytest

from kohaku.edw.tickets import Ticket
from kohaku.edw.tx_builder import EIP1559Transaction, TransactionBuilder


def test_eip1559_transaction_signing_and_recovery():
    wallet = Account.create()
    tx = EIP1559Transaction(
        chain_id=1,
        nonce=5,
        max_priority_fee_per_gas=2_000_000_000,
        max_fee_per_gas=30_000_000_000,
        gas_limit=50_000,
        to="0x47CE0C6eD5B0Ce3d3A51fdb1C52DC66a7c3c2936",
        value=1_000_000_000_000_000_000,  # 1 ETH
        data=b"\xde\xad\xbe\xef",
    )

    signed = tx.sign(wallet.key)
    assert signed.raw_hex.startswith("0x02")
    assert signed.sender.lower() == wallet.address.lower()
    assert signed.nonce == 5
    assert signed.chain_id == 1

    # Recover transaction via standard Ethereum consensus recovery
    recovered_sender = Account.recover_transaction(signed.raw_hex)
    assert recovered_sender.lower() == wallet.address.lower()


def test_build_deposit_transaction():
    depositor = Account.create()
    commitment = "0x" + "aa" * 32

    signed = TransactionBuilder.build_deposit_tx(
        commitment_hex=commitment,
        pool_id="tornado-cash-1-eth-0.1",
        nonce=0,
        private_key=depositor.key,
        max_fee_per_gas_gwei=20.0,
    )

    assert signed.to.lower() == "0x12d66f87a04a9e220743712ce6d9bb1b5616b8fc"
    assert signed.value == 100_000_000_000_000_000  # 0.1 ETH
    assert signed.data.hex().startswith("b214faa5")  # deposit selector
    assert "aa" * 32 in signed.data.hex()

    recovered = Account.recover_transaction(signed.raw_hex)
    assert recovered.lower() == depositor.address.lower()


def test_gasless_withdraw_payload_and_relayer_broadcast():
    ticket = Ticket.create_draft(currency="ETH", amount="1", chain_id=1)
    virgin_recipient = Account.create().address
    relayer = Account.create()

    # Dummy 256-byte Groth16 proof
    proof_bytes = b"\x42" * 256
    dummy_root = "0x" + "11" * 32

    # 1. Build gasless withdrawal payload
    payload = TransactionBuilder.build_gasless_withdraw_payload(
        ticket=ticket,
        recipient_address=virgin_recipient,
        merkle_root=dummy_root,
        proof_bytes=proof_bytes,
        relayer_address=relayer.address,
        relayer_fee_eth=0.01,  # 0.01 ETH fee to relayer
    )

    assert payload.recipient_address == virgin_recipient
    assert payload.relayer_address == relayer.address
    assert payload.relayer_fee_eth == 0.01
    assert payload.net_recipient_eth == 0.99  # 1.0 - 0.01
    assert payload.net_recipient_wei == 990_000_000_000_000_000
    assert payload.calldata.startswith("0x21a0adb6")  # withdraw selector

    # Fee exceeding note value raises error
    with pytest.raises(ValueError):
        TransactionBuilder.build_gasless_withdraw_payload(
            ticket=ticket,
            recipient_address=virgin_recipient,
            merkle_root=dummy_root,
            proof_bytes=proof_bytes,
            relayer_address=relayer.address,
            relayer_fee_eth=1.5,
        )

    # 2. Relayer signs the broadcast transaction
    relayer_tx = TransactionBuilder.sign_relayer_broadcast(
        payload=payload,
        relayer_private_key=relayer.key,
        nonce=12,
    )

    assert relayer_tx.to.lower() == payload.pool_address.lower()
    assert relayer_tx.value == 0  # relayer sends 0 ETH; the contract pays out
    assert relayer_tx.data.hex() == payload.calldata[2:].lower()
    assert relayer_tx.sender.lower() == relayer.address.lower()

    # Verify consensus validity of relayer tx
    recovered_relayer = Account.recover_transaction(relayer_tx.raw_hex)
    assert recovered_relayer.lower() == relayer.address.lower()


def test_dual_multi_shield_bundle():
    from kohaku.edw.tx_builder import SIMPLE_7702_ACCOUNT_ADDRESS

    depositor = Account.create()
    tickets = [
        Ticket.create_draft(currency="ETH", amount="1", chain_id=1),
        Ticket.create_draft(currency="ETH", amount="0.3", chain_id=1),
        Ticket.create_draft(currency="ETH", amount="0.01", chain_id=1),
    ]

    bundle = TransactionBuilder.build_multi_shield_bundle(
        tickets=tickets,
        private_key=depositor.key,
        start_nonce=7,
    )

    assert bundle.total_eth_str == "1.31"
    assert len(bundle.eip1559_txs) == 3
    assert [tx.nonce for tx in bundle.eip1559_txs] == [7, 8, 9]
    for tx in bundle.eip1559_txs:
        assert Account.recover_transaction(tx.raw_hex).lower() == depositor.address.lower()

    assert bundle.user_operation is not None
    assert bundle.user_operation.sender.lower() == depositor.address.lower()
    assert bundle.user_operation.call_data.startswith("0x34fcd5be")  # executeBatch selector
    assert bundle.user_operation.authorization is not None
    assert bundle.user_operation.authorization.address == SIMPLE_7702_ACCOUNT_ADDRESS
    assert bundle.user_operation.authorization.designator_bytecode().startswith(bytes.fromhex("ef0100"))

