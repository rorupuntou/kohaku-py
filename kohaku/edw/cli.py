"""Command-line interface for the native Python Ethereum Desktop Wallet (EDW).

Matches the EDW specification with privacy-first sovereign defaults:
- Zero telemetry, zero web2 dependencies
- Native Tor/SOCKS5 proxy support
- Encrypted blinded datastore with Argon2id + ChaCha20-Poly1305
- Gasless unshielding to virgin addresses
- Anonymous Invoices (payment requests)
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from typing import Optional

from eth_account import Account
import rlp

from kohaku.edw.p2p import P2PBroadcaster
from kohaku.edw.storage.cipher import InvalidPasswordError
from kohaku.edw.storage.database import EncryptedDatabase
from kohaku.edw.storage.keyring import KeyringManager
from kohaku.edw.tickets import TicketInvoice, TicketManager, TicketState
from kohaku.edw.tx_builder import TransactionBuilder
from kohaku.tornado.pools import MAINNET_POOLS, get_pool


def get_default_data_dir() -> Path:
    env_dir = os.environ.get("EDW_DATA_DIR")
    if env_dir:
        return Path(env_dir)
    return Path.home() / ".edw"


def open_or_init_database(data_dir: Path, chain_id: int, password: Optional[str] = None) -> EncryptedDatabase:
    net_dir = data_dir / str(chain_id)
    if not (net_dir / EncryptedDatabase.HEADER_FILE).exists():
        if not password:
            import getpass
            password = getpass.getpass("Initialize new EDW datastore password: ")
            confirm = getpass.getpass("Confirm password: ")
            if password != confirm:
                raise ValueError("Passwords do not match")
        return EncryptedDatabase.initialize(net_dir, password)

    if not password:
        import getpass
        password = getpass.getpass("Enter EDW decryption password: ")
    return EncryptedDatabase.open(net_dir, password)


def cmd_profile_new(args: argparse.Namespace) -> int:
    db = open_or_init_database(args.data_dir, args.chain_id, password=args.password)
    km = KeyringManager(db)

    # Generate new random 12-word phrase
    Account.enable_unaudited_hdwallet_features()
    acct, phrase = Account.create_with_mnemonic()

    m_idx = km.add_mnemonic(phrase)
    profile = km.create_profile(args.name, mnemonic_index=m_idx, profile_index=0)
    addr0 = km.derive_address(m_idx, 0, 0)

    print(f"Created new profile '{profile.name}' (Mnemonic #{m_idx}, Account #0)")
    print(f"Anchor Address (m/44'/60'/0'/0/0): {addr0}")
    print("\nRECOVERY PHRASE (KEEP SECRET AND OFFLINE):")
    print(f"  {phrase}\n")
    return 0


def cmd_profile_import(args: argparse.Namespace) -> int:
    db = open_or_init_database(args.data_dir, args.chain_id, password=args.password)
    km = KeyringManager(db)

    phrase = args.mnemonic.strip()
    m_idx = km.add_mnemonic(phrase)
    profile = km.create_profile(args.name, mnemonic_index=m_idx, profile_index=args.account)
    addr0 = km.derive_address(m_idx, args.account, 0)

    print(f"Imported profile '{profile.name}' (Mnemonic #{m_idx}, Account #{args.account})")
    print(f"Anchor Address: {addr0}")
    return 0


def cmd_profile_list(args: argparse.Namespace) -> int:
    db = open_or_init_database(args.data_dir, args.chain_id, password=args.password)
    km = KeyringManager(db)
    profiles = km.list_profiles()
    if not profiles:
        print("No profiles configured. Run 'edw profile new' to create one.")
        return 0

    print(f"{'PROFILE':<20} {'MNEMONIC':<10} {'ACCOUNT':<10} {'ANCHOR ADDRESS'}")
    print("-" * 75)
    for p in profiles:
        addr = km.derive_address(p.mnemonic_index, p.profile_index, 0)
        print(f"{p.name:<20} #{p.mnemonic_index:<9} #{p.profile_index:<9} {addr}")
    return 0


def cmd_next_fresh_address(args: argparse.Namespace) -> int:
    db = open_or_init_database(args.data_dir, args.chain_id, password=args.password)
    km = KeyringManager(db)
    profiles = km.list_profiles()
    if not profiles:
        print("Error: No profiles found. Run 'edw profile new' first.", file=sys.stderr)
        return 1

    p = profiles[0]
    fresh = km.get_next_fresh_address(p.mnemonic_index, p.profile_index, peek=args.peek)
    mode = "(PEEK)" if args.peek else "(STORED & ROTATED)"
    print(f"{fresh} {mode}")
    return 0


def cmd_balance(args: argparse.Namespace) -> int:
    db = open_or_init_database(args.data_dir, args.chain_id, password=args.password)
    km = KeyringManager(db)
    tm = TicketManager(db, profile_m=0, profile_x=0)

    profiles = km.list_profiles()
    anchor_addr = km.derive_address(0, 0, 0) if profiles else "N/A"
    spendable_private = tm.get_spendable_balance("ETH")
    unmined_tickets = tm.list_tickets(state=TicketState.DRAFT)
    mined_tickets = tm.list_tickets(state=TicketState.MINED)
    spent_tickets = tm.list_tickets(state=TicketState.SPENT)

    print("════════════════════════════════════════════════════════════════════════════")
    print("                    EDW-PY SOVEREIGN WALLET HOLDINGS                        ")
    print("════════════════════════════════════════════════════════════════════════════")
    print(f"Network Chain ID:    {args.chain_id} ({'Mainnet' if args.chain_id == 1 else 'Sepolia'})")
    print(f"Anchor Address:      {anchor_addr}")
    print(f"Private Spendable:   {spendable_private:.4f} ETH (Shielded Pools)")
    print(f"Pending Invoices:    {len(unmined_tickets)} draft ticket(s)")
    print(f"Mined / Active:      {len(mined_tickets)} note(s)")
    print(f"Spent / Withdrawn:   {len(spent_tickets)} note(s)")

    if args.verbose:
        print("\n--- SHIELDED NOTES DETAIL ---")
        for t in mined_tickets:
            print(f"  • [MINED] {t.amount} {t.currency} | ID: {t.id} | Leaf: #{t.leaf_index} | Comm: {t.commitment_hex[:16]}...")
        for t in unmined_tickets:
            print(f"  • [DRAFT] {t.amount} {t.currency} | ID: {t.id} | Comm: {t.commitment_hex[:16]}... (Waiting for deposit)")
    print("════════════════════════════════════════════════════════════════════════════")
    return 0


def cmd_invoice_new(args: argparse.Namespace) -> int:
    db = open_or_init_database(args.data_dir, args.chain_id, password=args.password)
    tm = TicketManager(db, profile_m=0, profile_x=0)

    ticket = tm.create_draft_ticket(
        currency=args.currency.upper(),
        amount=args.amount,
        chain_id=args.chain_id,
        label=args.label or "Invoice",
    )
    invoice = ticket.to_invoice()
    uri = invoice.to_uri()

    print("Generated Anonymous Payment Invoice (0-Identity Leaks):")
    print(f"  Invoice URI:     {uri}")
    print(f"  Deposit Amount:  {invoice.amount} {invoice.currency}")
    print(f"  Target Pool:     {invoice.contract_address}")
    print(f"  Commitment:      {invoice.commitment}")
    print("\nShare this URI or Commitment with whoever wants to pay you.")
    print("They will fund the ticket on Ethereum L1, and only YOU will be able to withdraw it.")
    return 0


def cmd_invoice_pay(args: argparse.Namespace) -> int:
    prep = TicketManager.prepare_invoice_deposit(args.invoice)
    print("Invoice Payment Prepared:")
    print(f"  To Contract:  {prep['to']}")
    print(f"  Amount:       {prep['value_eth']} ETH ({prep['value_wei']} wei)")
    print(f"  Calldata:     {prep['data'][:42]}...")

    if not args.private_key:
        print("\n[!] To broadcast directly, pass --private-key <hex>. Otherwise copy the calldata above.")
        return 0

    broadcaster = P2PBroadcaster(tor_proxy=args.tor_proxy)
    signed = TransactionBuilder.build_deposit_tx(
        commitment_hex=prep["commitment"],
        pool_id=f"tornado-cash-{prep['chain_id']}-eth-{prep['value_eth']}",
        nonce=args.nonce or 0,
        private_key=args.private_key,
    )
    print(f"\nBroadcasting raw transaction (Hash: {signed.tx_hash})...")
    res = broadcaster.broadcast_raw_tx(signed.raw_hex)
    print(f"✓ Success! Accepted by peer: {res.peer}")
    return 0


def cmd_tui(args: argparse.Namespace) -> int:
    from kohaku.tui.app import run_tui
    run_tui(mnemonic=args.mnemonic, chain_id=args.chain_id)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="edw",
        description="Ethereum Desktop Wallet (EDW) - Pure Python Sovereign Privacy Engine",
    )
    parser.add_argument("--data-dir", default=get_default_data_dir(), type=Path, help="Storage datastore directory")
    parser.add_argument("--chain-id", default=1, type=int, help="Network chain ID (1 for mainnet, 11155111 for sepolia)")
    parser.add_argument("--password", help="Decryption password (omit to prompt securely)")
    parser.add_argument("--tor-proxy", default=None, help="Tor SOCKS5 proxy (e.g. 127.0.0.1:9050)")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # balance
    bal_p = subparsers.add_parser("balance", help="View public, private and total holdings")
    bal_p.add_argument("--verbose", action="store_true", help="List detailed notes and vaults")
    bal_p.set_defaults(func=cmd_balance)

    # next-fresh-address
    nfa_p = subparsers.add_parser("next-fresh-address", help="Get next virgin address with 0 on-chain history")
    nfa_p.add_argument("--peek", action="store_true", help="Print address without advancing the cursor")
    nfa_p.set_defaults(func=cmd_next_fresh_address)

    # profile
    prof_p = subparsers.add_parser("profile", help="Manage wallet profiles")
    prof_sub = prof_p.add_subparsers(dest="subcommand", required=True)

    p_new = prof_sub.add_parser("new", help="Create a new profile with fresh recovery phrase")
    p_new.add_argument("--name", default="default", help="Profile name")
    p_new.set_defaults(func=cmd_profile_new)

    p_import = prof_sub.add_parser("import", help="Import profile from mnemonic recovery phrase")
    p_import.add_argument("--name", default="imported", help="Profile name")
    p_import.add_argument("--mnemonic", required=True, help="12 or 24-word BIP-39 mnemonic phrase")
    p_import.add_argument("--account", type=int, default=0, help="BIP-44 account index")
    p_import.set_defaults(func=cmd_profile_import)

    p_list = prof_sub.add_parser("list", help="List all configured profiles")
    p_list.set_defaults(func=cmd_profile_list)

    # invoice
    inv_p = subparsers.add_parser("invoice", help="Manage anonymous invoices (payment requests)")
    inv_sub = inv_p.add_subparsers(dest="subcommand", required=True)

    inv_new = inv_sub.add_parser("new", help="Create an anonymous payment invoice (0 leaks)")
    inv_new.add_argument("--amount", default="0.1", help="Amount denomination (0.1, 1, 10, 100)")
    inv_new.add_argument("--currency", default="ETH", help="Asset (default: ETH)")
    inv_new.add_argument("--label", default="", help="Optional local note label")
    inv_new.set_defaults(func=cmd_invoice_new)

    inv_pay = inv_sub.add_parser("pay", help="Pay / fund an anonymous invoice")
    inv_pay.add_argument("invoice", help="Invoice URI (edw-invoice:...) or JSON string")
    inv_pay.add_argument("--private-key", help="Funding private key to sign and broadcast")
    inv_pay.add_argument("--nonce", type=int, help="Account nonce")
    inv_pay.set_defaults(func=cmd_invoice_pay)

    # tui
    tui_p = subparsers.add_parser("tui", help="Launch interactive Terminal Desktop Wallet UI")
    tui_p.add_argument("--mnemonic", help="Optional BIP-39 mnemonic to pre-load")
    tui_p.set_defaults(func=cmd_tui)

    args = parser.parse_args()
    try:
        sys.exit(args.func(args))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
