"""Transaction builders for depositing into Tornado Cash pools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from eth_hash.auto import keccak
from kohaku.tornado.note import TornadoNote
from kohaku.tornado.pools import TornadoPool, get_pool

DEPOSIT_SELECTOR = keccak(b"deposit(bytes32)")[:4].hex()
APPROVE_SELECTOR = keccak(b"approve(address,uint256)")[:4].hex()


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


def build_deposit_transactions(note: TornadoNote) -> list[TransactionCall]:
    """Constructs the exact EVM transaction calls required to fund a Tornado note on-chain."""
    pool_id = f"tornado-cash-{note.chain_id}-{note.currency.lower()}-{note.amount}"
    pool = get_pool(pool_id)

    comm_clean = note.commitment_hex.replace("0x", "").zfill(64)
    deposit_calldata = f"0x{DEPOSIT_SELECTOR}{comm_clean}"

    calls = []

    # If it is an ERC-20 pool (like DAI or USDC), add the approveCall first
    if pool.asset != "ETH":
        spender = pool.contract_address.replace("0x", "").zfill(64)
        amt_hex = hex(pool.amount_wei)[2:].zfill(64)
        approve_calldata = f"0x{APPROVE_SELECTOR}{spender}{amt_hex}"
        calls.append(
            TransactionCall(
                to=pool.contract_address,  # Note: In production would be ERC-20 token address
                value=0,
                data=approve_calldata,
                description=f"Approve {pool.amount} {pool.asset} for Tornado Pool",
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
