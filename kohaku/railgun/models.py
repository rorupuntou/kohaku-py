"""Railgun UTXO, operation, shield, and unshield data models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kohaku.crypto.poseidon import poseidon_hash

RAILGUN_SMART_WALLET_MAINNET = "0xfa7093cdd9ee6932b4eb2c9e1cde7ce00b1fa4b9"

SHIELD_TOPIC = "0x3a5b9dc26075a3801a6ddccf95fec485bb7500a91b44cec1add984c21ee6db3b"
LEGACY_SHIELD_TOPICS = (
    "0xf75eaa09da191ca634619d229eaa2a62f3f30b79ef6e9a0a2cb33ae1dc07d71c",
    "0xc3821e11e71307afd1d94a490660178ff37aefdd3c0514e5dd08937bd7024f34",
)
TRANSACT_TOPIC = "0x56a618cda1e34057b7f849a5792f6c8587a2dbe11c83d0254e72cb3daffda7d1"
LEGACY_TRANSACT_TOPIC = "0xc82d23263b236b692a8094d858e0831328f26cd9bcd5127d91c9299036cb9de9"
NULLIFIED_TOPIC = "0x781745c57906dc2f175fec80a9c691744c91c48a34a83672c41c2604774eb11f"
LEGACY_NULLIFIED_TOPIC = "0x78b6af109cf8ed292e957cdc2975e50bfd37995f5c38d35dc10e2ed0007cbd09"
UNSHIELD_TOPIC = "0xd93cf895c7d5b2cd7dc7a098b678b3089f37d91f48d9b83a0800a91cbdf05284"

RAILGUN_TREE_DEPTH = 16
RAILGUN_MAX_LEAVES_PER_TREE = 1 << RAILGUN_TREE_DEPTH  # 65,536
PURE_UNSHIELD_TREE_SENTINEL = 99999  # 0x1869f sentinel in railgun-1-ops when no shielded leaf is created
RAILGUN_ZERO_VALUE = int(
    "0x048b99c68d30f926bf6a4f3f72a76f9b6f0f0255d3c52a3f6bf149a20b272c8d", 16
)

KNOWN_MAINNET_TOKENS: dict[str, tuple[str, int]] = {
    "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": ("WETH", 18),
    "0xdac17f958d2ee523a2206206994597c13d831ec7": ("USDT", 6),
    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": ("USDC", 6),
    "0x6b175474e89094c44da98b954eedeac495271d0f": ("DAI", 18),
    "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599": ("WBTC", 8),
    "0x7f39c581f595b53c5cb19bd0b3f8da6c935e2ca0": ("wstETH", 18),
    "0xae78736cd615f374d3085123a210448e74fc6393": ("rETH", 18),
    "0xe76c6c83af64e4c60245d8c7de953df673a7a33d": ("RAIL", 18),
}


@dataclass
class RailgunUTXO:
    """Stateful Railgun UTXO output indexed by `(tree_number, leaf_index)`.

    When ingested from an L1 `Shield` event without pre-computed `railgun-1-ops` commitments,
    `commitment` is lazily computed and cached via `poseidon_hash([npk, token_id, amount_wei])`.
    """

    tree_number: int
    leaf_index: int
    commitment: int
    block_number: int
    source: str = "operation"
    token_address: str | None = None
    amount_wei: int | None = None
    npk: int | None = None
    token_type: int = 0
    token_sub_id: int = 0

    def __getattribute__(self, name: str) -> Any:
        val = object.__getattribute__(self, name)
        if name == "commitment" and val == 0:
            npk = object.__getattribute__(self, "npk")
            token_addr = object.__getattribute__(self, "token_address")
            amount_wei = object.__getattribute__(self, "amount_wei")
            if npk is not None and token_addr is not None and amount_wei is not None:
                token_type = object.__getattribute__(self, "token_type")
                token_sub_id = object.__getattribute__(self, "token_sub_id")
                note = RailgunShieldNote(
                    tree_number=object.__getattribute__(self, "tree_number"),
                    leaf_index=object.__getattribute__(self, "leaf_index"),
                    npk=npk,
                    token_type=token_type,
                    token_address=token_addr,
                    token_sub_id=token_sub_id,
                    value=amount_wei,
                    block_number=object.__getattribute__(self, "block_number"),
                )
                val = note.commitment
                object.__setattr__(self, "commitment", val)
        return val

    @property
    def outpoint(self) -> tuple[int, int]:
        return (self.tree_number, self.leaf_index)

    @property
    def commitment_hex(self) -> str:
        return f"0x{self.commitment:064x}"


@dataclass
class RailgunOperation:
    """Represents a pre-indexed `railgun-operation` UTXO state transition (`NxM` circuit)."""

    block_number: int
    tx_index: int
    op_index: int
    nullifiers: list[str]
    commitments: list[str]
    bound_params_hash: str
    utxo_tree_in: int
    utxo_tree_out: int
    utxo_batch_start_position_out: int

    @property
    def is_pure_unshield(self) -> bool:
        """Returns True if this operation is a 100% L1 Unshield (`utxoTreeOut == 0x1869f / 99999`)
        that inserts zero new shielded leaves into the Merkle tree.
        """
        return self.utxo_tree_out == PURE_UNSHIELD_TREE_SENTINEL

    @property
    def topology(self) -> str:
        """Returns the `(n_inputs)x(n_outputs)` Groth16 circuit shape (e.g. `'1x2'`, `'2x3'`)."""
        return f"{len(self.nullifiers)}x{len(self.commitments)}"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RailgunOperation:
        def _parse_int(v: Any) -> int:
            if isinstance(v, int):
                return v
            s = str(v)
            return int(s, 16) if s.startswith("0x") else int(s)

        return cls(
            block_number=_parse_int(data["blockNumber"]),
            tx_index=_parse_int(data.get("transactionIndex", 0)),
            op_index=_parse_int(data.get("opIndex", 0)),
            nullifiers=[str(n).lower() for n in data.get("nullifiers", [])],
            commitments=[str(c).lower() for c in data.get("commitments", [])],
            bound_params_hash=str(data.get("boundParamsHash", "0x0")).lower(),
            utxo_tree_in=_parse_int(data.get("utxoTreeIn", 0)),
            utxo_tree_out=_parse_int(data.get("utxoTreeOut", 0)),
            utxo_batch_start_position_out=_parse_int(data.get("utxoBatchStartPositionOut", 0)),
        )


@dataclass
class RailgunShieldNote:
    """Decoded `Shield` commitment preimage emitted when depositing L1 tokens into Railgun."""

    tree_number: int
    leaf_index: int
    npk: int
    token_type: int
    token_address: str
    token_sub_id: int
    value: int
    block_number: int

    @property
    def token_id(self) -> int:
        if self.token_type == 0:
            return int(self.token_address, 16)
        from eth_hash.auto import keccak

        packed = (
            self.token_type.to_bytes(32, "big")
            + int(self.token_address, 16).to_bytes(32, "big")
            + self.token_sub_id.to_bytes(32, "big")
        )
        snark_field = 21888242871839275222246405745257275088548364400416034343698204186575808495617
        return int.from_bytes(keccak(packed), "big") % snark_field

    @property
    def commitment(self) -> int:
        return poseidon_hash([self.npk, self.token_id, self.value])

    @property
    def commitment_hex(self) -> str:
        return f"0x{self.commitment:064x}"

    @property
    def token_symbol(self) -> str:
        info = KNOWN_MAINNET_TOKENS.get(self.token_address.lower())
        return info[0] if info else self.token_address[:10]

    @property
    def decimal_amount(self) -> float:
        info = KNOWN_MAINNET_TOKENS.get(self.token_address.lower())
        decimals = info[1] if info else 18
        return self.value / (10**decimals)



@dataclass
class RailgunUnshieldRecord:
    """Decoded `Unshield` event emitted when withdrawing Railgun notes back to an L1 `0x` address."""

    to_address: str
    token_type: int
    token_address: str
    token_sub_id: int
    amount: int
    fee: int
    block_number: int

    @property
    def gross_amount(self) -> int:
        return self.amount + self.fee

    @property
    def token_symbol(self) -> str:
        info = KNOWN_MAINNET_TOKENS.get(self.token_address.lower())
        return info[0] if info else self.token_address[:10]

    @property
    def decimal_amount(self) -> float:
        info = KNOWN_MAINNET_TOKENS.get(self.token_address.lower())
        decimals = info[1] if info else 18
        return self.amount / (10**decimals)
