"""Offline EIP-1559 Raw Transaction Builder and Gasless Withdrawal Engine.

Constructs, encodes, signs, and pre-validates Ethereum L1 transactions
completely offline without requiring an external web2 RPC or bundler.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any, List, Optional

from eth_account import Account
from eth_account._utils.signing import sign_transaction_hash
from eth_hash.auto import keccak
from eth_keys import keys
import rlp

from kohaku.edw.tickets import Ticket
from kohaku.tornado.pools import get_pool
from kohaku.tornado.withdraw import build_withdraw_transaction


@dataclass
class SignedTransaction:
    """Signed Ethereum transaction ready for P2P network broadcast."""
    raw_bytes: bytes
    raw_hex: str
    tx_hash: str
    sender: str
    to: str
    value: int
    gas_limit: int
    data: bytes
    chain_id: int
    nonce: int


@dataclass
class GaslessWithdrawPayload:
    """Pre-validated payload for unshielding funds to a virgin address with 0 gas cost.

    The gas is paid by the relayer/builder, and reimbursed directly from the pool note.
    The recipient address receives the net amount without having ever touched gas.
    """
    ticket_id: str
    pool_id: str
    pool_address: str
    recipient_address: str
    relayer_address: str
    relayer_fee_wei: int
    relayer_fee_eth: float
    net_recipient_wei: int
    net_recipient_eth: float
    calldata: str
    chain_id: int
    nullifier_hash: str
    root: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticket_id": self.ticket_id,
            "pool_id": self.pool_id,
            "pool_address": self.pool_address,
            "recipient_address": self.recipient_address,
            "relayer_address": self.relayer_address,
            "relayer_fee_wei": self.relayer_fee_wei,
            "relayer_fee_eth": self.relayer_fee_eth,
            "net_recipient_wei": self.net_recipient_wei,
            "net_recipient_eth": self.net_recipient_eth,
            "calldata": self.calldata,
            "chain_id": self.chain_id,
            "nullifier_hash": self.nullifier_hash,
            "root": self.root,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


@dataclass
class EIP1559Transaction:
    """EIP-1559 (Type 2) deterministic transaction builder."""
    chain_id: int
    nonce: int
    max_priority_fee_per_gas: int
    max_fee_per_gas: int
    gas_limit: int
    to: str
    value: int
    data: bytes = b""
    access_list: List[Any] = field(default_factory=list)

    def _to_bytes_address(self) -> bytes:
        clean = self.to.lower().replace("0x", "")
        return bytes.fromhex(clean)

    def encode_unsigned(self) -> bytes:
        """Encode raw payload before signature according to EIP-1559:

        0x02 || rlp([chain_id, nonce, max_priority_fee, max_fee, gas_limit, to, value, data, access_list])
        """
        payload = [
            self.chain_id,
            self.nonce,
            self.max_priority_fee_per_gas,
            self.max_fee_per_gas,
            self.gas_limit,
            self._to_bytes_address(),
            self.value,
            self.data,
            self.access_list,
        ]
        return b"\x02" + rlp.encode(payload)

    def signing_hash(self) -> bytes:
        return keccak(self.encode_unsigned())

    def sign(self, private_key: str | bytes) -> SignedTransaction:
        """Sign transaction offline using secp256k1 private key."""
        if isinstance(private_key, str):
            clean_key = private_key[2:] if private_key.startswith("0x") else private_key
            key_bytes = bytes.fromhex(clean_key)
        else:
            key_bytes = private_key

        key_obj = keys.PrivateKey(key_bytes)
        sender_address = key_obj.public_key.to_checksum_address()

        tx_hash = self.signing_hash()
        v, r, s = sign_transaction_hash(key_obj, tx_hash)

        # EIP-1559 payload with signature components (y_parity, r, s)
        signed_fields = [
            self.chain_id,
            self.nonce,
            self.max_priority_fee_per_gas,
            self.max_fee_per_gas,
            self.gas_limit,
            self._to_bytes_address(),
            self.value,
            self.data,
            self.access_list,
            v,
            r,
            s,
        ]
        raw_tx_bytes = b"\x02" + rlp.encode(signed_fields)
        raw_hex = "0x" + raw_tx_bytes.hex()
        overall_tx_hash = "0x" + keccak(raw_tx_bytes).hex()

        return SignedTransaction(
            raw_bytes=raw_tx_bytes,
            raw_hex=raw_hex,
            tx_hash=overall_tx_hash,
            sender=sender_address,
            to=self.to,
            value=self.value,
            gas_limit=self.gas_limit,
            data=self.data,
            chain_id=self.chain_id,
            nonce=self.nonce,
        )


class TransactionBuilder:
    """High-level offline transaction constructor for deposits and unshields."""

    @staticmethod
    def build_deposit_tx(
        commitment_hex: str,
        pool_id: str,
        nonce: int,
        private_key: str | bytes,
        max_fee_per_gas_gwei: float = 25.0,
        max_priority_fee_gwei: float = 1.5,
        gas_limit: int = 1_000_000,
    ) -> SignedTransaction:
        """Build and sign an offline deposit transaction for Tornado Cash."""
        pool = get_pool(pool_id)
        commitment_clean = commitment_hex.lower().replace("0x", "").zfill(64)
        # deposit(bytes32) = 0xb214faa5
        calldata = bytes.fromhex("b214faa5" + commitment_clean)

        max_fee_wei = int(max_fee_per_gas_gwei * 10**9)
        priority_fee_wei = int(max_priority_fee_gwei * 10**9)

        tx = EIP1559Transaction(
            chain_id=pool.chain_id,
            nonce=nonce,
            max_priority_fee_per_gas=priority_fee_wei,
            max_fee_per_gas=max_fee_wei,
            gas_limit=gas_limit,
            to=pool.contract_address,
            value=pool.amount_wei,
            data=calldata,
        )
        return tx.sign(private_key)

    @staticmethod
    def build_gasless_withdraw_payload(
        ticket: Ticket,
        recipient_address: str,
        merkle_root: str,
        proof_bytes: bytes,
        relayer_address: str,
        relayer_fee_eth: float = 0.005,
        refund_eth: float = 0.0,
    ) -> GaslessWithdrawPayload:
        """Constructs an unshielding payload with relayer gas compensation.

        The recipient address pays ZERO gas and needs ZERO balance.
        """
        pool = get_pool(ticket.pool_id)
        fee_wei = int(relayer_fee_eth * 10**18)
        refund_wei = int(refund_eth * 10**18)

        if fee_wei >= pool.amount_wei:
            raise ValueError(f"Relayer fee ({relayer_fee_eth} ETH) exceeds total note value ({ticket.amount} ETH)")

        net_wei = pool.amount_wei - fee_wei
        net_eth = net_wei / 10**18

        call = build_withdraw_transaction(
            pool=pool,
            proof_bytes=proof_bytes,
            root=merkle_root,
            nullifier_hash=ticket.nullifier_hash_hex,
            recipient=recipient_address,
            relayer=relayer_address,
            fee=fee_wei,
            refund=refund_wei,
        )

        return GaslessWithdrawPayload(
            ticket_id=ticket.id,
            pool_id=pool.id,
            pool_address=pool.contract_address,
            recipient_address=recipient_address,
            relayer_address=relayer_address,
            relayer_fee_wei=fee_wei,
            relayer_fee_eth=relayer_fee_eth,
            net_recipient_wei=net_wei,
            net_recipient_eth=net_eth,
            calldata=call.data,
            chain_id=pool.chain_id,
            nullifier_hash=ticket.nullifier_hash_hex,
            root=merkle_root if merkle_root.startswith("0x") else f"0x{int(merkle_root):064x}",
        )

    @staticmethod
    def sign_relayer_broadcast(
        payload: GaslessWithdrawPayload,
        relayer_private_key: str | bytes,
        nonce: int,
        max_fee_per_gas_gwei: float = 25.0,
        max_priority_fee_gwei: float = 1.5,
        gas_limit: int = 450_000,
    ) -> SignedTransaction:
        """Used by the relayer / self-relayer to sign and broadcast the withdraw payload."""
        calldata_bytes = bytes.fromhex(payload.calldata[2:] if payload.calldata.startswith("0x") else payload.calldata)
        max_fee_wei = int(max_fee_per_gas_gwei * 10**9)
        priority_fee_wei = int(max_priority_fee_gwei * 10**9)

        tx = EIP1559Transaction(
            chain_id=payload.chain_id,
            nonce=nonce,
            max_priority_fee_per_gas=priority_fee_wei,
            max_fee_per_gas=max_fee_wei,
            gas_limit=gas_limit,
            to=payload.pool_address,
            value=0,
            data=calldata_bytes,
        )
        return tx.sign(relayer_private_key)
