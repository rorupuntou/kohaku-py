"""Privacy Pools vault state synchronizer using Saga CDN events."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from kohaku.crypto.poseidon import poseidon_hash2
from kohaku.merkle.tree import LeanIMT, MerkleProof, MerkleTree
from kohaku.privacy_pools.note import PrivacyPoolNote
from kohaku.privacy_pools.pools import PrivacyPool, get_privacy_pool
from kohaku.sync.client import SAGA_V2_URL, SagaClient

DEPOSITED_TOPIC = "0xe3b53cd1a44fbf11535e145d80b8ef1ed6d57a73bf5daa7e939b6b01657d6549"
WITHDRAWN_TOPIC = "0x75e161b3e824b114fc1a33274bd7091918dd4e639cede50b78b15a4eea956a21"
RAGEQUIT_TOPIC = "0xd2b3e868ae101106371f2bd93abc8d5a4de488b9fe47ed122c23625aa7172f13"


class PrivacyPoolsVault:
    """Manages state synchronization, note tracking, and Merkle tree generation

    for 0xBow Privacy Pools using Saga CDN (defaults to `/v2` with Ed25519 signature verification).
    """

    def __init__(
        self,
        pool_id_or_pool: str | PrivacyPool = "privacy-pools-1-eth",
        client: SagaClient | None = None,
    ):
        if isinstance(pool_id_or_pool, str):
            self.pool = get_privacy_pool(pool_id_or_pool)
        else:
            self.pool = pool_id_or_pool

        self.client = client or SagaClient(base_url=SAGA_V2_URL, verify_signature=True)
        self.commitments: list[int] = []
        self._commitments_set: set[int] = set()
        self.commitments_to_amounts: dict[int, int] = {}
        self.commitment_tx_hashes: dict[int, str | None] = {}
        self.change_commitments: list[int] = []
        self.ragequit_amounts: dict[int, int] = {}
        self.spent_nullifiers: set[int] = set()
        self.synced = False
        self._tree: MerkleTree | None = None

    def _ingest_event(self, event: Any) -> None:
        topic = event.event_topic.lower()

        if topic == DEPOSITED_TOPIC:
            # Deposited(address indexed depositor, uint256 commitment, uint256 label, uint256 value, uint256 precommitmentHash)
            raw = bytes.fromhex(event.data[2:])
            if len(raw) >= 96:
                leaf = int.from_bytes(raw[0:32], "big")
                amount = int.from_bytes(raw[64:96], "big")
                if leaf not in self._commitments_set:
                    self.commitments.append(leaf)
                    self._commitments_set.add(leaf)
                    self._tree = None
                self.commitments_to_amounts[leaf] = amount
                self.commitment_tx_hashes[leaf] = event.transaction_hash

        elif topic == WITHDRAWN_TOPIC:
            # Withdrawn(address indexed processooor, uint256 value, uint256 spentNullifier, uint256 newCommitment)
            raw = bytes.fromhex(event.data[2:])
            if len(raw) >= 64:
                nullifier_hash = int.from_bytes(raw[32:64], "big")
                self.spent_nullifiers.add(nullifier_hash)
            if len(raw) >= 96:
                new_comm = int.from_bytes(raw[64:96], "big")
                if new_comm != 0:
                    self.change_commitments.append(new_comm)

        elif topic == RAGEQUIT_TOPIC:
            # Ragequit(address indexed ragequitter, uint256 commitment, uint256 label, uint256 value)
            raw = bytes.fromhex(event.data[2:])
            if len(raw) >= 32:
                leaf = int.from_bytes(raw[0:32], "big")
                self.spent_nullifiers.add(leaf)
                if len(raw) >= 96:
                    self.ragequit_amounts[leaf] = int.from_bytes(raw[64:96], "big")

    def sync(self, on_chunk: Callable[[str, int, int], None] | None = None) -> None:
        """Streams deposits and withdrawals from Saga CDN (or local_dir) into memory sets."""
        self.commitments.clear()
        self._commitments_set.clear()
        self.commitments_to_amounts.clear()
        self.commitment_tx_hashes.clear()
        self.change_commitments.clear()
        self.ragequit_amounts.clear()
        self.spent_nullifiers.clear()
        self._tree = None

        proto = self.client.get_protocol(self.pool.id)
        all_chunks = list(proto.chunks)
        if proto.hot_head:
            all_chunks.append(proto.hot_head)

        total_chunks = len(all_chunks)

        for idx, chunk in enumerate(all_chunks, 1):
            if on_chunk:
                on_chunk(chunk.file, idx, total_chunks)

            for event in self.client.stream_chunk_events(chunk):
                self._ingest_event(event)

        self.synced = True

    def sync_from_rpc(
        self,
        rpc_url: str,
        from_block: int | None = None,
        to_block: int | str = "latest",
        socks5_proxy: str | None = None,
    ) -> int:
        """Fetches and ingests Deposited/Withdrawn/Ragequit logs directly from an Ethereum RPC node
        via `eth_getLogs` (with optional Tor SOCKS5 proxy), bypassing Saga CDN.
        """
        start_block = self.pool.deployed_block if from_block is None else from_block
        events = SagaClient.fetch_rpc_logs(
            rpc_url=rpc_url,
            contract_address=self.pool.contract_address,
            topics=[[DEPOSITED_TOPIC, WITHDRAWN_TOPIC, RAGEQUIT_TOPIC]],
            from_block=start_block,
            to_block=to_block,
            socks5_proxy=socks5_proxy,
        )
        for ev in events:
            self._ingest_event(ev)
        self.synced = True
        return len(events)

    def check_note(
        self, note: PrivacyPoolNote, on_chunk: Callable[[str, int, int], None] | None = None
    ) -> dict[str, Any]:
        """Fast O(1) membership check for a note."""
        if not self.synced:
            self.sync(on_chunk=on_chunk)

        comm = note.commitment
        is_mined = comm in self._commitments_set
        leaf_index = self.commitments.index(comm) if is_mined else None
        is_spent = (note.nullifier_hash in self.spent_nullifiers) or (comm in self.spent_nullifiers)

        return {
            "commitment": note.commitment_hex,
            "nullifier_hash": note.nullifier_hash_hex,
            "mined": is_mined,
            "leaf_index": leaf_index,
            "deposit_tx_hash": self.commitment_tx_hashes.get(comm),
            "spent": is_spent,
            "spendable": is_mined and not is_spent,
            "total_deposits": len(self.commitments),
            "total_withdrawals": len(self.spent_nullifiers),
        }

    def tree(self) -> LeanIMT:
        """Builds or returns cached dynamic Poseidon LeanIMT (`@zk-kit/lean-imt.sol`)."""
        if not self.synced:
            self.sync()

        if self._tree is None:
            t = LeanIMT(hash_fn=poseidon_hash2)
            for leaf in self.commitments:
                t.insert(leaf)
            self._tree = t
        return self._tree

    def get_merkle_proof(self, leaf_index: int) -> MerkleProof:
        return self.tree().generate_proof(leaf_index)

    def verify_root_onchain(
        self,
        rpc_url: str,
        root: int | None = None,
        socks5_proxy: str | None = None,
    ) -> bool:
        """Verifies the local Merkle root directly against the Privacy Pool smart contract's
        `currentRoot()` (selector `0x9c4f8c08`) on-chain via `eth_call`.
        """
        from kohaku.edw.p2p import P2PBroadcaster

        target_root = self.tree().root() if root is None else root
        broadcaster = P2PBroadcaster(
            rpc_urls=[rpc_url], socks5_proxy=socks5_proxy
        )
        res = broadcaster.rpc_call(
            "eth_call",
            [{"to": self.pool.contract_address, "data": "0x9c4f8c08"}, "latest"],
        )
        if not isinstance(res, str) or not res.startswith("0x") or len(res) < 66:
            return False
        return int(res, 16) == target_root
