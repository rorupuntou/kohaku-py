from pathlib import Path
import pytest

from kohaku.edw.storage.database import EncryptedDatabase
from kohaku.edw.tickets import Ticket, TicketInvoice, TicketManager, TicketState


def test_ticket_draft_and_invoice_generation():
    ticket = Ticket.create_draft(currency="ETH", amount="0.1", chain_id=1, label="Donation")
    assert ticket.state == TicketState.DRAFT
    assert ticket.amount == "0.1"
    assert ticket.nullifier_hex != ticket.secret_hex
    assert len(ticket.commitment_hex) == 66  # 0x + 64 hex chars
    assert len(ticket.nullifier_hash_hex) == 66

    # Convert to cryptographic TornadoNote
    note = ticket.to_tornado_note()
    assert note.commitment_hex == ticket.commitment_hex
    assert note.nullifier_hash_hex == ticket.nullifier_hash_hex

    # Generate safe public invoice
    invoice = ticket.to_invoice()
    assert invoice.currency == "ETH"
    assert invoice.amount == "0.1"
    assert invoice.commitment == ticket.commitment_hex
    assert invoice.contract_address == "0x12d66f87a04a9e220743712ce6d9bb1b5616b8fc"

    # Export & Parse URI
    uri = invoice.to_uri()
    assert uri.startswith("edw-invoice:v1:1:ETH:0.1:0x12d66f87a04a9e220743712ce6d9bb1b5616b8fc:")
    parsed = TicketInvoice.from_uri(uri)
    assert parsed.commitment == ticket.commitment_hex
    assert parsed.amount == "0.1"
    assert parsed.chain_id == 1

    # Prepare deposit calldata to pay invoice
    deposit_tx = TicketManager.prepare_invoice_deposit(uri)
    assert deposit_tx["to"] == "0x12d66f87a04a9e220743712ce6d9bb1b5616b8fc"
    assert deposit_tx["value_wei"] == 100_000_000_000_000_000  # 0.1 ETH
    assert deposit_tx["data"].startswith("0xb214faa5")  # deposit(bytes32) selector
    assert ticket.commitment_hex[2:] in deposit_tx["data"]


def test_ticket_manager_encrypted_lifecycle(tmp_path: Path):
    db = EncryptedDatabase.initialize(tmp_path / "tickets_store", "pass123")
    tm = TicketManager(db, profile_m=0, profile_x=0)

    # 1. Create offline drafts
    t1 = tm.create_draft_ticket(currency="ETH", amount="0.1", chain_id=1, label="Invoice 1")
    t2 = tm.create_draft_ticket(currency="ETH", amount="1", chain_id=1, label="Invoice 2")

    # Drafts are unmined, spendable balance is 0.0
    assert len(tm.list_tickets(state=TicketState.DRAFT)) == 2
    assert len(tm.list_tickets(state=TicketState.MINED)) == 0
    assert tm.get_spendable_balance("ETH") == 0.0

    # 2. Deposit confirmed on Ethereum L1: mark_mined
    success = tm.mark_mined(t1.commitment_hex, leaf_index=42, block_number=19000000, tx_hash="0xabc123")
    assert success is True

    # t1 is now MINED, spendable balance is 0.1 ETH
    assert len(tm.list_tickets(state=TicketState.DRAFT)) == 1
    assert len(tm.list_tickets(state=TicketState.MINED)) == 1
    assert tm.get_spendable_balance("ETH") == 0.1

    # Mine t2 as well
    tm.mark_mined(t2.commitment_hex, leaf_index=43, block_number=19000005)
    assert tm.get_spendable_balance("ETH") == 1.1

    # 3. Withdrawal executed on-chain: mark_spent
    t1_updated = tm.get_ticket(t1.id)
    assert t1_updated is not None
    assert t1_updated.leaf_index == 42

    spent_ok = tm.mark_spent(t1.nullifier_hash_hex, block_number=19000100, tx_hash="0xdef456")
    assert spent_ok is True

    # t1 is now SPENT, spendable balance is 1.0 ETH
    assert len(tm.list_tickets(state=TicketState.SPENT)) == 1
    assert len(tm.list_tickets(state=TicketState.MINED)) == 1
    assert tm.get_spendable_balance("ETH") == 1.0

    # Lookups
    by_comm = tm.get_ticket_by_commitment(t2.commitment_hex)
    assert by_comm is not None
    assert by_comm.id == t2.id

    by_null = tm.get_ticket_by_nullifier_hash(t1.nullifier_hash_hex)
    assert by_null is not None
    assert by_null.state == TicketState.SPENT
