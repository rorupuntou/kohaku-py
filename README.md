# kohaku-py 🦊⚡

Python privacy SDK & sovereign desktop wallet engine for Ethereum, bringing **Tornado Cash**, **Privacy Pools (0xBow)**, **ERC-5564 Stealth Addresses**, and the **Saga Sync** protocol to pure Python.

Companion implementation to the Ethereum Foundation's **[ethereum/kohaku](https://github.com/ethereum/kohaku)** (TypeScript), **[ethereum/kohaku-rs](https://github.com/ethereum/kohaku-rs)** (Rust), and **[ethereum/desktop-wallet](https://github.com/ethereum/desktop-wallet)**.

---

## Terminal Desktop Wallet (TUI & CLI)

`kohaku-py` includes the full **`edw`** (Ethereum Desktop Wallet) sovereign engine in pure Python, complete with an interactive terminal UI and zero-leakage encrypted storage:

<p align="center">
  <img src="assets/tui_preview.svg" alt="Kohaku Desktop Wallet TUI" width="100%" />
</p>

Launch the interactive terminal wallet:
```bash
edw tui
# or
kohaku tui
```

---

## Key Features

- **Blinded Encrypted Datastore (`edw-core`)**:
  - Encrypted with **Argon2id** (64 MiB, 3 passes, 1 lane) and **ChaCha20-Poly1305** AEAD.
  - **Zero leakage on disk**: Record filenames are blinded with HKDF-SHA256 (`<blinded_hash>.bin`). An attacker inspecting disk sees zero accounts, zero notes, and zero history.
  - Fast password updates rewrites only `header.json` without re-encrypting records.
- **Privacy by Default & Fresh Address Rotation**:
  - Automatically derives and rotates unlinked virgin addresses along `m/44'/60'/x'/0/i` (`edw next-fresh-address`).
- **Extended ETH Denominations & Multi-Shield Bundling**:
  - Supports all 9 native ETH Tornado pools on Mainnet & Sepolia (`0.01`, `0.03`, `0.1`, `0.3`, `1`, `3`, `10`, `30`, `100` ETH) with greedy amount decomposition (`33.34 ETH` $\rightarrow$ `[30, 3, 0.3, 0.03, 0.01]`).
  - **Dual Multi-Shield Engine (`edw shield`)**: Bundles multi-note deposits into a single atomic ERC-4337 v0.8 `UserOperation` (`Simple7702Account.executeBatch` + signed EIP-7702 authorization) while simultaneously generating sequential EIP-1559 raw transactions for zero-bundler P2P/Tor fallback.
  - **Smart Coin Selection (`edw unshield`)**: Supports both `exact` denomination matching and largest-first `cover` note selection across held `MINED` notes.
- **Encrypted Per-Network Service Registry (`edw network`)**:
  - Manage per-chain RPC endpoints, ERC-4337 Bundlers, and Saga CDN Indexers inside the Argon2id + ChaCha20-Poly1305 blinded datastore.
- **Gasless Unshielding (Relayer Cut)**:
  - Unshield directly to fresh virgin addresses with **0 ETH prior gas**. Relayers or block builders execute the withdrawal on L1 and are reimbursed directly from the note.
- **Anonymous Invoices (`edw-invoice:v1:...`)**:
  - Generate untraceable payment requests exposing only public commitments. Third parties fund the ticket on Ethereum L1, and only you can withdraw it.
- **Sovereign Mempool & Tor / SOCKS5 Tunneling**:
  - Native RFC 1928 SOCKS5 client in pure Python. Route transactions and RPCs through Tor (`127.0.0.1:9050`) to eliminate IP tracking.
  - Multi-peer failover broadcaster (`P2PBroadcaster`).
- **ZK Cryptography & Protocols**:
  - Pure Python BN254 scalar field arithmetic modulo $p$.
  - 220-round canonical MiMC-7 Sponge matching Tornado Cash on-chain contracts.
  - Circomlib-compatible Poseidon for 0xBow Privacy Pools.
  - 20-level binary Merkle Tree with proof verification.
  - ERC-5564 Scheme 1 Stealth Meta-Addresses with secp256k1 ECDH.

---

## Installation

```bash
git clone https://github.com/rorupuntou/kohaku-py
cd kohaku-py

# With virtualenv
python -m venv .venv
source .venv/bin/activate  # or source .venv/bin/activate.fish
pip install -e .

# Or with Nix
nix develop
```

---

## EDW CLI Quickstart

```bash
# 1. Create a new encrypted wallet profile
edw profile new --name cypherpunk

# 2. View profiles
edw profile list

# 3. Get next unlinked virgin address
edw next-fresh-address --peek  # peek without advancing
edw next-fresh-address         # rotate and store cursor

# 4. Multi-Shield arbitrary ETH amount (greedy decomposition + Dual EIP-7702 UserOp / EIP-1559)
edw shield --amount 33.34 --label "Vault-Deposit"

# 5. Unshield with automatic coin selection (cover or --exact)
edw unshield --amount 3.31 --to 0xVirginRecipient... --exact

# 6. Configure encrypted per-chain RPCs, ERC-4337 Bundlers, and Saga Indexer
edw network view
edw network bundler-add https://bundler.example.org/rpc

# 7. Create an anonymous payment request (Invoice)
edw invoice new --amount 0.03 --label "Consulting"
# Returns: edw-invoice:v1:1:ETH:0.03:0x398971a7ae0fed4ae435f353ef00d3d4e4c18fd4:0x...

# 8. Check public and private spendable balances
edw balance --verbose

# 9. Launch the interactive terminal UI
edw tui
```

---

## Python SDK Quickstart

### 1. Offline EIP-1559 Transaction Signing & Gasless Withdraw

```python
from kohaku.edw.tx_builder import TransactionBuilder
from kohaku.edw.tickets import Ticket

# Create an offline draft note
ticket = Ticket.create_draft(currency="ETH", amount="1", chain_id=1)

# Build a gasless withdrawal payload
payload = TransactionBuilder.build_gasless_withdraw_payload(
    ticket=ticket,
    recipient_address="0xVirginAddress...",
    merkle_root="0xRoot...",
    proof_bytes=proof_bytes,
    relayer_address="0xRelayerNode...",
    relayer_fee_eth=0.01,
)
print("Calldata ready:", payload.calldata)
print("Net ETH received by recipient:", payload.net_recipient_eth)
```

### 2. Encrypted Blinded Datastore

```python
from kohaku.edw.storage.database import EncryptedDatabase

# Open encrypted store
db = EncryptedDatabase.open("~/.edw/1", password="my-password")

# Write confidential key material (filename on disk is completely blinded)
db.set("vault:tornado", "note:0", b"secret-payload")

# Read back
secret = db.get("vault:tornado", "note:0")
```

### 3. Generate & Inspect Tornado Cash Notes

```python
from kohaku.tornado import TornadoNote, TornadoVault

note = TornadoNote.create(currency="ETH", amount="0.1", chain_id=1)
print("Note URI:", note.to_note_string())
print("Deposit Commitment:", note.commitment_hex)
print("Withdrawal Nullifier Hash:", note.nullifier_hash_hex)
```

---

## Test Suite

```bash
pytest -v
```

```
tests/test_crypto.py::test_mimc_constants PASSED
tests/test_crypto.py::test_tornado_zero_value_propagation PASSED
tests/test_crypto.py::test_poseidon PASSED
tests/test_edw_cli.py::test_edw_cli_full_workflow PASSED
tests/test_edw_cli.py::test_edw_cli_shield_unshield_and_network PASSED
tests/test_edw_p2p.py::test_socks5_handshake_mock_server PASSED
tests/test_edw_p2p.py::test_p2p_broadcaster_with_failover PASSED
tests/test_edw_p2p.py::test_dispatch_gasless_withdrawal PASSED
tests/test_edw_storage.py::test_blinded_cipher_lifecycle PASSED
tests/test_edw_storage.py::test_encrypted_database_disk_zero_leakage PASSED
tests/test_edw_storage.py::test_keyring_manager_and_fresh_address_rotation PASSED
tests/test_edw_tickets.py::test_ticket_draft_and_invoice_generation PASSED
tests/test_edw_tickets.py::test_ticket_manager_encrypted_lifecycle PASSED
tests/test_edw_tickets.py::test_multi_shield_and_coin_selection PASSED
tests/test_edw_tx_builder.py::test_eip1559_transaction_signing_and_recovery PASSED
tests/test_edw_tx_builder.py::test_build_deposit_transaction PASSED
tests/test_edw_tx_builder.py::test_gasless_withdraw_payload_and_relayer_broadcast PASSED
tests/test_edw_tx_builder.py::test_dual_multi_shield_bundle PASSED
tests/test_merkle.py::test_merkle_tree_proofs PASSED
tests/test_privacy_pools.py::test_privacy_pool_note PASSED
tests/test_privacy_pools.py::test_association_set PASSED
tests/test_privacy_pools.py::test_privacy_pools_registry PASSED
tests/test_stealth.py::test_stealth_keypair_derivation PASSED
tests/test_stealth.py::test_erc5564_scheme1_lifecycle PASSED
tests/test_tornado.py::test_tornado_note_creation_and_parsing PASSED
tests/test_tornado.py::test_tornado_pools PASSED
tests/test_tornado.py::test_keychain_derivation PASSED
tests/test_tornado.py::test_deposit_transactions PASSED
tests/test_tornado.py::test_circuit_inputs_and_withdraw_transaction PASSED
tests/test_tui.py::test_tui_app_mount_and_headless PASSED

============================== 30 passed in 8.03s ==============================
```

---

## License

MIT License. Designed for privacy, sovereignty, and research.
