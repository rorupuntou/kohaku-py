from __future__ import annotations

import argparse
import json
import sys

from kohaku.privacy_pools.note import PrivacyPoolNote
from kohaku.privacy_pools.pools import ALL_PRIVACY_POOLS, get_privacy_pool
from kohaku.privacy_pools.vault import PrivacyPoolsVault
from kohaku.sync.client import DEFAULT_SAGA_URL, SagaClient
from kohaku.tornado.circuit import solidity_proof_from_snarkjs
from kohaku.tornado.note import TornadoNote
from kohaku.tornado.pools import ALL_POOLS, get_pool
from kohaku.tornado.vault import TornadoVault
from kohaku.tornado.withdraw import build_withdraw_transaction, build_withdrawal_inputs


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


def cmd_tornado_withdraw_inputs(args: argparse.Namespace) -> int:
    note = TornadoNote.from_note_string(args.note)
    pool_id = f"tornado-cash-{note.chain_id}-{note.currency.lower()}-{note.amount}"
    print(f"Fetching inclusion proof from {pool_id} via Saga CDN...")

    vault = TornadoVault(pool_id)
    inputs = build_withdrawal_inputs(
        vault=vault,
        note=note,
        recipient=args.recipient,
        relayer=args.relayer or "0x0000000000000000000000000000000000000000",
        fee=args.fee,
        refund=args.refund,
    )

    inputs_json = inputs.to_json()
    if args.output:
        with open(args.output, "w") as f:
            f.write(inputs_json)
        print(f"\nGroth16 Circuit Inputs saved to {args.output}!")
    else:
        print("\nGroth16 Circuit Inputs (JSON for snarkjs):")
        print(inputs_json)
    return 0


def cmd_tornado_withdraw_calldata(args: argparse.Namespace) -> int:
    # Read proof bytes
    if args.proof.endswith(".json"):
        with open(args.proof) as f:
            proof_data = json.load(f)
        proof_bytes = solidity_proof_from_snarkjs(proof_data)
    else:
        clean_hex = args.proof[2:] if args.proof.startswith("0x") else args.proof
        proof_bytes = bytes.fromhex(clean_hex)

    pool = get_pool(args.pool)
    call = build_withdraw_transaction(
        pool=pool,
        proof_bytes=proof_bytes,
        root=args.root,
        nullifier_hash=args.nullifier_hash,
        recipient=args.recipient,
        relayer=args.relayer or "0x0000000000000000000000000000000000000000",
        fee=args.fee,
        refund=args.refund,
    )

    print("Withdrawal Transaction Call:\n")
    print(f"  To:       {call.to}")
    print(f"  Calldata: {call.data}")
    print(f"\n  CLI Command (Cast):")
    print(f"    cast send {call.to} {call.data} --private-key <YOUR_KEY>")
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


def cmd_privacy_pools_pools(args: argparse.Namespace) -> int:
    print(f"{'POOL ID':<25} {'ASSET':<8} {'CONTRACT ADDRESS':<44} {'DECIMALS'}")
    print("-" * 88)
    for p_id, p in sorted(ALL_PRIVACY_POOLS.items()):
        print(f"{p_id:<25} {p.asset:<8} {p.contract_address:<44} {p.decimals}")
    return 0


def cmd_privacy_pools_new_note(args: argparse.Namespace) -> int:
    value_wei = int(float(args.amount) * 10**18)
    note = PrivacyPoolNote.create(value=value_wei, label=args.label)
    print("New Privacy Pools Note Generated:")
    print(f"  Commitment:     {note.commitment_hex}")
    print(f"  Nullifier Hash: {note.nullifier_hash_hex}")
    print(f"  Value:          {args.amount} ETH ({value_wei} wei)")
    print(f"  Label:          {note.label}")
    return 0


def cmd_privacy_pools_check_note(args: argparse.Namespace) -> int:
    vault = PrivacyPoolsVault(args.pool)
    print(f"Scanning Privacy Pool {args.pool} via Saga CDN...")

    def progress(filename: str, current: int, total: int) -> None:
        sys.stdout.write(f"  [{current}/{total}] Fetching and scanning {filename}...\n")
        sys.stdout.flush()

    comm = int(args.commitment, 16) if args.commitment.startswith("0x") else int(args.commitment)
    vault.sync(on_chunk=progress)

    is_mined = comm in vault._commitments_set
    is_spent = comm in vault.spent_nullifiers

    print("\nPool Statistics:")
    print(f"  Total Historical Deposits:    {len(vault.commitments)}")
    print(f"  Total Historical Withdrawals: {len(vault.spent_nullifiers)}")

    print("\nCommitment Status:")
    print(f"  Commitment:     {hex(comm)}")
    print(f"  Mined on-chain: {'YES ✓' if is_mined else 'NO ✗'}")
    if is_mined:
        idx = vault.commitments.index(comm)
        print(f"  Leaf Index:     {idx}")
        amt = vault.commitments_to_amounts.get(comm)
        if amt is not None:
            print(f"  Deposit Amount: {amt / 10**18} ETH ({amt} wei)")
    print(f"  Spent:          {'YES ✗' if is_spent else 'NO ✓'}")
    return 0


def cmd_stealth_meta_address(args: argparse.Namespace) -> int:
    from kohaku.stealth import derive_stealth_keypair

    pair = derive_stealth_keypair(args.mnemonic, chain_id=args.chain_id)
    print("Derived ERC-5564 Stealth Meta-Address:")
    print(f"  URI:                  {pair.stealth_meta_address_uri}")
    print(f"  Stealth Meta Address: {pair.stealth_meta_address}")
    print(f"  Spending Public Key:  {pair.spending_public_key}")
    print(f"  Viewing Public Key:   {pair.viewing_public_key}")
    return 0


def cmd_stealth_generate_address(args: argparse.Namespace) -> int:
    from kohaku.stealth import generate_stealth_address

    result = generate_stealth_address(args.meta_address)
    print("Generated One-Time Stealth Address:")
    print(f"  Stealth Address:      {result['stealth_address']}")
    print(f"  Ephemeral Public Key: {result['ephemeral_public_key']}")
    print(f"  View Tag:             {result['view_tag']}")
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

    w_inputs = tornado_sub.add_parser("withdraw-inputs", help="Generate Groth16 circuit inputs for note withdrawal")
    w_inputs.add_argument("note", help="Tornado note URI")
    w_inputs.add_argument("--recipient", required=True, help="Recipient address for withdrawn funds")
    w_inputs.add_argument("--relayer", default="0x0000000000000000000000000000000000000000", help="Relayer address")
    w_inputs.add_argument("--fee", type=int, default=0, help="Relayer fee in wei")
    w_inputs.add_argument("--refund", type=int, default=0, help="Relayer refund in wei")
    w_inputs.add_argument("--output", help="Save inputs to JSON file path")
    w_inputs.set_defaults(func=lambda client, args: cmd_tornado_withdraw_inputs(args))

    w_calldata = tornado_sub.add_parser("withdraw-calldata", help="Generate withdraw transaction calldata")
    w_calldata.add_argument("--pool", required=True, help="Pool ID (e.g. tornado-cash-1-eth-0.1)")
    w_calldata.add_argument("--proof", required=True, help="256-byte hex proof or path to snarkjs proof.json")
    w_calldata.add_argument("--root", required=True, help="Merkle root hex or decimal")
    w_calldata.add_argument("--nullifier-hash", required=True, help="Nullifier hash hex or decimal")
    w_calldata.add_argument("--recipient", required=True, help="Recipient address")
    w_calldata.add_argument("--relayer", default="0x0000000000000000000000000000000000000000", help="Relayer address")
    w_calldata.add_argument("--fee", type=int, default=0, help="Relayer fee in wei")
    w_calldata.add_argument("--refund", type=int, default=0, help="Relayer refund in wei")
    w_calldata.set_defaults(func=lambda client, args: cmd_tornado_withdraw_calldata(args))

    scan_p = tornado_sub.add_parser("scan-wallet", help="Recover all notes for a mnemonic seed phrase")
    scan_p.add_argument("--mnemonic", help="BIP-39 mnemonic seed phrase (12 or 24 words)")
    scan_p.add_argument("--private-key", help="Raw hex private key")
    scan_p.add_argument("--profile", type=int, default=0, help="Profile derivation index (default: 0)")
    scan_p.set_defaults(func=lambda client, args: cmd_tornado_scan_wallet(args))

    # privacy-pools
    pp_parser = subparsers.add_parser("privacy-pools", help="Privacy Pools commands")
    pp_sub = pp_parser.add_subparsers(dest="subcommand", required=True)

    pp_pools = pp_sub.add_parser("pools", help="List known 0xBow Privacy Pools")
    pp_pools.set_defaults(func=lambda client, args: cmd_privacy_pools_pools(args))

    pp_new = pp_sub.add_parser("new-note", help="Generate a new Privacy Pools note")
    pp_new.add_argument("--amount", default="1.0", help="Amount in ETH (arbitrary decimal amount)")
    pp_new.add_argument("--label", type=int, default=0, help="Association label (default: 0)")
    pp_new.set_defaults(func=lambda client, args: cmd_privacy_pools_new_note(args))

    pp_check = pp_sub.add_parser("check-note", help="Check note / commitment status in a Privacy Pool")
    pp_check.add_argument("commitment", help="Commitment hex string (e.g. 0x...)")
    pp_check.add_argument("--pool", default="privacy-pools-1-eth", help="Pool ID (default: privacy-pools-1-eth)")
    pp_check.set_defaults(func=lambda client, args: cmd_privacy_pools_check_note(args))

    # stealth
    stealth_parser = subparsers.add_parser("stealth", help="ERC-5564 Stealth Address commands")
    stealth_sub = stealth_parser.add_subparsers(dest="subcommand", required=True)

    meta_p = stealth_sub.add_parser("meta-address", help="Derive ERC-5564 stealth meta-address URI from seed phrase")
    meta_p.add_argument("--mnemonic", required=True, help="BIP-39 mnemonic seed phrase (12 or 24 words)")
    meta_p.add_argument("--chain-id", type=int, default=1, help="Network chain ID (default: 1 for eth, 11155111 for sep)")
    meta_p.set_defaults(func=lambda client, args: cmd_stealth_meta_address(args))

    gen_p = stealth_sub.add_parser("generate-address", help="Generate one-time stealth address for a recipient meta-address")
    gen_p.add_argument("meta_address", help="Stealth meta-address URI (st:<chain>:0x...) or raw 66-byte hex")
    gen_p.set_defaults(func=lambda client, args: cmd_stealth_generate_address(args))

    args = parser.parse_args()
    client = SagaClient(base_url=args.url)

    try:
        sys.exit(args.func(client, args))
    except Exception as e:
        sys.stderr.write(f"Error: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
