from kohaku.crypto.bn254 import P
from kohaku.privacy_pools.asp import AssociationSet
from kohaku.privacy_pools.note import PrivacyPoolNote
from kohaku.privacy_pools.pools import ALL_PRIVACY_POOLS, get_privacy_pool
from kohaku.privacy_pools.vault import DEPOSITED_TOPIC, PrivacyPoolsVault


def test_privacy_pool_note():
    note = PrivacyPoolNote.create(value=10**18, label=0)

    assert note.value == 10**18
    assert note.label == 0
    assert note.commitment < P
    assert note.nullifier_hash < P


def test_association_set():
    note1 = PrivacyPoolNote.create(value=10**18)
    note2 = PrivacyPoolNote.create(value=2 * 10**18)

    asp = AssociationSet.from_deposits("0xbow", [note1.commitment, note2.commitment])

    assert asp.is_included(note1.commitment) is True
    assert asp.is_included(note2.commitment) is True
    assert asp.is_included(0x12345) is False

    proof = asp.generate_proof(0)
    assert proof.leaf == note1.commitment


def test_privacy_pools_registry():
    from kohaku.privacy_pools.pools import PRIVACY_POOLS_ENTRYPOINT

    assert len(ALL_PRIVACY_POOLS) == 14
    assert PRIVACY_POOLS_ENTRYPOINT == "0x6818809eefce719e480a7526d76bd3e561526b46"

    for suffix in (
        "eth",
        "usds",
        "susds",
        "dai",
        "usdt",
        "usdc",
        "wsteth",
        "wbtc",
        "usde",
        "usd1",
        "frxusd",
        "woeth",
        "fxusd",
        "bold",
    ):
        assert f"privacy-pools-1-{suffix}" in ALL_PRIVACY_POOLS

    pool = get_privacy_pool("privacy-pools-1-eth")
    assert pool.asset == "ETH"
    assert pool.contract_address.lower() == "0xf241d57c6debae225c0f2e6ea1529373c9a9c9fb"
    assert pool.is_native is True

    bold_pool = get_privacy_pool("privacy-pools-1-bold")
    assert bold_pool.is_native is False
    assert bold_pool.asset == "BOLD"
    assert bold_pool.asset_address == "0x6440f144b7e50d6a8439336510312d2f54beb01d"
    assert bold_pool.deployed_block == 24435268


def test_saga_v2_event_and_ed25519_manifest_signature():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    from kohaku.sync.client import verify_manifest_ed25519
    from kohaku.sync.models import Event

    ev = Event.from_dict(
        {
            "contractAddress": "0xb4b5fd38fd4788071d7287e3cb52948e0d10b23e",
            "eventTopic": DEPOSITED_TOPIC,
            "topics": [DEPOSITED_TOPIC],
            "data": "0x" + "00" * 96,
            "blockNumber": "0x174f395",
            "logIndex": "0x384",
            "transactionHash": "0x2e2e4c402c695bdf1234567890abcdef1234567890abcdef1234567890abcdef",
        }
    )
    assert ev.block_number == 0x174F395
    assert ev.transaction_hash == "0x2e2e4c402c695bdf1234567890abcdef1234567890abcdef1234567890abcdef"
    assert ev.to_dict()["transactionHash"] == ev.transaction_hash

    priv = Ed25519PrivateKey.generate()
    pub_hex = "0x" + priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    payload = b'{"version":1,"availableProtocols":{}}'
    sig_hex = "0x" + priv.sign(payload).hex()

    assert verify_manifest_ed25519(payload, sig_hex, pubkey_hex=pub_hex) is True
    assert verify_manifest_ed25519(payload + b"tampered", sig_hex, pubkey_hex=pub_hex) is False


def test_local_dir_sync_and_onchain_root_verification(tmp_path, monkeypatch):
    import hashlib
    import json
    from kohaku.edw.p2p import P2PBroadcaster
    from kohaku.sync.client import (
        FASTLY_SAGA_V2_URL,
        GCS_ORIGIN_SAGA_V2_URL,
        SAGA_V2_URL,
        SagaClient,
    )

    note = PrivacyPoolNote.create(value=25 * 10**18, label=0x1234)
    dep_data = (
        "0x"
        + f"{note.commitment:064x}"
        + f"{note.label:064x}"
        + f"{note.value:064x}"
        + f"{0:064x}"
    )
    chunk_jsonl = (
        json.dumps(
            {
                "contractAddress": "0xb4b5fd38fd4788071d7287e3cb52948e0d10b23e",
                "eventTopic": DEPOSITED_TOPIC,
                "topics": [DEPOSITED_TOPIC],
                "data": dep_data,
                "blockNumber": "0x174f395",
                "logIndex": "0x1",
                "transactionHash": "0x" + "aa" * 32,
            }
        )
        + "\n"
    ).encode("utf-8")
    digest_hex = "0x" + hashlib.sha256(chunk_jsonl).hexdigest()
    chunk_file = "privacy-pools-1-bold-[0x174da44,0x190b543).hot.jsonl"
    (tmp_path / chunk_file).write_bytes(chunk_jsonl)

    manifest_dict = {
        "version": 1,
        "updatedAt": "2026-10-25T00:00:00Z",
        "availableProtocols": {
            "privacy-pools-1-bold": {
                "chainId": 1,
                "fromBlock": 0x174DA44,
                "toBlock": 0x190B543,
                "protocol": "privacy-pools",
                "protocolMetadata": {"asset": "BOLD"},
                "events": [],
                "chunks": [],
                "hotHead": {
                    "file": chunk_file + ".gz",
                    "fromBlock": 0x174DA44,
                    "toBlock": 0x190B543,
                    "size": len(chunk_jsonl),
                    "digest": {"alg": "sha256", "data": digest_hex},
                },
            }
        },
    }
    (tmp_path / "index.json").write_text(json.dumps(manifest_dict), encoding="utf-8")

    client = SagaClient(
        base_url=SAGA_V2_URL,
        verify_signature=False,
        local_dir=tmp_path,
    )
    assert client.fallback_urls == [FASTLY_SAGA_V2_URL, GCS_ORIGIN_SAGA_V2_URL]

    vault = PrivacyPoolsVault("privacy-pools-1-bold", client=client)
    status = vault.check_note(note)
    assert status["mined"] is True
    assert status["spendable"] is True
    assert status["deposit_tx_hash"] == "0x" + "aa" * 32

    local_root = vault.tree().root()

    def fake_rpc_call(self, method, params=None):
        if method == "eth_call":
            return f"0x{local_root:064x}"
        if method == "eth_getLogs":
            return [
                {
                    "address": "0xb4b5fd38fd4788071d7287e3cb52948e0d10b23e",
                    "topics": [DEPOSITED_TOPIC],
                    "data": dep_data,
                    "blockNumber": "0x174f395",
                    "logIndex": "0x1",
                    "transactionHash": "0x" + "bb" * 32,
                }
            ]
        raise AssertionError(f"Unexpected RPC method {method}")

    monkeypatch.setattr(P2PBroadcaster, "rpc_call", fake_rpc_call)

    assert vault.verify_root_onchain("http://127.0.0.1:8545") is True
    assert vault.verify_root_onchain("http://127.0.0.1:8545", root=local_root + 1) is False

    rpc_vault = PrivacyPoolsVault("privacy-pools-1-bold", client=client)
    count = rpc_vault.sync_from_rpc("http://127.0.0.1:8545", from_block=24435268)
    assert count == 1
    assert rpc_vault.check_note(note)["mined"] is True

