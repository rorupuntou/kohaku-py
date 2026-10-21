# kohaku-py 🦊⚡

Python privacy SDK for the **Ethereum** ecosystem, bringing **Tornado Cash**, **Privacy Pools**, and the **Saga Sync** protocol to Python.

Companion implementation to the Ethereum Foundation's **[ethereum/kohaku](https://github.com/ethereum/kohaku)** (TypeScript) and **[ethereum/kohaku-rs](https://github.com/ethereum/kohaku-rs)** (Rust).

---

## Architecture Overview

`kohaku-py` is built in modular layers:

- **`kohaku.sync`**: Verifiable, content-addressed log synchronizer client for the **Saga Sync** protocol (Fat Solutions). Reads gzip chunks and validates SHA-256 digests.
- **`kohaku.crypto`**:
  - `bn254`: Scalar field arithmetic on alt_bn128 ($p = 21888242871839275222246405745257275088548364400416034343698204186575808495617$).
  - `mimc`: Pure Python MiMC Sponge hash with 220 rounds, matching Tornado Cash on-chain contracts byte-for-byte.
  - `poseidon`: Poseidon hash matching Circomlib for Privacy Pools.
- **`kohaku.merkle`**: 20-level binary Merkle Tree supporting incremental inserts, zero-branch caching, and cryptographic proof generation.
- **`kohaku.tornado`**: Tornado Cash note derivation (`nullifier` & `secret`), commitment hashing, pool registry, and live on-chain status checking.
- **`kohaku.privacy_pools`**: Privacy Pools note derivation with arbitrary deposit amounts, labels, and Association Set verification (0xBow / Vitalik compliance model).
- **`kohaku.cli`**: Full-featured command-line interface (`kohaku`).

---

## Installation

```bash
git clone https://github.com/rorupuntou/kohaku-py
cd kohaku-py
pip install -e .
```

---

## Quickstart

### 1. Generate & Inspect Tornado Cash Notes

```python
from kohaku.tornado import TornadoNote, TornadoVault

# Generate a new random 0.1 ETH note
note = TornadoNote.create(currency="ETH", amount="0.1", chain_id=1)
print("Note URI:", note.to_note_string())
print("Deposit Commitment:", note.commitment_hex)
print("Withdrawal Nullifier Hash:", note.nullifier_hash_hex)

# Scan the pool via Saga CDN to check if it has been mined or spent
vault = TornadoVault("tornado-cash-1-eth-0.1")
status = vault.check_note(note)
print("Is Mined:", status["mined"])
print("Is Spent:", status["spent"])
```

### 2. Privacy Pools (Arbitrary Amounts & Association Sets)

```python
from kohaku.privacy_pools import PrivacyPoolNote, AssociationSet

# Create a Privacy Pools note for 0.75 ETH
amount_wei = int(0.75 * 10**18)
note = PrivacyPoolNote.create(value=amount_wei)
print("Commitment:", note.commitment_hex)

# Verify against an Association Set
clean_set = AssociationSet.from_deposits(asp_id="0xbow", clean_commitments=[note.commitment])
print("Is included in clean set:", clean_set.is_included(note.commitment))
```

### 3. Merkle Tree & Proof Generation

```python
from kohaku.crypto.mimc import mimc_hash2
from kohaku.merkle import MerkleTree

tree = MerkleTree(height=20, hash_fn=mimc_hash2)
idx = tree.insert(0x1234567890abcdef)
proof = tree.generate_proof(idx)

# Verify proof validity
assert proof.verify(hash_fn=mimc_hash2) is True
print("Proof verified! Merkle Root:", hex(proof.root))
```

---

## CLI Usage

```bash
# List available privacy protocols on Saga CDN
kohaku sync list

# List official Tornado Cash pools and contract addresses
kohaku tornado pools

# Generate a fresh Tornado Cash note
kohaku tornado new-note --amount 0.1 --currency ETH

# Check status of an existing note
kohaku tornado check-note tornado-eth-0.1-1-0x...

# Get ready-to-broadcast calldata and Cast command to fund a note on-chain
kohaku tornado deposit-calldata tornado-eth-0.1-1-0x...

# Recover all Tornado Cash notes from a BIP-39 mnemonic seed phrase
kohaku tornado scan-wallet --mnemonic "twelve words seed phrase..."

# Generate Groth16 circuit inputs (JSON for snarkjs) to withdraw a note
kohaku tornado withdraw-inputs tornado-eth-0.1-1-0x... --recipient 0xYourRecipientAddress --output inputs.json

# Encode withdrawal transaction calldata to submit to the Tornado Cash contract
kohaku tornado withdraw-calldata \
  --pool tornado-cash-1-eth-0.1 \
  --proof proof.json \
  --root 0x... \
  --nullifier-hash 0x... \
  --recipient 0xYourRecipientAddress

# List all official 0xBow Privacy Pools on Ethereum mainnet
kohaku privacy-pools pools

# Generate a Privacy Pools note with dynamic ETH value
kohaku privacy-pools new-note --amount 2.5

# Check on-chain deposit/withdrawal status of a Privacy Pools commitment via Saga CDN
kohaku privacy-pools check-note 0x... --pool privacy-pools-1-eth
```

---

## License

MIT
