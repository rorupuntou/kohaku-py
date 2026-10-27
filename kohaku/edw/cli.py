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

from kohaku.edw.network import NetworkConfigManager
from kohaku.edw.p2p import P2PBroadcaster
from kohaku.edw.storage.cipher import InvalidPasswordError
from kohaku.edw.storage.database import EncryptedDatabase
from kohaku.edw.storage.keyring import KeyringManager
from kohaku.edw.tickets import TicketInvoice, TicketManager, TicketState
from kohaku.edw.tx_builder import TransactionBuilder
from kohaku.tornado.pools import (
    MAINNET_POOLS,
    format_amount,
    get_pool,
    parse_amount,
    parse_eth,
    resolve_asset,
    withdrawal_notes,
)


def get_default_data_dir() -> Path:
    env_dir = os.environ.get("EDW_DATA_DIR")
    if env_dir:
        return Path(env_dir)
    return Path.home() / ".edw"


def _resolve_password(args: argparse.Namespace) -> Optional[str]:
    if getattr(args, "password", None):
        return args.password
    pw_file = getattr(args, "password_file", None)
    if pw_file and Path(pw_file).exists():
        return Path(pw_file).read_text(encoding="utf-8").strip()
    return os.environ.get("EDW_PASSWORD")


def open_or_init_database(
    data_dir: Path,
    chain_id: int,
    password: Optional[str] = None,
    password_file: Optional[Path] = None,
) -> EncryptedDatabase:
    if not password and password_file and Path(password_file).exists():
        password = Path(password_file).read_text(encoding="utf-8").strip()
    if not password:
        password = os.environ.get("EDW_PASSWORD")

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


def _resolve_private_key(
    args: argparse.Namespace, db: Optional[EncryptedDatabase] = None
) -> Optional[str]:
    """Resolves signing private key securely via `getpass`, unlocked Keyring profile, or CLI arg (with `/proc` OPSEC warning)."""
    raw_key = getattr(args, "private_key", None)
    if getattr(args, "prompt_key", False) or raw_key == "-":
        import getpass

        return getpass.getpass("Enter signing private key (hidden): ").strip()
    if getattr(args, "from_profile", False) and db is not None:
        km = KeyringManager(db)
        profiles = km.list_profiles()
        if not profiles:
            raise ValueError("No profiles configured in datastore for --from-profile")
        p = profiles[0]
        phrase = km.get_mnemonic(p.mnemonic_index)
        Account.enable_unaudited_hdwallet_features()
        acct = Account.from_mnemonic(
            phrase, account_path=f"m/44'/60'/{p.profile_index}'/0/0"
        )
        return acct.key.hex()
    if raw_key:
        if "pytest" not in sys.modules:
            print(
                "[OPSEC NOTICE] Passing --private-key via CLI argv exposes it in /proc/<pid>/cmdline. "
                "Prefer `--prompt-key` or `--from-profile`.",
                file=sys.stderr,
            )
        return raw_key
    return None


def cmd_invoice_pay(args: argparse.Namespace) -> int:
    prep = TicketManager.prepare_invoice_deposit(args.invoice)
    print("Invoice Payment Prepared:")
    print(f"  To Contract:  {prep['to']}")
    print(f"  Amount:       {prep['value_eth']} ETH ({prep['value_wei']} wei)")
    print(f"  Calldata:     {prep['data'][:42]}...")

    priv_key = _resolve_private_key(args)
    if not priv_key:
        print("\n[!] To broadcast directly, pass --prompt-key (recommended) or --private-key <hex>. Otherwise copy the calldata above.")
        return 0

    broadcaster = P2PBroadcaster(tor_proxy=args.tor_proxy)
    signed = TransactionBuilder.build_deposit_tx(
        commitment_hex=prep["commitment"],
        pool_id=f"tornado-cash-{prep['chain_id']}-eth-{prep['value_eth']}",
        nonce=args.nonce or 0,
        private_key=priv_key,
    )
    print(f"\nBroadcasting raw transaction (Hash: {signed.tx_hash})...")
    res = broadcaster.broadcast_raw_tx(signed.raw_hex)
    print(f"✓ Success! Accepted by peer: {res.peer}")
    return 0


def cmd_shield(args: argparse.Namespace) -> int:
    password = _resolve_password(args)
    db = open_or_init_database(args.data_dir, args.chain_id, password=password)
    tm = TicketManager(db, profile_m=0, profile_x=0)

    token_str = getattr(args, "token", "ETH") or "ETH"
    asset_info = resolve_asset(token_str, args.chain_id)
    token_symbol = asset_info["symbol"]
    decimals = asset_info["decimals"]
    amount_raw = parse_amount(args.amount, decimals)

    tickets = tm.create_multi_shield_tickets(
        amount_wei=amount_raw,
        chain_id=args.chain_id,
        currency=token_symbol,
        label=args.label or "Multi-Shield",
    )

    print("════════════════════════════════════════════════════════════════════════════")
    print("                  EDW-PY MULTI-SHIELD DECOMPOSITION                         ")
    print("════════════════════════════════════════════════════════════════════════════")
    print(f"Total Amount:        {args.amount} {token_symbol} ({amount_raw} base units)")
    print(f"Decomposed Notes:    {len(tickets)} note(s) -> {[t.amount + ' ' + token_symbol for t in tickets]}")
    for idx, t in enumerate(tickets):
        print(f"  [{idx + 1}] {t.amount:<5} {token_symbol} | Pool: {t.pool_id} | Commitment: {t.commitment_hex[:20]}...")

    priv_key = _resolve_private_key(args, db=db)
    if not priv_key:
        print("\n[✓] Draft tickets encrypted and stored locally.")
        print("    Pass --prompt-key or --from-profile to sign the Dual Multi-Shield Bundle (EIP-7702 UserOp + EIP-1559).")
        print("════════════════════════════════════════════════════════════════════════════")
        return 0

    bundle = TransactionBuilder.build_multi_shield_bundle(
        tickets=tickets,
        private_key=priv_key,
        start_nonce=args.nonce,
    )
    print(f"\nSender Address:      {bundle.sender}")
    if bundle.user_operation is not None:
        print(f"ERC-4337 UserOpHash: {bundle.user_operation.user_op_hash}")
        print(f"EIP-7702 Delegate:   {bundle.user_operation.authorization.address if bundle.user_operation.authorization else 'already-delegated'}")
    print(f"EIP-1559 Fallback:   {len(bundle.eip1559_txs)} signed raw transaction(s) (nonces {args.nonce}..{args.nonce + len(bundle.eip1559_txs) - 1})")
    for tx in bundle.eip1559_txs:
        print(f"  • Nonce #{tx.nonce}: tx_hash={tx.tx_hash}")
    print("════════════════════════════════════════════════════════════════════════════")
    return 0


from kohaku.tornado.relayers import DEFAULT_ACTIVE_MAINNET_RELAYERS, RelayerRegistryVault


def cmd_relayers(args: argparse.Namespace) -> int:
    print("════════════════════════════════════════════════════════════════════════════")
    print("             TORNADO CASH ON-CHAIN RELAYER REGISTRY (MAINNET)               ")
    print("════════════════════════════════════════════════════════════════════════════")
    for idx, entry in enumerate(DEFAULT_ACTIVE_MAINNET_RELAYERS, start=1):
        ens = entry["ens"]
        url = entry["url"]
        addr = entry["address"]
        stake = entry["stake_torn"]
        status_str = "REGISTRY CACHED"
        if getattr(args, "probe", False):
            try:
                quote = RelayerRegistryVault.fetch_relayer_status(
                    url, socks5_proxy=args.tor_proxy, timeout=5.0
                )
                status_str = (
                    f"ONLINE | Fee: {quote.service_fee_percent:.3f}% | Gas: {quote.fast_gas_gwei:.2f} gwei"
                )
            except Exception as exc:
                status_str = f"OFFLINE ({exc})"
        print(f"  [{idx}] {ens:<24} | Stake: {stake:>9.2f} TORN | {url}")
        print(f"      RewardAccount: {addr} | {status_str}")
    print("════════════════════════════════════════════════════════════════════════════")
    return 0


def cmd_unshield(args: argparse.Namespace) -> int:
    import secrets

    password = _resolve_password(args)
    db = open_or_init_database(args.data_dir, args.chain_id, password=password)
    tm = TicketManager(db, profile_m=0, profile_x=0)

    token_str = getattr(args, "token", "ETH") or "ETH"
    asset_info = resolve_asset(token_str, args.chain_id)
    token_symbol = asset_info["symbol"]
    decimals = asset_info["decimals"]
    amount_raw = parse_amount(args.amount, decimals)

    held = tm.list_tickets(state=TicketState.MINED)
    if token_symbol != "ETH":
        # Withdrawal notes selects token notes and prepends the ETH sponsor note
        selected = withdrawal_notes(amount_raw, held, token_symbol, args.chain_id)
        mode_str = f"SPONSORED ERC-20 ({token_symbol})"
    elif args.exact:
        selected = tm.select_exact_tickets(amount_raw, currency="ETH", chain_id=args.chain_id)
        mode_str = "EXACT MATCH"
    else:
        selected = tm.select_cover_tickets(amount_raw, currency="ETH", chain_id=args.chain_id)
        mode_str = "COVER (LARGEST-FIRST)"

    quote = None
    if getattr(args, "relayer_url", None):
        quote = RelayerRegistryVault.fetch_relayer_status(
            args.relayer_url, socks5_proxy=args.tor_proxy
        )
    elif getattr(args, "auto_relayer", False):
        quote = RelayerRegistryVault.select_best_relayer(socks5_proxy=args.tor_proxy)

    jitter_max = getattr(args, "jitter", 0) or 0
    print("════════════════════════════════════════════════════════════════════════════")
    print(f"                  EDW-PY UNSHIELD COIN SELECTION ({mode_str})")
    print("════════════════════════════════════════════════════════════════════════════")
    print(f"Target Recipient:    {args.to}")
    print(f"Requested Amount:    {args.amount} {token_symbol} ({amount_raw} base units)")
    if token_symbol != "ETH":
        print(f"Selected Notes ({len(selected)}):")
        sponsor = selected[0]
        print(f"  • [SPONSOR] {sponsor.amount} ETH note pays gas through Tornado paymaster")
        for idx, t in enumerate(selected[1:], start=1):
            print(f"  • [TAIL #{idx}] {t.amount} {t.currency} note | Leaf: #{t.leaf_index} | Comm: {t.commitment_hex[:16]}...")
        if quote is not None:
            print(f"Selected Relayer:    {quote.base_url} (Reward: {quote.reward_account})")
    else:
        total_selected_wei = sum(t.amount_wei for t in selected)
        print(f"Selected Notes ({len(selected)}): {total_selected_wei / 1e18:.4f} ETH total")
        if quote is not None:
            print(f"Selected Relayer:    {quote.base_url} (Reward: {quote.reward_account})")
            print(f"Relayer Service Fee: {quote.service_fee_percent:.3f}%")
        if len(selected) > 1:
            print(
                "[OPSEC WARNING] Unshielding multiple notes to the same recipient in a burst allows "
                "amount/timing graph correlation. Use `--jitter <sec>` and fresh recipient addresses."
            )
        cum_delay = 0
        for idx, t in enumerate(selected):
            fee_info = ""
            if quote is not None:
                fee_wei = quote.compute_fee_wei(t.amount_wei)
                net_wei = max(0, t.amount_wei - fee_wei)
                fee_info = f" | Fee: {fee_wei / 1e18:.6f} ETH | Net: {net_wei / 1e18:.6f} ETH"
            jitter_info = ""
            if jitter_max > 0 and idx > 0:
                cum_delay += secrets.randbelow(jitter_max) + 1
                jitter_info = f" | Jitter Delay: +{cum_delay}s"
            print(
                f"  [{idx + 1}] {t.amount:<5} ETH | ID: {t.id} | Leaf: #{t.leaf_index} | NullifierHash: {t.nullifier_hash_hex[:18]}...{fee_info}{jitter_info}"
            )
    print("════════════════════════════════════════════════════════════════════════════")
    return 0


def cmd_railgun_address(args: argparse.Namespace) -> int:
    from kohaku.railgun import RailgunAddress

    if args.decode:
        dec = RailgunAddress.from_0zk(args.decode)
        print("════════════════════════════════════════════════════════════════════════════")
        print("                   RAILGUN 0zk BECH32M ADDRESS DECODED                      ")
        print("════════════════════════════════════════════════════════════════════════════")
        print(f"Address:             {args.decode}")
        print(f"Version:             {dec.version}")
        print(f"Master Public Key:   0x{dec.master_public_key:064x}")
        print(f"Viewing Public Key:  0x{dec.viewing_public_key.hex()}")
        print(f"Network Chain:       type={dec.chain_type}, chain_id={dec.chain_id}")
        print("════════════════════════════════════════════════════════════════════════════")
        return 0

    if not args.mpk or not args.vpk:
        raise ValueError("Provide either --decode <0zk1...> or both --mpk <hex> and --vpk <hex>")
    mpk_int = int(args.mpk, 16)
    vpk_clean = args.vpk[2:] if args.vpk.startswith("0x") else args.vpk
    vpk_bytes = bytes.fromhex(vpk_clean.zfill(64))
    rg = RailgunAddress(
        master_public_key=mpk_int,
        viewing_public_key=vpk_bytes,
        chain_type=0,
        chain_id=args.chain_id,
    )
    print(rg.to_0zk())
    return 0


def cmd_railgun_audit(args: argparse.Namespace) -> int:
    from collections import Counter
    from kohaku.railgun import KNOWN_MAINNET_TOKENS, RailgunVault
    from kohaku.sync.client import SagaClient

    client = SagaClient(local_dir=args.local_dir, verify_checksum=False)
    vault = RailgunVault(client=client)
    vault.sync_ops(include_hot=True)
    if not args.skip_events:
        vault.sync_events(include_hot=True)

    summary = vault.utxo_audit_summary()
    print("════════════════════════════════════════════════════════════════════════════")
    print("             RAILGUN L1 STATEFUL UTXO & MERKLE TREE AUDIT                   ")
    print("════════════════════════════════════════════════════════════════════════════")
    print(f"Contract Address:    {summary['contract']}")
    print(f"Total Operations:    {summary['operations_count']:,} ({summary['shielded_utxo_ops_count']:,} shielded, {summary['pure_unshield_ops_count']:,} pure unshields)")
    print(f"Merkle Trees (d=16): {summary['trees_count']} active trees -> {summary['tree_leaves_allocated']}")
    print(f"Total UTXO Leaves:   {summary['total_tree_leaves_allocated']:,}")
    print(f"Nullifiers Burned:   {summary['total_nullifiers_burned']:,}")
    print(f"Active Unspent Set:  {summary['net_active_utxos_estimate']:,} live UTXOs")
    print(f"Top NxM Topologies:  {summary['top_circuit_topologies']}")
    if not args.skip_events:
        print(f"Decoded L1 Shields:  {summary['shields_decoded']:,} deposit notes")
        print(f"Decoded L1 Unshield: {summary['unshields_decoded']:,} withdrawals")
        sh_vol: Counter[str] = Counter()
        un_vol: Counter[str] = Counter()
        for s in vault.shields:
            if s.token_address in KNOWN_MAINNET_TOKENS:
                sh_vol[s.token_symbol] += s.decimal_amount
        for u in vault.unshields:
            if u.token_address in KNOWN_MAINNET_TOKENS:
                un_vol[u.token_symbol] += u.decimal_amount
        print("\n--- MAJOR TOKEN FLOWS (SHIELD IN vs UNSHIELD OUT) ---")
        for sym in ("WETH", "USDT", "USDC", "DAI", "WBTC", "wstETH", "rETH", "RAIL"):
            if sh_vol[sym] > 0 or un_vol[sym] > 0:
                net_pool = max(0.0, sh_vol[sym] - un_vol[sym])
                print(
                    f"  • {sym:<7} | Shielded In: {sh_vol[sym]:>15,.2f} | Unshielded Out: {un_vol[sym]:>15,.2f} | Net Retained: {net_pool:>14,.2f}"
                )
    print("════════════════════════════════════════════════════════════════════════════")
    return 0


def cmd_network(args: argparse.Namespace) -> int:
    db = open_or_init_database(args.data_dir, args.chain_id, password=args.password)
    nm = NetworkConfigManager(db, chain_id=args.chain_id)

    action = args.net_action
    if action == "view":
        svc = nm.load()
    elif action == "rpc-add":
        svc = nm.add_rpc(args.url)
    elif action == "rpc-remove":
        svc = nm.remove_rpc(args.url)
    elif action == "bundler-add":
        svc = nm.add_bundler(args.url)
    elif action == "bundler-remove":
        svc = nm.remove_bundler(args.url)
    elif action == "indexer-set":
        svc = nm.set_indexer(args.url)
    elif action == "indexer-clear":
        svc = nm.set_indexer(None)
    else:
        raise ValueError(f"Unknown network action: {action}")

    print("════════════════════════════════════════════════════════════════════════════")
    print(f"               EDW-PY NETWORK SERVICES (CHAIN ID: {svc.chain_id})")
    print("════════════════════════════════════════════════════════════════════════════")
    print(f"Saga Indexer URL:    {svc.indexer_url or '(disabled — RPC log sync only)'}")
    print(f"RPC Endpoints ({len(svc.rpc_urls)}):")
    for u in svc.rpc_urls:
        print(f"  • {u}")
    print(f"ERC-4337 Bundlers ({len(svc.bundler_urls)}):")
    if svc.bundler_urls:
        for u in svc.bundler_urls:
            print(f"  • {u}")
    else:
        print("  • (none configured — using sovereign EIP-1559 fallback)")
    print("════════════════════════════════════════════════════════════════════════════")
    return 0


def cmd_conformance(args: argparse.Namespace) -> int:
    from kohaku.conformance.verifier import verify_all
    vdir = Path(args.dir) if getattr(args, "dir", None) else None
    results = verify_all(vdir)
    all_ok = True
    total_cases = 0

    print("=" * 65)
    print("  🦊⚡ KOHAKU CONFORMANCE SUITE (Cross-Client Spec Verification)")
    print("=" * 65)
    for suite_name, res in results.items():
        total_cases += res.cases_run
        status = "PASSED" if res.passed else "FAILED"
        bullet = "✓" if res.passed else "✗"
        print(f" {bullet} {suite_name:<28} [{res.cases_run} vectors] -> {status}")
        if not res.passed:
            all_ok = False
            for err in res.errors:
                print(f"     ! {err}")

    print("-" * 65)
    if all_ok:
        print(f"🎉 100% SPEC PARITY: All {total_cases} canonical vectors verified successfully.")
        return 0
    else:
        print("❌ CONFORMANCE FAILURES DETECTED.")
        return 1


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
    parser.add_argument("--password-file", type=Path, help="Path to file containing decryption password")
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
    inv_new.add_argument("--amount", default="0.1", help="Amount denomination (0.01, 0.03, 0.1, 0.3, 1, 3, 10, 30, 100)")
    inv_new.add_argument("--currency", default="ETH", help="Asset (default: ETH)")
    inv_new.add_argument("--label", default="", help="Optional local note label")
    inv_new.set_defaults(func=cmd_invoice_new)

    inv_pay = inv_sub.add_parser("pay", help="Pay / fund an anonymous invoice")
    inv_pay.add_argument("invoice", help="Invoice URI (edw-invoice:...) or JSON string")
    inv_pay.add_argument("--private-key", help="Funding private key to sign and broadcast (or '-' to prompt)")
    inv_pay.add_argument("--prompt-key", action="store_true", help="Prompt securely for signing key via getpass (OPSEC recommended)")
    inv_pay.add_argument("--nonce", type=int, help="Account nonce")
    inv_pay.set_defaults(func=cmd_invoice_pay)

    # shield (multi-note greedy packing + Dual UserOp / EIP-1559)
    sh_p = subparsers.add_parser("shield", help="Decompose and shield arbitrary ETH/ERC20 amounts into Tornado notes")
    sh_p.add_argument("--amount", required=True, help="Decimal token/ETH amount (e.g. 33.34 or 1100)")
    sh_p.add_argument("--token", default="ETH", help="Asset symbol: ETH (default), USDC, USDT, DAI, or WBTC")
    sh_p.add_argument("--label", default="Multi-Shield", help="Label prefix for created notes")
    sh_p.add_argument("--private-key", help="Optional private key to sign Dual UserOp + EIP-1559 bundle")
    sh_p.add_argument("--prompt-key", action="store_true", help="Prompt securely for signing key via getpass (OPSEC recommended)")
    sh_p.add_argument("--from-profile", action="store_true", help="Derive signing key directly from unlocked Keyring profile")
    sh_p.add_argument("--nonce", type=int, default=0, help="Starting account nonce (default: 0)")
    sh_p.set_defaults(func=cmd_shield)

    # unshield (exact / cover coin selection over held MINED notes)
    un_p = subparsers.add_parser("unshield", help="Select held MINED notes to unshield a target ETH/ERC20 amount")
    un_p.add_argument("--amount", required=True, help="Decimal token/ETH amount to unshield (e.g. 1.1 or 100)")
    un_p.add_argument("--token", default="ETH", help="Asset symbol: ETH (default), USDC, USDT, DAI, or WBTC")
    un_p.add_argument("--to", required=True, help="Recipient Ethereum address (0x...)")
    un_p.add_argument("--exact", action="store_true", help="Require exact denomination match instead of cover")
    un_p.add_argument(
        "--auto-relayer",
        action="store_true",
        help="Probe active on-chain relayers (/v1/status) and auto-select the healthiest lowest-fee relayer",
    )
    un_p.add_argument("--relayer-url", help="Explicit relayer base URL to query for /v1/status fee quote")
    un_p.add_argument(
        "--jitter",
        type=int,
        default=0,
        help="Max random delay (seconds) per additional note to mitigate multi-note timing correlation",
    )
    un_p.set_defaults(func=cmd_unshield)

    # relayers (on-chain Tornado Cash Relayer Registry & live /v1/status probing)
    rel_p = subparsers.add_parser("relayers", help="List and probe active on-chain Tornado Cash relayers")
    rel_p.add_argument("--probe", action="store_true", help="Query live /v1/status endpoints for fee & health quotes")
    rel_p.set_defaults(func=cmd_relayers)

    # railgun (0zk Bech32m addresses & stateful UTXO multi-tree auditor)
    rg_p = subparsers.add_parser("railgun", help="Railgun 0zk Bech32m utilities and UTXO chainstate auditor")
    rg_sub = rg_p.add_subparsers(dest="rg_action", required=True)

    rg_addr = rg_sub.add_parser("address", help="Encode or decode a Railgun 0zk1... Bech32m address")
    rg_addr.add_argument("--decode", help="Decode an existing 0zk1... address")
    rg_addr.add_argument("--mpk", help="Master Public Key (32-byte hex) to encode")
    rg_addr.add_argument("--vpk", help="Viewing Public Key (32-byte hex) to encode")
    rg_addr.set_defaults(func=cmd_railgun_address)

    rg_audit = rg_sub.add_parser("audit", help="Run stateful UTXO & Shield/Unshield audit on Railgun snapshots")
    rg_audit.add_argument("--local-dir", type=Path, help="Local directory with pre-downloaded Saga snapshots")
    rg_audit.add_argument("--skip-events", action="store_true", help="Audit only railgun-1-ops without smartwallet events")
    rg_audit.set_defaults(func=cmd_railgun_audit)


    # network (encrypted per-chain RPC, Bundler, and Saga Indexer registry)
    net_p = subparsers.add_parser("network", help="Manage encrypted per-chain RPC, Bundler, and Indexer services")
    net_sub = net_p.add_subparsers(dest="net_action", required=True)

    net_view = net_sub.add_parser("view", help="View configured network endpoints")
    net_view.set_defaults(func=cmd_network)

    for act, help_txt in (
        ("rpc-add", "Add an RPC endpoint URL"),
        ("rpc-remove", "Remove an RPC endpoint URL"),
        ("bundler-add", "Add an ERC-4337 Bundler URL"),
        ("bundler-remove", "Remove an ERC-4337 Bundler URL"),
        ("indexer-set", "Set the Saga CDN Indexer URL"),
    ):
        p_act = net_sub.add_parser(act, help=help_txt)
        p_act.add_argument("url", help="Service endpoint URL")
        p_act.set_defaults(func=cmd_network)

    net_clear = net_sub.add_parser("indexer-clear", help="Disable the Saga CDN Indexer for this chain")
    net_clear.set_defaults(func=cmd_network)

    # tui
    tui_p = subparsers.add_parser("tui", help="Launch interactive Terminal Desktop Wallet UI")
    tui_p.add_argument("--mnemonic", help="Optional BIP-39 mnemonic to pre-load")
    tui_p.set_defaults(func=cmd_tui)

    # conformance
    conf_p = subparsers.add_parser("conformance", help="Verify cross-client canonical test vectors")
    conf_p.add_argument("--dir", help="Optional path to custom conformance vectors directory")
    conf_p.set_defaults(func=cmd_conformance)

    args = parser.parse_args()
    try:
        sys.exit(args.func(args))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

