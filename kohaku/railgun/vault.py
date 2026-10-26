"""Railgun multi-tree UTXO vault and stateful auditor (`railgun-1-ops` & `railgun-1-smartwallet`).

Incorporates the stateful in-memory UTXO set and topology tracking patterns from
`bitcoin_satoshi2/historical_kernel_auditor.py`.
"""

from __future__ import annotations

from collections import Counter
import json
from typing import Any

from kohaku.railgun.models import (
    LEGACY_NULLIFIED_TOPIC,
    LEGACY_SHIELD_TOPICS,
    LEGACY_TRANSACT_TOPIC,
    NULLIFIED_TOPIC,
    RAILGUN_SMART_WALLET_MAINNET,
    SHIELD_TOPIC,
    TRANSACT_TOPIC,
    UNSHIELD_TOPIC,
    RailgunOperation,
    RailgunShieldNote,
    RailgunUnshieldRecord,
    RailgunUTXO,
)
from kohaku.sync.client import DEFAULT_SAGA_URL, SagaClient


class RailgunVault:
    """Reconstructs and audits Railgun's multi-tree UTXO set, `NxM` transaction topologies,
    and L1 `Shield`/`Unshield` flows from Saga CDN or local `.jsonl` snapshots.
    """

    def __init__(
        self,
        ops_protocol_id: str = "railgun-1-ops",
        events_protocol_id: str = "railgun-1-smartwallet",
        client: SagaClient | None = None,
    ):
        self.ops_protocol_id = ops_protocol_id
        self.events_protocol_id = events_protocol_id
        self.client = client or SagaClient(base_url=DEFAULT_SAGA_URL)
        self.utxos: dict[tuple[int, int], RailgunUTXO] = {}
        self.nullifiers: dict[str, int] = {}
        self.operations: list[RailgunOperation] = []
        self.pure_unshield_ops_count: int = 0
        self.shields: list[RailgunShieldNote] = []
        self.unshields: list[RailgunUnshieldRecord] = []
        self.topologies: Counter[str] = Counter()

    def ingest_operation(self, op_data: dict[str, Any] | RailgunOperation) -> RailgunOperation:
        """Ingests a `railgun-operation` entity (`railgun-1-ops`) into the multi-tree UTXO state."""
        op = op_data if isinstance(op_data, RailgunOperation) else RailgunOperation.from_dict(op_data)
        self.operations.append(op)
        self.topologies[op.topology] += 1

        for nf in op.nullifiers:
            self.nullifiers[nf.lower()] = op.utxo_tree_in

        if op.is_pure_unshield:
            self.pure_unshield_ops_count += 1
            return op

        for offset, comm_hex in enumerate(op.commitments):
            leaf_idx = op.utxo_batch_start_position_out + offset
            comm_int = int(comm_hex, 16) if comm_hex.startswith("0x") else int(comm_hex, 16)
            outpoint = (op.utxo_tree_out, leaf_idx)
            existing = self.utxos.get(outpoint)
            if existing is None:
                self.utxos[outpoint] = RailgunUTXO(
                    tree_number=op.utxo_tree_out,
                    leaf_index=leaf_idx,
                    commitment=comm_int,
                    block_number=op.block_number,
                    source="operation",
                )
        return op

    def ingest_event(self, event: Any) -> None:
        """Decodes and ingests a raw `RailgunSmartWallet` L1 event (`Shield`, `Transact`, `Nullified`, `Unshield`)
        across both Era 1 (v1/v2.0) and Era 2 (v2.1+) event schemas.
        """
        topic = event.event_topic.lower()
        raw = bytes.fromhex(event.data[2:]) if event.data.startswith("0x") else bytes.fromhex(event.data)

        if topic in (SHIELD_TOPIC, *LEGACY_SHIELD_TOPICS) and len(raw) >= 192:
            tree_num = int.from_bytes(raw[0:32], "big")
            start_pos = int.from_bytes(raw[32:64], "big")
            comm_offset = int.from_bytes(raw[64:96], "big")
            if len(raw) >= comm_offset + 32:
                count = int.from_bytes(raw[comm_offset : comm_offset + 32], "big")
                cursor = comm_offset + 32
                for idx in range(count):
                    if len(raw) < cursor + 160:
                        break
                    npk = int.from_bytes(raw[cursor : cursor + 32], "big")
                    token_type = int.from_bytes(raw[cursor + 32 : cursor + 64], "big")
                    token_addr = "0x" + raw[cursor + 64 : cursor + 96][-20:].hex().lower()
                    token_sub_id = int.from_bytes(raw[cursor + 96 : cursor + 128], "big")
                    value = int.from_bytes(raw[cursor + 128 : cursor + 160], "big")
                    cursor += 160

                    leaf_idx = start_pos + idx
                    note = RailgunShieldNote(
                        tree_number=tree_num,
                        leaf_index=leaf_idx,
                        npk=npk,
                        token_type=token_type,
                        token_address=token_addr,
                        token_sub_id=token_sub_id,
                        value=value,
                        block_number=event.block_number,
                    )
                    self.shields.append(note)
                    existing_utxo = self.utxos.get((tree_num, leaf_idx))
                    comm_val = (
                        existing_utxo.commitment
                        if existing_utxo is not None and existing_utxo.commitment != 0
                        else 0
                    )
                    self.utxos[(tree_num, leaf_idx)] = RailgunUTXO(
                        tree_number=tree_num,
                        leaf_index=leaf_idx,
                        commitment=comm_val,
                        block_number=event.block_number,
                        source="shield",
                        token_address=token_addr,
                        amount_wei=value,
                        npk=npk,
                        token_type=token_type,
                        token_sub_id=token_sub_id,
                    )

        elif topic in (TRANSACT_TOPIC, LEGACY_TRANSACT_TOPIC) and len(raw) >= 160:
            tree_num = int.from_bytes(raw[0:32], "big")
            start_pos = int.from_bytes(raw[32:64], "big")
            hash_offset = int.from_bytes(raw[64:96], "big")
            if len(raw) >= hash_offset + 32:
                count = int.from_bytes(raw[hash_offset : hash_offset + 32], "big")
                cursor = hash_offset + 32
                for idx in range(count):
                    if len(raw) < cursor + 32:
                        break
                    comm_int = int.from_bytes(raw[cursor : cursor + 32], "big")
                    cursor += 32
                    leaf_idx = start_pos + idx
                    outpoint = (tree_num, leaf_idx)
                    if outpoint not in self.utxos:
                        self.utxos[outpoint] = RailgunUTXO(
                            tree_number=tree_num,
                            leaf_index=leaf_idx,
                            commitment=comm_int,
                            block_number=event.block_number,
                            source="transact",
                        )

        elif topic in (NULLIFIED_TOPIC, LEGACY_NULLIFIED_TOPIC) and len(raw) >= 96:
            tree_num = int.from_bytes(raw[0:32], "big")
            arr_offset = int.from_bytes(raw[32:64], "big")
            if len(raw) >= arr_offset + 32:
                count = int.from_bytes(raw[arr_offset : arr_offset + 32], "big")
                cursor = arr_offset + 32
                for _ in range(count):
                    if len(raw) < cursor + 32:
                        break
                    nf_hex = "0x" + raw[cursor : cursor + 32].hex()
                    cursor += 32
                    self.nullifiers[nf_hex] = tree_num

        elif topic == UNSHIELD_TOPIC and len(raw) >= 192:
            to_addr = "0x" + raw[0:32][-20:].hex().lower()
            token_type = int.from_bytes(raw[32:64], "big")
            token_addr = "0x" + raw[64:96][-20:].hex().lower()
            token_sub_id = int.from_bytes(raw[96:128], "big")
            amount = int.from_bytes(raw[128:160], "big")
            fee = int.from_bytes(raw[160:192], "big")
            self.unshields.append(
                RailgunUnshieldRecord(
                    to_address=to_addr,
                    token_type=token_type,
                    token_address=token_addr,
                    token_sub_id=token_sub_id,
                    amount=amount,
                    fee=fee,
                    block_number=event.block_number,
                )
            )

    def sync_ops(self, include_hot: bool = True) -> None:
        """Streams all `railgun-1-ops` chunks and builds the UTXO operation graph."""
        from kohaku.sync.exceptions import ChunkDownloadError

        proto = self.client.get_protocol(self.ops_protocol_id)
        all_chunks = list(proto.chunks)
        if include_hot and proto.hot_head is not None:
            all_chunks.append(proto.hot_head)
        for chunk in all_chunks:
            if chunk.is_hot and not include_hot:
                continue
            try:
                raw_bytes = self.client.fetch_chunk_bytes(chunk)
            except ChunkDownloadError:
                if chunk.is_hot and self.client.local_dir is not None:
                    continue
                raise
            for line in raw_bytes.decode("utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                if data.get("entity") == "railgun-operation":
                    self.ingest_operation(data)

    def sync_events(self, include_hot: bool = True) -> None:
        """Streams `railgun-1-smartwallet` events and decodes `Shield`, `Transact`, `Nullified`, `Unshield`."""
        for event in self.client.stream_events(self.events_protocol_id, include_hot=include_hot):
            self.ingest_event(event)

    def utxo_audit_summary(self) -> dict[str, Any]:
        """Generates a Bitcoin-style stateful UTXO audit summary across all Railgun trees."""
        trees_summary: dict[int, int] = Counter()
        max_leaf_by_tree: dict[int, int] = {}
        for tree_num, leaf_idx in self.utxos:
            trees_summary[tree_num] += 1
            if tree_num not in max_leaf_by_tree or leaf_idx > max_leaf_by_tree[tree_num]:
                max_leaf_by_tree[tree_num] = leaf_idx

        total_indexed = len(self.utxos)
        total_allocated = sum(m + 1 for m in max_leaf_by_tree.values())
        total_nullified = len(self.nullifiers)
        effective_created = max(total_indexed, total_allocated)
        return {
            "contract": RAILGUN_SMART_WALLET_MAINNET,
            "operations_count": len(self.operations),
            "shielded_utxo_ops_count": len(self.operations) - self.pure_unshield_ops_count,
            "pure_unshield_ops_count": self.pure_unshield_ops_count,
            "trees_count": len(trees_summary),
            "utxos_by_tree": dict(sorted(trees_summary.items())),
            "tree_leaves_allocated": {t: m + 1 for t, m in sorted(max_leaf_by_tree.items())},
            "total_commitments_created": total_indexed,
            "total_tree_leaves_allocated": total_allocated,
            "total_nullifiers_burned": total_nullified,
            "net_active_utxos_estimate": max(0, effective_created - total_nullified),
            "top_circuit_topologies": dict(self.topologies.most_common(10)),
            "shields_decoded": len(self.shields),
            "unshields_decoded": len(self.unshields),
        }

