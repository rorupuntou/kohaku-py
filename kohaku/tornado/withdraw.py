"""Tornado Cash withdrawal calldata and circuit witness builder."""

from __future__ import annotations

import eth_abi
from eth_hash.auto import keccak

from kohaku.tornado.circuit import CircuitInputs
from kohaku.tornado.note import TornadoNote
from kohaku.tornado.pools import TornadoPool, get_pool
from kohaku.tornado.tx import Call
from kohaku.tornado.vault import TornadoVault

WITHDRAW_SELECTOR = bytes.fromhex("21a0adb6")


def build_withdrawal_inputs(
    vault: TornadoVault,
    note: TornadoNote,
    recipient: str,
    relayer: str = "0x0000000000000000000000000000000000000000",
    fee: int = 0,
    refund: int = 0,
) -> CircuitInputs:
    """Builds the 20-level Merkle inclusion proof and returns CircuitInputs

    for Tornado Cash Groth16 zk-SNARK witness generation.
    """
    if not vault.synced:
        vault.sync()

    comm = note.commitment
    if comm not in vault._commitments_set:
        raise ValueError(f"Note commitment {note.commitment_hex} not found in pool {vault.pool.id}. Cannot withdraw unmined note.")

    if note.nullifier_hash in vault.spent_nullifiers:
        raise ValueError(f"Note nullifier {note.nullifier_hash_hex} has already been spent in pool {vault.pool.id}.")

    leaf_index = vault.commitments.index(comm)
    proof = vault.get_merkle_proof(leaf_index)

    recipient_int = int(recipient, 16)
    relayer_int = int(relayer, 16)

    return CircuitInputs(
        root=proof.root,
        nullifier_hash=note.nullifier_hash,
        recipient=recipient_int,
        relayer=relayer_int,
        fee=fee,
        refund=refund,
        nullifier=note.nullifier,
        secret=note.secret,
        path_elements=proof.path_elements,
        path_indices=proof.path_indices,
    )


def build_withdraw_transaction(
    pool: TornadoPool,
    proof_bytes: bytes,
    root: int | str,
    nullifier_hash: int | str,
    recipient: str,
    relayer: str = "0x0000000000000000000000000000000000000000",
    fee: int = 0,
    refund: int = 0,
) -> Call:
    """Encodes the `withdraw(bytes,bytes32,bytes32,address,address,uint256,uint256)` ABI call."""
    if isinstance(root, str):
        root_int = int(root, 16)
    else:
        root_int = root

    if isinstance(nullifier_hash, str):
        null_int = int(nullifier_hash, 16)
    else:
        null_int = nullifier_hash

    root_bytes = root_int.to_bytes(32, "big")
    null_bytes = null_int.to_bytes(32, "big")

    recipient_checksum = recipient.lower()
    relayer_checksum = relayer.lower()

    encoded_params = eth_abi.encode(
        ["bytes", "bytes32", "bytes32", "address", "address", "uint256", "uint256"],
        [proof_bytes, root_bytes, null_bytes, recipient_checksum, relayer_checksum, fee, refund],
    )

    calldata = "0x" + (WITHDRAW_SELECTOR + encoded_params).hex()

    return Call(
        to=pool.contract_address,
        data=calldata,
        value=0,
        description=f"Withdraw from {pool.amount} {pool.asset} Tornado Pool to {recipient}",
    )
