from __future__ import annotations

import argparse
import json
import sys

from kohaku.privacy_pools.note import PrivacyPoolNote
from kohaku.sync.client import DEFAULT_SAGA_URL, SagaClient
from kohaku.tornado.note import TornadoNote
from kohaku.tornado.pools import ALL_POOLS, MAINNET_POOLS
from kohaku.tornado.vault import TornadoVault


def cmd_sync_list(client: SagaClient, args: argparse.Namespace) -> int:
    manifest = client.get_manifest()
    print(f"Saga CDN: {client.base_url}")
    print(f"Updated at: {manifest.updated_at} (v{manifest.version})\n")
    print(f"{'PROTOCOL ID':<35} {'CHAIN':<8} {'CHUNKS':<8} {'BLOCK RANGE'}")
    print("-" * 75)

    for p_id in sorted(manifest.available_protocols.keys()):
        proto = manifest.available_protocols[p_id]
        rng = proto.block_range
        range_str = f"[{rng[0]}..{rng[1]}]" if rng else "empty"
        print(f"{p_id:<35} {proto.chain_id:<8} {proto.total_chunks:<8} {range_str}")
    return 0


def cmd_tornado_pools(args: argparse.Namespace) -> int:
    print(f"{'POOL ID':<32} {'DENOMINATION':<15} {'CONTRACT ADDRESS':<44} {'DEPLOYED'}")
    print("-" * 105)
    for p_id, p in sorted(ALL_POOLS.items()):
        denom = f"{p.amount} {p.asset}"
        print(f"{p_id:<32} {denom:<15} {p.contract_address:<44} {p.deployed_block}")
    return 0


def cmd_tornado_new_note(args: argparse.Namespace) -> int:
    note = TornadoNote.create(currency=args.currency, amount=args.amount, chain_id=args.chain_id)
    print("New Tornado Cash Note Generated:")
    print(f"  Note URI:        {note.to_note_string()}")
    print(f"  Commitment:      {note.commitment_hex}")
    print(f"  Nullifier Hash:  {note.nullifier_hash_hex}")
    print(f"  Denomination:    {note.amount} {note.currency} (Chain ID {note.chain_id})")
    return 0


def cmd_tornado_check_note(args: argparse.Namespace) -> int:
    note = TornadoNote.from_note_string(args.note)
    pool_id = f"tornado-cash-{note.chain_id}-{note.currency.lower()}-{note.amount}"
    print(f"Scanning pool {pool_id} via Saga CDN...")

    def progress(filename: str, current: int, total: int) -> None:
        sys.stdout.write(f"  [{current}/{total}] Fetching and scanning {filename}...\n")
        sys.stdout.flush()

    vault = TornadoVault(pool_id)
    status = vault.check_note(note, on_chunk=progress)

    print("\nPool Statistics:")
    print(f"  Total Historical Deposits:    {status['total_deposits']}")
    print(f"  Total Historical Withdrawals: {status['total_withdrawals']}")

    print("\nNote Status:")
    print(f"  Commitment:     {status['commitment']}")
    print(f"  Nullifier Hash: {status['nullifier_hash']}")
    print(f"  Mined on-chain: {'YES ✓' if status['mined'] else 'NO ✗'}")
    if status['mined']:
        print(f"  Leaf Index:     {status['leaf_index']}")
    print(f"  Spent:          {'YES (Withdrawal seen) ✗' if status['spent'] else 'NO (Unspent) ✓'}")
    print(f"  Spendable:      {'YES ✓' if status['spendable'] else 'NO ✗'}")
    return 0


def cmd_tornado_deposit_calldata(args: argparse.Namespace) -> int:
    from kohaku.tornado.tx import build_deposit_transactions

    note = TornadoNote.from_note_string(args.note)
    calls = build_deposit_transactions(note)

    print("Deposit Transactions to Fund Note on-chain:\n")
    for idx, call in enumerate(calls, 1):
        print(f"Call #{idx}: {call.description}")
        print(f"  To:       {call.to}")
        print(f"  Value:    {call.value} wei ({call.value / 10**18} ETH)")
        print(f"  Calldata: {call.data}")
        print(f"\n  CLI Command (Cast):")
        print(f"    cast send {call.to} {call.data} --value {call.value} --private-key <YOUR_KEY>")
        print()
    return 0


def cmd_tornado_scan_wallet(args: argparse.Namespace) -> int:
    from kohaku.tornado.keychain import TornadoKeychain

    if args.mnemonic:
        keychain = TornadoKeychain.from_mnemonic(args.mnemonic, profile_index=args.profile)
    elif args.private_key:
        keychain = TornadoKeychain(args.private_key)
    else:
        sys.stderr.write("Error: Must provide --mnemonic or --private-key\n")
        return 1

    print(f"Scanning Tornado Cash notes for derived Keychain address {keychain.address}...")

    def progress(nonce: int, empty: int) -> None:
        sys.stdout.write(f"\r  Checking nonce {nonce}... ({empty}/20 consecutive empty nonces)")
        sys.stdout.flush()

    found = keychain.scan_wallet(on_progress=progress)
    print("\n\nScan Completed!\n")

    if not found:
        print("No historical or active notes found for this seed phrase.")
        return 0

    print(f"{'NONCE':<8} {'POOL':<25} {'AMOUNT':<12} {'LEAF':<8} {'STATUS'}")
    print("-" * 65)
    total_spendable = 0.0
    for n in found:
        status_str = "SPENDABLE ✓" if n["spendable"] else ("SPENT ✗" if n["spent"] else "UNMINED")
        print(f"{n['nonce']:<8} {n['pool']:<25} {n['amount']:<12} {n['leaf_index']:<8} {status_str}")
        if n["spendable"] and "ETH" in n["amount"]:
            total_spendable += float(n["amount"].split()[0])

    print("-" * 65)
    print(f"Total Spendable Balance: {total_spendable:.4f} ETH")
    return 0


def cmd_privacy_pools_new_note(args: argparse.Namespace) -> int:
    # Value in eth to wei
    value_wei = int(float(args.amount) * 10**18)
    note = PrivacyPoolNote.create(value=value_wei, label=args.label)
    print("New Privacy Pools Note Generated:")
    print(f"  Commitment:     {note.commitment_hex}")
    print(f"  Nullifier Hash: {note.nullifier_hash_hex}")
    print(f"  Value:          {args.amount} ETH ({value_wei} wei)")
    print(f"  Label:          {note.label}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="kohaku",
        description="Kohaku Python CLI: Privacy toolkit for Ethereum (Tornado Cash, Privacy Pools, Saga Sync).",
    )
    parser.add_argument("--url", default=DEFAULT_SAGA_URL, help="Saga CDN base URL")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # sync
    sync_parser = subparsers.add_parser("sync", help="Saga sync commands")
    sync_sub = sync_parser.add_subparsers(dest="subcommand", required=True)
    list_p = sync_sub.add_parser("list", help="List available protocols")
    list_p.set_defaults(func=lambda client, args: cmd_sync_list(client, args))

    # tornado
    tornado_parser = subparsers.add_parser("tornado", help="Tornado Cash commands")
    tornado_sub = tornado_parser.add_subparsers(dest="subcommand", required=True)

    pools_p = tornado_sub.add_parser("pools", help="List known Tornado Cash pools")
    pools_p.set_defaults(func=lambda client, args: cmd_tornado_pools(args))

    new_p = tornado_sub.add_parser("new-note", help="Generate a new Tornado Cash note")
    new_p.add_argument("--currency", default="ETH", help="Asset symbol (default: ETH)")
    new_p.add_argument("--amount", default="0.1", help="Pool denomination (default: 0.1)")
    new_p.add_argument("--chain-id", type=int, default=1, help="Network chain ID (default: 1)")
    new_p.set_defaults(func=lambda client, args: cmd_tornado_new_note(args))

    check_p = tornado_sub.add_parser("check-note", help="Check note status on-chain via Saga CDN")
    check_p.add_argument("note", help="Tornado note URI (tornado-<currency>-<amount>-<chain>-0x...)")
    check_p.set_defaults(func=lambda client, args: cmd_tornado_check_note(args))

    calldata_p = tornado_sub.add_parser("deposit-calldata", help="Get on-chain transaction calldata to fund a note")
    calldata_p.add_argument("note", help="Tornado note URI")
    calldata_p.set_defaults(func=lambda client, args: cmd_tornado_deposit_calldata(args))

    scan_p = tornado_sub.add_parser("scan-wallet", help="Recover all notes for a mnemonic seed phrase")
    scan_p.add_argument("--mnemonic", help="BIP-39 mnemonic seed phrase (12 or 24 words)")
    scan_p.add_argument("--private-key", help="Raw hex private key")
    scan_p.add_argument("--profile", type=int, default=0, help="Profile derivation index (default: 0)")
    scan_p.set_defaults(func=lambda client, args: cmd_tornado_scan_wallet(args))

    # privacy-pools
    pp_parser = subparsers.add_parser("privacy-pools", help="Privacy Pools commands")
    pp_sub = pp_parser.add_subparsers(dest="subcommand", required=True)

    pp_new = pp_sub.add_parser("new-note", help="Generate a new Privacy Pools note")
    pp_new.add_argument("--amount", default="1.0", help="Amount in ETH (arbitrary decimal amount)")
    pp_new.add_argument("--label", type=int, default=0, help="Association label (default: 0)")
    pp_new.set_defaults(func=lambda client, args: cmd_privacy_pools_new_note(args))

    args = parser.parse_args()
    client = SagaClient(base_url=args.url)

    try:
        sys.exit(args.func(client, args))
    except Exception as e:
        sys.stderr.write(f"Error: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
