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
    assert len(bundle.user_operation.account_gas_limits_hex) == 66
    assert len(bundle.user_operation.gas_fees_hex) == 66


def test_packed_user_operation_v08_eip712_hash_kohaku_rs_vector():
    """Verifies bit-for-bit parity with `kohaku-rs` (`crates/userop-kit/src/signable_user_operation.rs` snapshot)."""
    from kohaku.edw.tx_builder import compute_packed_user_op_hash_v08, pack_u128_pair

    init_code = bytes.fromhex("000000000000000000000000000000000000beef") + b"factory data"
    paymaster_and_data = (
        bytes.fromhex("000000000000000000000000000000000000feed")
        + (20_000).to_bytes(16, "big")
        + (30_000).to_bytes(16, "big")
        + b"paymaster data"
    )
    assert (
        "0x" + pack_u128_pair(50_000, 100_000).hex()
        == "0x0000000000000000000000000000c350000000000000000000000000000186a0"
    )
    assert (
        "0x" + pack_u128_pair(50, 200).hex()
        == "0x00000000000000000000000000000032000000000000000000000000000000c8"
    )

    op_hash = compute_packed_user_op_hash_v08(
        sender="0x000000000000000000000000000000000000dEaD",
        nonce=42,
        init_code=init_code,
        call_data=b"call data",
        verification_gas_limit=50_000,
        call_gas_limit=100_000,
        pre_verification_gas=10_000,
        max_priority_fee_per_gas=50,
        max_fee_per_gas=200,
        paymaster_and_data=paymaster_and_data,
        chain_id=1,
    )
    assert (
        "0x" + op_hash.hex()
        == "0xa763cdf6c11eee14cea4d32863d184afe29859b556c85b7ae6f11f64f8945492"
    )


def test_erc20_multi_shield_bundle_and_forward_call():
    """Verifies batching of ERC-20 approval + deposits and token forwarding matching desktop-wallet."""
    from eth_account import Account
    from kohaku.edw.tickets import Ticket
    from kohaku.edw.tx_builder import TransactionBuilder
    from kohaku.tornado.pools import TOKEN_ADDRESSES

    depositor = Account.create()
    tickets = [
        Ticket.create_draft(currency="USDC", amount="100", chain_id=1),
        Ticket.create_draft(currency="USDC", amount="1000", chain_id=1),
    ]

    bundle = TransactionBuilder.build_multi_shield_bundle(
        tickets=tickets,
        private_key=depositor.key,
        start_nonce=10,
    )

    assert bundle.token == "USDC"
    assert bundle.total_amount_str == "1100"
    # Each ERC-20 note requires an approve tx and a deposit tx -> 4 sequential EIP-1559 txs
    assert len(bundle.eip1559_txs) == 4
    assert [tx.nonce for tx in bundle.eip1559_txs] == [10, 11, 12, 13]
    for tx in bundle.eip1559_txs:
        assert Account.recover_transaction(tx.raw_hex).lower() == depositor.address.lower()

    # UserOperation executeBatch encodes 4 calls (approve, deposit, approve, deposit)
    assert bundle.user_operation is not None
    assert bundle.user_operation.call_data.startswith("0x34fcd5be")

    # Verify ERC-20 forward call uses transfer(to, amount)
    recipient = Account.create().address
    usdc_addr = TOKEN_ADDRESSES[(1, "USDC")]
    target, val, data = TransactionBuilder.build_erc20_forward_call(
        token_address=usdc_addr,
        recipient_address=recipient,
        amount_raw=100_000_000,
    )
    assert target.lower() == usdc_addr.lower()
    assert val == 0
    assert data.hex().startswith("a9059cbb")  # transfer(address,uint256)
    assert recipient.lower().removeprefix("0x") in data.hex()


