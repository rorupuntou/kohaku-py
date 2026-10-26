"""Offline Ticket Lifecycle and Anonymous Invoices Management for EDW.

Tickets follow a strict cryptographic state machine:
- DRAFT: Generated offline. Contains nullifier, secret, and commitment. Unmined.
- MINED: Deposit transaction confirmed on Ethereum L1, added to the Merkle tree leaf. Spendable.
- SPENT: Nullifier revealed on withdrawal and marked on-chain. Unspendable.

Anonymous Invoices allow sharing only the public commitment and amount,
allowing another party (or an old wallet) to fund the ticket without
disclosing secrets or destination address.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import json
import os
import time
from typing import Any, List, Optional

from kohaku.edw.storage.database import EncryptedDatabase
from kohaku.tornado.note import TornadoNote
from kohaku.tornado.pools import ALL_POOLS, decompose_eth_amount, get_pool
from kohaku.tornado.tx import build_deposit_transactions


class TicketState(str, Enum):
    DRAFT = "DRAFT"      # Created offline, unmined, 0 on-chain traces
    MINED = "MINED"      # Confirmed deposit in Merkle tree, spendable
    SPENT = "SPENT"      # Nullifier hash revealed on L1, burned


@dataclass
class TicketInvoice:
    """Public invoice containing ONLY the commitment and payment details.

    Safe to share publicly. Does not leak private secrets or destination.
    """
    version: int
    chain_id: int
    currency: str
    amount: str
    pool_id: str
    contract_address: str
    commitment: str

    def to_uri(self) -> str:
        """Serialize into compact URI format:

        edw-invoice:v1:<chain_id>:<currency>:<amount>:<contract>:<commitment>
        """
        return f"edw-invoice:v1:{self.chain_id}:{self.currency.upper()}:{self.amount}:{self.contract_address}:{self.commitment}"

    @classmethod
    def from_uri(cls, uri: str) -> TicketInvoice:
        parts = uri.strip().split(":")
        if len(parts) != 7 or parts[0] != "edw-invoice" or parts[1] != "v1":
            raise ValueError(f"Invalid invoice URI format: {uri}")
        chain_id = int(parts[2])
        currency = parts[3].upper()
        amount = parts[4]
        contract = parts[5].lower()
        commitment = parts[6]

        pool_id = f"tornado-cash-{chain_id}-{currency.lower()}-{amount}"
        return cls(
            version=1,
            chain_id=chain_id,
            currency=currency,
            amount=amount,
            pool_id=pool_id,
            contract_address=contract,
            commitment=commitment,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Ticket:
    """Complete private ticket with secret material and lifecycle tracking."""
    id: str
    currency: str
    amount: str
    chain_id: int
    pool_id: str
    nullifier_hex: str
    secret_hex: str
    commitment_hex: str
    nullifier_hash_hex: str
    state: TicketState
    label: str = ""
    created_at: int = 0
    leaf_index: Optional[int] = None
    deposit_block: Optional[int] = None
    deposit_tx_hash: Optional[str] = None
    spent_block: Optional[int] = None
    spent_tx_hash: Optional[str] = None

    @classmethod
    def create_draft(
        cls,
        currency: str = "ETH",
        amount: str = "0.1",
        chain_id: int = 1,
        label: str = "",
    ) -> Ticket:
        """Create a new offline draft ticket with freshly generated 31-byte secrets."""
        pool_id = f"tornado-cash-{chain_id}-{currency.lower()}-{amount}"
        pool = get_pool(pool_id)  # validates pool existence

        nullifier = os.urandom(31)
        secret = os.urandom(31)
        note = TornadoNote(
            currency=pool.asset,
            amount=pool.amount,
            chain_id=pool.chain_id,
            nullifier=nullifier,
            secret=secret,
        )

        ticket_id = note.commitment_hex[2:18]
        return cls(
            id=ticket_id,
            currency=pool.asset,
            amount=pool.amount,
            chain_id=pool.chain_id,
            pool_id=pool.id,
            nullifier_hex=nullifier.hex(),
            secret_hex=secret.hex(),
            commitment_hex=note.commitment_hex,
            nullifier_hash_hex=note.nullifier_hash_hex,
            state=TicketState.DRAFT,
            label=label,
            created_at=int(time.time()),
        )

    def to_tornado_note(self) -> TornadoNote:
        """Convert to cryptographic TornadoNote object for Merkle/ZK proving."""
        return TornadoNote(
            currency=self.currency,
            amount=self.amount,
            chain_id=self.chain_id,
            nullifier=bytes.fromhex(self.nullifier_hex),
            secret=bytes.fromhex(self.secret_hex),
            leaf_index=self.leaf_index,
            spent=(self.state == TicketState.SPENT),
        )

    def to_invoice(self) -> TicketInvoice:
        """Export safe public invoice without revealing nullifier or secret."""
        pool = get_pool(self.pool_id)
        return TicketInvoice(
            version=1,
            chain_id=self.chain_id,
            currency=self.currency,
            amount=self.amount,
            pool_id=self.pool_id,
            contract_address=pool.contract_address,
            commitment=self.commitment_hex,
        )

    @property
    def amount_wei(self) -> int:
        return get_pool(self.pool_id).amount_wei

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["state"] = self.state.value
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Ticket:
        data = dict(d)
        data["state"] = TicketState(data["state"])
        return cls(**data)


class TicketManager:
    """Manages encrypted tickets index and state transitions inside EDW storage."""

    def __init__(self, db: EncryptedDatabase, profile_m: int = 0, profile_x: int = 0):
        self.db = db
        self.scope = f"tickets:{profile_m}:{profile_x}"

    def _get_ticket_ids(self) -> List[str]:
        return self.db.get_json(self.scope, "index", default=[])

    def _save_ticket_ids(self, ids: List[str]) -> None:
        self.db.set_json(self.scope, "index", ids)

    def save_ticket(self, ticket: Ticket) -> None:
        ids = self._get_ticket_ids()
        if ticket.id not in ids:
            ids.append(ticket.id)
            self._save_ticket_ids(ids)
        self.db.set_json(self.scope, f"ticket:{ticket.id}", ticket.to_dict())

    def get_ticket(self, ticket_id: str) -> Optional[Ticket]:
        data = self.db.get_json(self.scope, f"ticket:{ticket_id}")
        if not data:
            return None
        return Ticket.from_dict(data)

    def create_draft_ticket(
        self,
        currency: str = "ETH",
        amount: str = "0.1",
        chain_id: int = 1,
        label: str = "",
    ) -> Ticket:
        ticket = Ticket.create_draft(currency=currency, amount=amount, chain_id=chain_id, label=label)
        self.save_ticket(ticket)
        return ticket

    def create_multi_shield_tickets(
        self,
        amount_wei: int,
        chain_id: int = 1,
        label: str = "Multi-Shield",
    ) -> List[Ticket]:
        """Decompose `amount_wei` into native ETH pools and create & save draft tickets."""
        pools = decompose_eth_amount(amount_wei, chain_id=chain_id)
        created: List[Ticket] = []
        for idx, pool in enumerate(pools):
            note_label = f"{label} ({idx + 1}/{len(pools)}: {pool.amount} ETH)"
            ticket = self.create_draft_ticket(
                currency=pool.asset,
                amount=pool.amount,
                chain_id=pool.chain_id,
                label=note_label,
            )
            created.append(ticket)
        return created

    def list_tickets(self, state: Optional[TicketState] = None) -> List[Ticket]:
        ids = self._get_ticket_ids()
        tickets = []
        for tid in ids:
            t = self.get_ticket(tid)
            if t is not None:
                if state is None or t.state == state:
                    tickets.append(t)
        return tickets

    def select_exact_tickets(
        self, amount_wei: int, currency: str = "ETH", chain_id: Optional[int] = None
    ) -> List[Ticket]:
        """Select unspent MINED tickets whose denominations sum exactly to `amount_wei` (largest first).

        Matches `edw_core::vault::tornadocash::exact_notes`.
        """
        if amount_wei <= 0:
            raise ValueError("Amount must be greater than zero")

        available = [
            t
            for t in self.list_tickets(state=TicketState.MINED)
            if t.currency.upper() == currency.upper()
            and (chain_id is None or t.chain_id == chain_id)
        ]
        available.sort(key=lambda t: t.amount_wei, reverse=True)

        remaining = amount_wei
        chosen: List[Ticket] = []
        for t in list(available):
            if t.amount_wei <= remaining:
                chosen.append(t)
                remaining -= t.amount_wei
                if remaining == 0:
                    break

        if remaining != 0:
            raise ValueError(
                f"Held MINED notes cannot make {amount_wei} wei exactly (short by {remaining} wei)"
            )
        return chosen

    def select_cover_tickets(
        self, amount_wei: int, currency: str = "ETH", chain_id: Optional[int] = None
    ) -> List[Ticket]:
        """Select the smallest largest-first set of unspent MINED tickets covering at least `amount_wei`.

        Whole denominations are taken largest first; any remainder takes the smallest held note
        that covers it. Matches `edw_core::vault::tornadocash::cover_notes`.
        """
        if amount_wei <= 0:
            raise ValueError("Amount must be greater than zero")

        available = [
            t
            for t in self.list_tickets(state=TicketState.MINED)
            if t.currency.upper() == currency.upper()
            and (chain_id is None or t.chain_id == chain_id)
        ]
        available.sort(key=lambda t: t.amount_wei, reverse=True)

        remaining = amount_wei
        chosen: List[Ticket] = []
        leftover: List[Ticket] = []
        for t in available:
            if t.amount_wei <= remaining and remaining > 0:
                chosen.append(t)
                remaining -= t.amount_wei
            else:
                leftover.append(t)

        if remaining == 0:
            return chosen

        leftover.sort(key=lambda t: t.amount_wei)
        for extra in leftover:
            if extra.amount_wei >= remaining:
                chosen.append(extra)
                return chosen

        raise ValueError(f"Held MINED notes cannot cover {amount_wei} wei")

    def get_ticket_by_commitment(self, commitment_hex: str) -> Optional[Ticket]:
        clean = commitment_hex.lower()
        for t in self.list_tickets():
            if t.commitment_hex.lower() == clean:
                return t
        return None

    def get_ticket_by_nullifier_hash(self, nullifier_hash_hex: str) -> Optional[Ticket]:
        clean = nullifier_hash_hex.lower()
        for t in self.list_tickets():
            if t.nullifier_hash_hex.lower() == clean:
                return t
        return None

    def mark_mined(
        self,
        commitment_hex: str,
        leaf_index: int,
        block_number: Optional[int] = None,
        tx_hash: Optional[str] = None,
    ) -> bool:
        """Transitions ticket from DRAFT -> MINED."""
        ticket = self.get_ticket_by_commitment(commitment_hex)
        if not ticket:
            return False
        ticket.state = TicketState.MINED
        ticket.leaf_index = leaf_index
        ticket.deposit_block = block_number
        ticket.deposit_tx_hash = tx_hash
        self.save_ticket(ticket)
        return True

    def mark_spent(
        self,
        nullifier_hash_hex: str,
        block_number: Optional[int] = None,
        tx_hash: Optional[str] = None,
    ) -> bool:
        """Transitions ticket from MINED -> SPENT."""
        ticket = self.get_ticket_by_nullifier_hash(nullifier_hash_hex)
        if not ticket:
            return False
        ticket.state = TicketState.SPENT
        ticket.spent_block = block_number
        ticket.spent_tx_hash = tx_hash
        self.save_ticket(ticket)
        return True

    def get_spendable_balance_wei(self, currency: str = "ETH") -> int:
        """Calculates exact total spendable (MINED and unspent) holdings in wei."""
        total_wei = 0
        for t in self.list_tickets(state=TicketState.MINED):
            if t.currency.upper() == currency.upper():
                total_wei += t.amount_wei
        return total_wei

    def get_spendable_balance(self, currency: str = "ETH") -> float:
        """Calculates total spendable (MINED and unspent) holdings in currency using exact Decimal summation."""
        from decimal import Decimal

        total = Decimal("0")
        for t in self.list_tickets(state=TicketState.MINED):
            if t.currency.upper() == currency.upper():
                total += Decimal(str(t.amount))
        return float(total)

    @staticmethod
    def prepare_invoice_deposit(invoice_uri_or_dict: str | dict) -> dict[str, Any]:
        """Prepares transaction data for funding an invoice.

        Can be called by anyone wishing to pay an anonymous invoice.
        """
        if isinstance(invoice_uri_or_dict, str):
            if invoice_uri_or_dict.startswith("edw-invoice:"):
                invoice = TicketInvoice.from_uri(invoice_uri_or_dict)
            else:
                invoice = TicketInvoice(**json.loads(invoice_uri_or_dict))
        else:
            invoice = TicketInvoice(**invoice_uri_or_dict)

        pool = get_pool(invoice.pool_id)
        # Function selector for deposit(bytes32): 0xb214faa5
        commitment_clean = invoice.commitment.lower().replace("0x", "").zfill(64)
        calldata = f"0xb214faa5{commitment_clean}"

        return {
            "to": pool.contract_address,
            "value_wei": pool.amount_wei,
            "value_eth": pool.amount,
            "data": calldata,
            "chain_id": pool.chain_id,
            "commitment": invoice.commitment,
        }
