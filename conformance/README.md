# Cross-Client Conformance Suite & Spec Test Vectors (v1)

This directory contains the canonical cross-client test vectors and specification suite for the Ethereum Privacy and Sovereign Desktop Wallet stack (`desktop-wallet`, `kohaku-rs`, `kohaku-py`, and `kohaku-ts`).

Inspired by the Ethereum Foundation's **Execution Spec Tests** (`execution-spec-tests`) and **Consensus Spec Tests**, these language-agnostic JSON vectors ensure that multiple implementations across Rust, Python, and TypeScript maintain 100% bit-for-bit mathematical and serialization parity, eliminating regressions and guesswork during active protocol iterations.

---

## Architecture & Test Suites

The test suite is partitioned into six canonical domains under `conformance/v1/`:

```text
conformance/v1/
├── crypto_primitives.json       # MiMC-7, Poseidon, BabyJubJub Pedersen & LeanIMT
├── tornado_notes.json           # ETH & ERC-20 note strings, commitments, and nullifiers
├── invoices.json                # edw-invoice:v1:... anonymous payment request URIs
├── multishield_userop.json      # Greedy splitting & ERC-4337 v0.8 PackedUserOp EIP-712 hashing
├── railgun.json                 # 73-byte Bech32m 0zk1qy... address encoding and decoding
└── blinded_storage.json         # Argon2id KDF parameters & HKDF-SHA256 blinded disk filenames
```

---

### 1. `crypto_primitives.json`
Validates zero-knowledge hash functions and incremental tree structures:
- **MiMC-7 Sponge**:
  - 220 canonical round constants matching Tornado Cash on-chain contracts.
  - Verification of `TORNADO_ZERO_VALUE` ($21663839004416932...$) and Level 1 tree zero propagation.
- **Poseidon Hash**:
  - Circomlib-compatible $t=2$ and $t=3$ modular hash evaluations over BN254 scalar field $\mathbb{F}_p$.
- **BabyJubJub Pedersen Hash**:
  - Exact compressed generator point representation for Generator 0 (`1d1a2f1759e2...`).
  - Bit-packing and modular reduction of arbitrary preimages (e.g., `"Hello, world!"`).
- **LeanIMT (Lean Incremental Merkle Tree)**:
  - Dynamic leaf insertion with promotion of odd nodes without zero-hashing.
  - Sibling path generation and on-chain verification proof validity.

### 2. `tornado_notes.json`
Validates privacy note encoding and cryptographic derivation:
- Standard 31-byte secret and 31-byte nullifier test pairs.
- Exact commitment and nullifier hash derivations matching circomlib and on-chain verifiers.
- Note URI strings across **ETH**, **DAI**, **USDC**, and **WBTC** (`tornado-<currency>-<amount>-<chain_id>-0x...`).

### 3. `invoices.json`
Validates confidential payment request URIs:
- Format: `edw-invoice:v1:<chain_id>:<currency>:<amount>:<pool_contract>:<commitment>`
- Ensures public invoices can be generated offline and settled without exposing private note secrets or destination addresses.

### 4. `multishield_userop.json`
Validates account abstraction bundling and coin decomposition:
- **Greedy Amount Splitting**: Resolves token decimals (ETH/DAI = 18, USDC/USDT = 6, WBTC = 8) and partitions arbitrary values (e.g., `33.34 ETH` $\rightarrow$ `[30, 3, 0.3, 0.03, 0.01]`, `1100 USDC` $\rightarrow$ `[1000, 100]`).
- **ERC-4337 v0.8 `PackedUserOperation` EIP-712 Hashing**:
  - Canonical `u128` gas limit and fee packing: `pack(verificationGasLimit, callGasLimit)` and `pack(maxPriorityFeePerGas, maxFeePerGas)`.
  - Canonical EIP-712 Domain Separator with EntryPoint v0.8 (`0x4337084D9E255Ff0702461CF8895CE9E3b5Ff108`).
  - Bit-for-bit parity with `kohaku-rs` (`crates/userop-kit/src/signable_user_operation.rs`).

### 5. `railgun.json`
Validates Railgun shielded UTXO addresses:
- 73-byte payload Bech32m encoder/decoder with separator `0zk`.
- Verification of chain-specific addresses (`chain_type=0, chain_id=1`) and cross-chain all-network addresses (`chain_type=null`).

### 6. `blinded_storage.json`
Validates zero-metadata on-disk database storage:
- **Argon2id KDF**: 3 passes, 64 MiB memory cost, 1 parallelism lane, 32-byte hash length.
- **HKDF-SHA256 Blinded Paths**: Derivation of disk filenames (`<blinded_hash>.bin`) from logical keys (`vault:tornado/note:0`) to ensure disk-level zero leakage.
- **Record Encryption Keys**: Deterministic derivation of per-record ChaCha20-Poly1305 keys.

---

## Consuming in Other Clients (Rust / TypeScript)

Because all test vectors are plain JSON, sibling projects (`desktop-wallet` in Rust or `kohaku` in TypeScript) can consume them directly in their CI/test suites:

### Rust (`desktop-wallet` / `kohaku-rs`) Example
```rust
#[test]
fn test_conformance_tornado_notes() {
    let json_str = include_str!("../conformance/v1/tornado_notes.json");
    let suite: TornadoNotesSuite = serde_json::from_str(json_str).unwrap();
    
    let secret = hex::decode(&suite.fixed_secrets.secret_hex).unwrap();
    let nullifier = hex::decode(&suite.fixed_secrets.nullifier_hex).unwrap();
    
    for tv in suite.test_vectors {
        let note = TornadoNote::from_parts(&tv.currency, &tv.amount, tv.chain_id, &secret, &nullifier);
        assert_eq!(note.to_string(), tv.expected_note_string);
        assert_eq!(note.commitment_hex(), suite.fixed_secrets.expected_commitment_hex);
        assert_eq!(note.nullifier_hash_hex(), suite.fixed_secrets.expected_nullifier_hash_hex);
    }
}
```

### TypeScript (`ethereum/kohaku`) Example
```typescript
import notesSuite from "../conformance/v1/tornado_notes.json";

describe("Tornado Notes Conformance", () => {
  it("matches canonical commitment and nullifier hashes", () => {
    const { secret_hex, nullifier_hex, expected_commitment_hex } = notesSuite.fixed_secrets;
    for (const tv of notesSuite.test_vectors) {
      const note = new TornadoNote({
        currency: tv.currency,
        amount: tv.amount,
        chainId: tv.chain_id,
        secret: Buffer.from(secret_hex, "hex"),
        nullifier: Buffer.from(nullifier_hex, "hex"),
      });
      expect(note.commitmentHex).toBe(expected_commitment_hex);
      expect(note.toString()).toBe(tv.expected_note_string);
    }
  });
});
```

---

## Running the Conformance Suite in Python

### 1. Via `edw` CLI:
```bash
edw conformance
# Or test against a custom directory of vectors:
edw conformance --dir /path/to/conformance/v1
```

### 2. Via Python Module:
```bash
python -m kohaku.conformance
```

### 3. Via `pytest`:
```bash
pytest tests/test_conformance.py -v
```
