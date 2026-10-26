"""Transaction builders for depositing into Tornado Cash pools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from eth_hash.auto import keccak
from kohaku.tornado.note import TornadoNote
from kohaku.tornado.pools import TOKEN_ADDRESSES, TornadoPool, get_pool

DEPOSIT_SELECTOR = keccak(b"deposit(bytes32)")[:4].hex()
APPROVE_SELECTOR = keccak(b"approve(address,uint256)")[:4].hex()
TRANSFER_SELECTOR = keccak(b"transfer(address,uint256)")[:4].hex()


@dataclass
class TransactionCall:
    to: str
    value: int
    data: str
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "to": self.to,
            "value": hex(self.value),
            "data": self.data,
            "description": self.description,
        }


Call = TransactionCall


def build_erc20_approve_call(
    token_address: str, spender_address: str, amount_wei: int
) -> TransactionCall:
    """Build an ERC-20 approve(spender, amount) EVM call."""
    spender_clean = spender_address.lower().replace("0x", "").zfill(64)
    amt_hex = hex(amount_wei)[2:].zfill(64)
    calldata = f"0x{APPROVE_SELECTOR}{spender_clean}{amt_hex}"
    return TransactionCall(
        to=token_address.lower(),
        value=0,
        data=calldata,
        description=f"Approve {amount_wei} tokens for {spender_address}",
    )


def build_erc20_transfer_call(
    token_address: str, recipient_address: str, amount_wei: int
) -> TransactionCall:
    """Build an ERC-20 transfer(recipient, amount) EVM call."""
    recipient_clean = recipient_address.lower().replace("0x", "").zfill(64)
    amt_hex = hex(amount_wei)[2:].zfill(64)
    calldata = f"0x{TRANSFER_SELECTOR}{recipient_clean}{amt_hex}"
    return TransactionCall(
        to=token_address.lower(),
        value=0,
        data=calldata,
        description=f"Transfer {amount_wei} tokens to {recipient_address}",
    )


def build_deposit_transactions(note: TornadoNote) -> list[TransactionCall]:
    """Constructs the exact EVM transaction calls required to fund a Tornado note on-chain."""
    pool_id = f"tornado-cash-{note.chain_id}-{note.currency.lower()}-{note.amount}"
    pool = get_pool(pool_id)

    comm_clean = note.commitment_hex.replace("0x", "").zfill(64)
    deposit_calldata = f"0x{DEPOSIT_SELECTOR}{comm_clean}"

    calls = []

    # If it is an ERC-20 pool, add the approveCall first
    if pool.asset != "ETH":
        token_addr = TOKEN_ADDRESSES.get((pool.chain_id, pool.asset), pool.contract_address)
        calls.append(
            build_erc20_approve_call(
                token_address=token_addr,
                spender_address=pool.contract_address,
                amount_wei=pool.amount_wei,
            )
        )

    # Deposit call
    calls.append(
        TransactionCall(
            to=pool.contract_address,
            value=pool.amount_wei if pool.asset == "ETH" else 0,
            data=deposit_calldata,
            description=f"Deposit {pool.amount} {pool.asset} into Tornado Pool (commitment: {note.commitment_hex[:10]}...)",
        )
    )

    return calls
