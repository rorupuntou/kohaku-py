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
    def _gwei_to_wei(val: float | int | str) -> int:
        from decimal import Decimal

        return int(Decimal(str(val)) * (Decimal(10) ** 9))

    @staticmethod
    def _eth_to_wei(val: float | int | str) -> int:
        from decimal import Decimal

        return int(Decimal(str(val)) * (Decimal(10) ** 18))

    @staticmethod
    def build_deposit_tx(
        commitment_hex: str,
        pool_id: str,
        nonce: int,
        private_key: str | bytes,
        max_fee_per_gas_gwei: float | str = 25.0,
        max_priority_fee_gwei: float | str = 1.5,
        gas_limit: int = 1_000_000,
    ) -> SignedTransaction:
        """Build and sign an offline deposit transaction for Tornado Cash."""
        pool = get_pool(pool_id)
        commitment_clean = commitment_hex.lower().replace("0x", "").zfill(64)
        # deposit(bytes32) = 0xb214faa5
        calldata = bytes.fromhex("b214faa5" + commitment_clean)

        max_fee_wei = TransactionBuilder._gwei_to_wei(max_fee_per_gas_gwei)
        priority_fee_wei = TransactionBuilder._gwei_to_wei(max_priority_fee_gwei)

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
        relayer_fee_eth: float | str = 0.005,
        refund_eth: float | str = 0.0,
    ) -> GaslessWithdrawPayload:
        """Constructs an unshielding payload with relayer gas compensation.

        The recipient address pays ZERO gas and needs ZERO balance.
        Uses exact `Decimal` conversion to prevent 1-wei IEEE-754 rounding drift.
        """
        from decimal import Decimal

        pool = get_pool(ticket.pool_id)
        fee_wei = TransactionBuilder._eth_to_wei(relayer_fee_eth)
        refund_wei = TransactionBuilder._eth_to_wei(refund_eth)

        if fee_wei >= pool.amount_wei:
            raise ValueError(f"Relayer fee ({relayer_fee_eth} ETH) exceeds total note value ({ticket.amount} ETH)")

        net_wei = pool.amount_wei - fee_wei
        net_eth = float(Decimal(net_wei) / (Decimal(10) ** 18))

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
            relayer_fee_eth=float(Decimal(str(relayer_fee_eth))),
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
        max_fee_per_gas_gwei: float | str = 25.0,
        max_priority_fee_gwei: float | str = 1.5,
        gas_limit: int = 450_000,
    ) -> SignedTransaction:
        """Used by the relayer / self-relayer to sign and broadcast the withdraw payload."""
        calldata_bytes = bytes.fromhex(payload.calldata[2:] if payload.calldata.startswith("0x") else payload.calldata)
        max_fee_wei = TransactionBuilder._gwei_to_wei(max_fee_per_gas_gwei)
        priority_fee_wei = TransactionBuilder._gwei_to_wei(max_priority_fee_gwei)

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

    @staticmethod
    def build_multi_shield_bundle(
        tickets: List[Ticket],
        private_key: str | bytes,
        start_nonce: int = 0,
        max_fee_per_gas_gwei: float | str = 25.0,
        max_priority_fee_gwei: float | str = 1.5,
        gas_limit_per_deposit: int = 1_000_000,
        already_delegated: bool = False,
    ) -> MultiShieldBundle:
        """Build a Dual Multi-Shield Bundle (ERC-4337 + EIP-7702 UserOperation AND EIP-1559 sequence).

        Matches EDW PR #108 (`submit_user_operation` over `Simple7702SmartAccount::executeBatch`)
        while also pre-signing sequential EIP-1559 transactions for sovereign P2P/Tor fallback.
        """
        if not tickets:
            raise ValueError("Cannot build a multi-shield bundle with zero tickets")

        eip1559_txs: List[SignedTransaction] = []
        calls: List[tuple[str, int, bytes]] = []
        total_wei = 0
        chain_id = tickets[0].chain_id

        for idx, ticket in enumerate(tickets):
            pool = get_pool(ticket.pool_id)
            total_wei += pool.amount_wei
            commitment_clean = ticket.commitment_hex.lower().replace("0x", "").zfill(64)
            calldata = bytes.fromhex("b214faa5" + commitment_clean)
            calls.append((pool.contract_address, pool.amount_wei, calldata))

            signed_tx = TransactionBuilder.build_deposit_tx(
                commitment_hex=ticket.commitment_hex,
                pool_id=ticket.pool_id,
                nonce=start_nonce + idx,
                private_key=private_key,
                max_fee_per_gas_gwei=max_fee_per_gas_gwei,
                max_priority_fee_gwei=max_priority_fee_gwei,
                gas_limit=gas_limit_per_deposit,
            )
            eip1559_txs.append(signed_tx)

        user_op: Optional[UserOperationBatch] = None
        if len(tickets) > 1:
            user_op = UserOperationBatch.build_and_sign(
                chain_id=chain_id,
                calls=calls,
                private_key=private_key,
                account_nonce=start_nonce,
                max_fee_per_gas_gwei=max_fee_per_gas_gwei,
                max_priority_fee_gwei=max_priority_fee_gwei,
                already_delegated=already_delegated,
            )

        return MultiShieldBundle(
            chain_id=chain_id,
            sender=eip1559_txs[0].sender,
            tickets=tickets,
            total_wei=total_wei,
            user_operation=user_op,
            eip1559_txs=eip1559_txs,
        )


# ---------------------------------------------------------------------------
# EIP-7702 & ERC-4337 v0.8 Simple7702Account Batching (EDW PR #108 & kohaku-rs Parity)
# ---------------------------------------------------------------------------

SIMPLE_7702_ACCOUNT_ADDRESS = "0xe6Cae83BdE06E4c305530e199D7217f42808555B"
SIMPLE_DELEGATE_ADDRESS = "0xACAe14c5d84EA4a1ddb84bFbDc1a62796677ACcA"
ENTRYPOINT_V08_ADDRESS = "0x4337084D9E255Ff0702461CF8895CE9E3b5Ff108"
EIP7702_MAGIC = b"\x05"
EIP7702_DESIGNATOR_PREFIX = bytes.fromhex("ef0100")

EIP712_DOMAIN_TYPEHASH = keccak(
    b"EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"
)
PACKED_USEROP_TYPEHASH = keccak(
    b"PackedUserOperation(address sender,uint256 nonce,bytes initCode,bytes callData,bytes32 accountGasLimits,uint256 preVerificationGas,bytes32 gasFees,bytes paymasterAndData)"
)


def pack_u128_pair(high_128: int, low_128: int) -> bytes:
    """Packs two 128-bit unsigned integers into a single 32-byte `bytes32` word (`(high << 128) | low`)."""
    mask = (1 << 128) - 1
    combined = ((high_128 & mask) << 128) | (low_128 & mask)
    return combined.to_bytes(32, "big")


def compute_packed_user_op_hash_v08(
    sender: str,
    nonce: int,
    init_code: bytes,
    call_data: bytes,
    verification_gas_limit: int,
    call_gas_limit: int,
    pre_verification_gas: int,
    max_priority_fee_per_gas: int,
    max_fee_per_gas: int,
    paymaster_and_data: bytes,
    chain_id: int,
    entry_point: str = ENTRYPOINT_V08_ADDRESS,
) -> bytes:
    """Computes the canonical ERC-4337 v0.8 EIP-712 signing hash over `PackedUserOperation`.

    Matches `kohaku-rs` (`crates/userop-kit/src/signable_user_operation.rs` & `entry_point.rs`)
    bit-for-bit (`domain = {name: "ERC4337", version: "1", chainId, verifyingContract}`).
    """
    import eth_abi

    account_gas_limits = pack_u128_pair(verification_gas_limit, call_gas_limit)
    gas_fees = pack_u128_pair(max_priority_fee_per_gas, max_fee_per_gas)

    domain_separator = keccak(
        eth_abi.encode(
            ["bytes32", "bytes32", "bytes32", "uint256", "address"],
            [
                EIP712_DOMAIN_TYPEHASH,
                keccak(b"ERC4337"),
                keccak(b"1"),
                chain_id,
                entry_point.lower(),
            ],
        )
    )

    struct_hash = keccak(
        eth_abi.encode(
            [
                "bytes32",
                "address",
                "uint256",
                "bytes32",
                "bytes32",
                "bytes32",
                "uint256",
                "bytes32",
                "bytes32",
            ],
            [
                PACKED_USEROP_TYPEHASH,
                sender.lower(),
                nonce,
                keccak(init_code),
                keccak(call_data),
                account_gas_limits,
                pre_verification_gas,
                gas_fees,
                keccak(paymaster_and_data),
            ],
        )
    )
    return keccak(b"\x19\x01" + domain_separator + struct_hash)


def compute_packed_user_op_hash_v07(
    sender: str,
    nonce: int,
    init_code: bytes,
    call_data: bytes,
    verification_gas_limit: int,
    call_gas_limit: int,
    pre_verification_gas: int,
    max_priority_fee_per_gas: int,
    max_fee_per_gas: int,
    paymaster_and_data: bytes,
    chain_id: int,
    entry_point: str = ENTRYPOINT_V08_ADDRESS,
) -> bytes:
    """Computes the ERC-4337 v0.7 `userOpHash` (`keccak256(abi.encode(keccak256(packedUserOp), entryPoint, chainId))`)."""
    import eth_abi

    account_gas_limits = pack_u128_pair(verification_gas_limit, call_gas_limit)
    gas_fees = pack_u128_pair(max_priority_fee_per_gas, max_fee_per_gas)

    packed_op_hash = keccak(
        eth_abi.encode(
            [
                "address",
                "uint256",
                "bytes32",
                "bytes32",
                "bytes32",
                "uint256",
                "bytes32",
                "bytes32",
            ],
            [
                sender.lower(),
                nonce,
                keccak(init_code),
                keccak(call_data),
                account_gas_limits,
                pre_verification_gas,
                gas_fees,
                keccak(paymaster_and_data),
            ],
        )
    )
    return keccak(
        eth_abi.encode(
            ["bytes32", "address", "uint256"],
            [packed_op_hash, entry_point.lower(), chain_id],
        )
    )


@dataclass(frozen=True)
class EIP7702Authorization:
    """Signed EIP-7702 authorization tuple (`0x05 || rlp([chain_id, address, nonce])`)."""

    chain_id: int
    address: str
    nonce: int
    y_parity: int
    r: str
    s: str

    @classmethod
    def sign(
        cls,
        chain_id: int,
        implementation: str,
        nonce: int,
        private_key: str | bytes,
    ) -> EIP7702Authorization:
        if isinstance(private_key, str):
            clean_key = private_key[2:] if private_key.startswith("0x") else private_key
            key_bytes = bytes.fromhex(clean_key)
        else:
            key_bytes = private_key

        key_obj = keys.PrivateKey(key_bytes)
        addr_bytes = bytes.fromhex(implementation.lower().removeprefix("0x"))
        msg_hash = keccak(EIP7702_MAGIC + rlp.encode([chain_id, addr_bytes, nonce]))
        v, r, s = sign_transaction_hash(key_obj, msg_hash)
        return cls(
            chain_id=chain_id,
            address=implementation,
            nonce=nonce,
            y_parity=v,
            r=f"0x{r:064x}",
            s=f"0x{s:064x}",
        )

    def designator_bytecode(self) -> bytes:
        """Return `0xef0100 || implementation` (23 bytes)."""
        return EIP7702_DESIGNATOR_PREFIX + bytes.fromhex(self.address.lower().removeprefix("0x"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "chainId": hex(self.chain_id),
            "address": self.address,
            "nonce": hex(self.nonce),
            "yParity": hex(self.y_parity),
            "r": self.r,
            "s": self.s,
        }


@dataclass(frozen=True)
class UserOperationBatch:
    """ERC-4337 v0.8 `PackedUserOperation` wrapping `Simple7702Account.executeBatch`."""

    sender: str
    chain_id: int
    nonce: int
    call_data: str
    call_gas_limit: int
    verification_gas_limit: int
    pre_verification_gas: int
    max_fee_per_gas: int
    max_priority_fee_per_gas: int
    authorization: Optional[EIP7702Authorization]
    user_op_hash: str
    signature: str
    init_code: bytes = b""
    paymaster_and_data: bytes = b""

    @property
    def account_gas_limits_hex(self) -> str:
        """Returns `bytes32((verificationGasLimit << 128) | callGasLimit)`."""
        return "0x" + pack_u128_pair(self.verification_gas_limit, self.call_gas_limit).hex()

    @property
    def gas_fees_hex(self) -> str:
        """Returns `bytes32((maxPriorityFeePerGas << 128) | maxFeePerGas)`."""
        return "0x" + pack_u128_pair(self.max_priority_fee_per_gas, self.max_fee_per_gas).hex()

    @classmethod
    def build_and_sign(
        cls,
        chain_id: int,
        calls: List[tuple[str, int, bytes]],
        private_key: str | bytes,
        account_nonce: int = 0,
        max_fee_per_gas_gwei: float | str = 25.0,
        max_priority_fee_gwei: float | str = 1.5,
        already_delegated: bool = False,
        init_code: bytes = b"",
        paymaster_and_data: bytes = b"",
    ) -> UserOperationBatch:
        import eth_abi

        if isinstance(private_key, str):
            clean_key = private_key[2:] if private_key.startswith("0x") else private_key
            key_bytes = bytes.fromhex(clean_key)
        else:
            key_bytes = private_key

        key_obj = keys.PrivateKey(key_bytes)
        sender = key_obj.public_key.to_checksum_address()

        # Simple7702Account.executeBatch((address,uint256,bytes)[])
        selector = keccak(b"executeBatch((address,uint256,bytes)[])")[:4]
        normalized_calls = [
            (target.lower(), int(val), bytes(data)) for target, val, data in calls
        ]
        encoded_args = eth_abi.encode(["(address,uint256,bytes)[]"], [normalized_calls])
        call_data_bytes = selector + encoded_args
        call_data_hex = "0x" + call_data_bytes.hex()

        auth = (
            None
            if already_delegated
            else EIP7702Authorization.sign(
                chain_id=chain_id,
                implementation=SIMPLE_7702_ACCOUNT_ADDRESS,
                nonce=account_nonce,
                private_key=key_bytes,
            )
        )

        call_gas = 950_000 * len(calls)
        ver_gas = 150_000
        pre_ver_gas = 60_000
        max_fee_wei = TransactionBuilder._gwei_to_wei(max_fee_per_gas_gwei)
        prio_fee_wei = TransactionBuilder._gwei_to_wei(max_priority_fee_gwei)

        op_hash_bytes = compute_packed_user_op_hash_v08(
            sender=sender,
            nonce=account_nonce,
            init_code=init_code,
            call_data=call_data_bytes,
            verification_gas_limit=ver_gas,
            call_gas_limit=call_gas,
            pre_verification_gas=pre_ver_gas,
            max_priority_fee_per_gas=prio_fee_wei,
            max_fee_per_gas=max_fee_wei,
            paymaster_and_data=paymaster_and_data,
            chain_id=chain_id,
            entry_point=ENTRYPOINT_V08_ADDRESS,
        )
        v, r, s = sign_transaction_hash(key_obj, op_hash_bytes)
        sig_bytes = r.to_bytes(32, "big") + s.to_bytes(32, "big") + bytes([v + 27])

        return cls(
            sender=sender,
            chain_id=chain_id,
            nonce=account_nonce,
            call_data=call_data_hex,
            call_gas_limit=call_gas,
            verification_gas_limit=ver_gas,
            pre_verification_gas=pre_ver_gas,
            max_fee_per_gas=max_fee_wei,
            max_priority_fee_per_gas=prio_fee_wei,
            authorization=auth,
            user_op_hash="0x" + op_hash_bytes.hex(),
            signature="0x" + sig_bytes.hex(),
            init_code=init_code,
            paymaster_and_data=paymaster_and_data,
        )

    def to_rpc_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "sender": self.sender,
            "nonce": hex(self.nonce),
            "callData": self.call_data,
            "callGasLimit": hex(self.call_gas_limit),
            "verificationGasLimit": hex(self.verification_gas_limit),
            "preVerificationGas": hex(self.pre_verification_gas),
            "maxFeePerGas": hex(self.max_fee_per_gas),
            "maxPriorityFeePerGas": hex(self.max_priority_fee_per_gas),
            "signature": self.signature,
        }
        if self.authorization is not None:
            payload["eip7702Auth"] = self.authorization.to_dict()
        return payload


@dataclass(frozen=True)
class MultiShieldBundle:
    """Dual multi-shield execution bundle (UserOperation + sequential EIP-1559 fallback)."""

    chain_id: int
    sender: str
    tickets: List[Ticket]
    total_wei: int
    user_operation: Optional[UserOperationBatch]
    eip1559_txs: List[SignedTransaction]

    @property
    def total_eth_str(self) -> str:
        from decimal import Decimal
        val = (Decimal(self.total_wei) / (Decimal(10) ** 18)).normalize()
        return format(val, "f")

