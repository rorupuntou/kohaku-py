import pytest
from kohaku.crypto.bn254 import P
from kohaku.tornado.circuit import CircuitInputs, solidity_proof_from_snarkjs
from kohaku.tornado.note import TornadoNote
from kohaku.tornado.pools import (
    MAINNET_POOLS,
    SEPOLIA_POOLS,
    decompose_eth_amount,
    get_pool,
    parse_eth,
)
from kohaku.tornado.withdraw import build_withdraw_transaction


def test_tornado_note_creation_and_parsing():
    note = TornadoNote.create(currency="ETH", amount="0.1", chain_id=1)

    assert len(note.nullifier) == 31
    assert len(note.secret) == 31
    assert note.commitment < P
    assert note.nullifier_hash < P

    note_str = note.to_note_string()
    assert note_str.startswith("tornado-eth-0.1-1-0x")

    # Roundtrip parsing
    parsed = TornadoNote.from_note_string(note_str)
    assert parsed.currency == "ETH"
    assert parsed.amount == "0.1"
    assert parsed.chain_id == 1
    assert parsed.nullifier == note.nullifier
    assert parsed.secret == note.secret
    assert parsed.commitment == note.commitment
    assert parsed.nullifier_hash == note.nullifier_hash


def test_tornado_pools():
    pool = get_pool("tornado-cash-1-eth-0.1")
    assert pool.asset == "ETH"
    assert pool.amount == "0.1"
    assert pool.contract_address == "0x12d66f87a04a9e220743712ce6d9bb1b5616b8fc"

    # Extended ETH pools (EDW PR #111)
    for amt in ("0.01", "0.03", "0.3", "3", "30"):
        assert f"tornado-cash-1-eth-{amt}" in MAINNET_POOLS
        assert f"tornado-cash-11155111-eth-{amt}" in SEPOLIA_POOLS

    # Greedy amount decomposition: 33.34 ETH -> [30, 3, 0.3, 0.03, 0.01]
    pools = decompose_eth_amount(parse_eth("33.34"), chain_id=1)
    assert [p.amount for p in pools] == ["30", "3", "0.3", "0.03", "0.01"]



def test_keychain_derivation():
    from kohaku.tornado.keychain import TornadoKeychain

    mnemonic = "test test test test test test test test test test test junk"
    kc = TornadoKeychain.from_mnemonic(mnemonic)
    assert kc.address == "0x04fD1301f5EaAA7236c273ea00d03c8c24Ab05D7"

    # Derive note for pool at nonce 0
    note = kc.derive_note("tornado-cash-1-eth-0.1", nonce=0)
    assert note.currency == "ETH"
    assert note.amount == "0.1"
    assert len(note.secret) == 31
    assert len(note.nullifier) == 31
    assert note.commitment < P


def test_deposit_transactions():
    from kohaku.tornado.tx import build_deposit_transactions

    note = TornadoNote.create(currency="ETH", amount="0.1", chain_id=1)
    calls = build_deposit_transactions(note)

    assert len(calls) == 1
    call = calls[0]
    assert call.to == "0x12d66f87a04a9e220743712ce6d9bb1b5616b8fc"
    assert call.value == 100_000_000_000_000_000
    assert call.data.startswith("0xb214faa5")


def test_circuit_inputs_and_withdraw_transaction():
    inputs = CircuitInputs(
        root=12345,
        nullifier_hash=67890,
        recipient=int("0x70997970C51812dc3A010C7d01b50e0d17dc79C8", 16),
        relayer=0,
        fee=0,
        refund=0,
        nullifier=111,
        secret=222,
        path_elements=[0] * 20,
        path_indices=[0] * 20,
    )
    d = inputs.to_dict()
    assert d["root"] == "12345"
    assert d["nullifierHash"] == "67890"
    assert len(d["pathElements"]) == 20
    assert len(d["pathIndices"]) == 20

    # Test dummy snarkjs proof conversion
    snarkjs_proof = {
        "pi_a": ["1", "2", "1"],
        "pi_b": [["3", "4"], ["5", "6"], ["1", "0"]],
        "pi_c": ["7", "8", "1"],
        "protocol": "groth16",
    }
    proof_bytes = solidity_proof_from_snarkjs(snarkjs_proof)
    assert len(proof_bytes) == 256

    pool = get_pool("tornado-cash-1-eth-0.1")
    tx = build_withdraw_transaction(
        pool=pool,
        proof_bytes=proof_bytes,
        root=12345,
        nullifier_hash=67890,
        recipient="0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
    )
    assert tx.to == pool.contract_address
    assert tx.value == 0
    assert tx.data.startswith("0x21a0adb6")

    # Verify end-to-end build_withdrawal_inputs with TornadoVault & LE integer conversion
    from kohaku.tornado.vault import TornadoVault
    from kohaku.tornado.withdraw import build_withdrawal_inputs

    note = TornadoNote(
        currency="ETH",
        amount="0.1",
        chain_id=1,
        nullifier=b"\x01" + b"\x00" * 30,
        secret=b"\x02" + b"\x00" * 30,
    )
    assert note.nullifier_int == 1
    assert note.secret_int == 2

    vault = TornadoVault("tornado-cash-1-eth-0.1")
    vault.commitments.append(note.commitment)
    vault._commitments_set.add(note.commitment)
    vault.synced = True

    w_inputs = build_withdrawal_inputs(
        vault=vault,
        note=note,
        recipient="0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
    )
    assert w_inputs.nullifier == 1
    assert w_inputs.secret == 2
    assert w_inputs.nullifier_hash == note.nullifier_hash
    assert len(w_inputs.path_elements) == 20



def test_relayer_registry_vault_and_ens_resolution(monkeypatch):
    from kohaku.edw.p2p import P2PBroadcaster
    from kohaku.sync.models import Event
    from kohaku.tornado.relayers import (
        RELAYER_REGISTERED_TOPIC,
        RELAYER_REGISTRY_ADDRESS,
        STAKE_BURNED_TOPIC,
        RelayerRegistryVault,
    )

    reg_vault = RelayerRegistryVault()
    # Real RelayerRegistered payload from block 0xd9737f (relayer-service.eth)
    reg_ev = Event(
        contract_address=RELAYER_REGISTRY_ADDRESS,
        event_topic=RELAYER_REGISTERED_TOPIC,
        topics=[RELAYER_REGISTERED_TOPIC],
        data=(
            "0xb60fb3b99e7206f890e586aa0b9fda9e859f4366eace809ee7de0edba56a2be9"
            "0000000000000000000000000000000000000000000000000000000000000080"
            "00000000000000000000000020bb3095a4852f4c97d7a188e9f7183c85acfc49"
            "00000000000000000000000000000000000000000000001b1ae4d6e2ef500000"
            "0000000000000000000000000000000000000000000000000000000000000013"
            "72656c617965722d736572766963652e65746800000000000000000000000000"
        ),
        block_number=0xD9737F,
        log_index=0xA8,
    )
    burn_ev = Event(
        contract_address=RELAYER_REGISTRY_ADDRESS,
        event_topic=STAKE_BURNED_TOPIC,
        topics=[STAKE_BURNED_TOPIC],
        data=(
            "0x00000000000000000000000020bb3095a4852f4c97d7a188e9f7183c85acfc49"
            "0000000000000000000000000000000000000000000000001ca9d2c10d11e12c"
        ),
        block_number=0xD9738F,
        log_index=0xC,
    )
    reg_vault.ingest_event(reg_ev)
    reg_vault.ingest_event(burn_ev)

    active = reg_vault.active_relayers(min_stake_torn=100.0)
    assert len(active) == 1
    rel = active[0]
    assert rel.ens_name == "relayer-service.eth"
    assert rel.mainnet_subdomain == "mainnet-tornado.relayer-service.eth"
    assert rel.relay_count == 1
    assert 497.0 < rel.staked_torn <= 500.0
    assert 2.0 < rel.burned_torn < 2.1

    def fake_rpc(self, method, params=None):
        data = params[0]["data"]
        if data.startswith("0x0178b8bf"):
            return "0x0000000000000000000000004976fb03c32e5b8cfe2b6ccb31c09ba78ebaba41"
        if data.startswith("0x59d1d43c"):
            return (
                "0x0000000000000000000000000000000000000000000000000000000000000020"
                "000000000000000000000000000000000000000000000000000000000000000d"
                "6574682e72656c746f722e737500000000000000000000000000000000000000"
            )
        raise AssertionError(data)

    monkeypatch.setattr(P2PBroadcaster, "rpc_call", fake_rpc)
    url = RelayerRegistryVault.resolve_ens_url("reltor.eth", "http://127.0.0.1:8545")
    assert url == "https://eth.reltor.su"


def test_relayer_status_quote_and_auto_selection(monkeypatch):
    import kohaku.edw.p2p as p2p_mod
    from kohaku.tornado.relayers import RelayerRegistryVault

    def fake_get_json(url, proxy=None, timeout=8.0):
        if "00relayer" in url:
            return {
                "rewardAccount": "0xda0b76cc92e94a6f972Ed29C104BBe8d73c2f753",
                "tornadoServiceFee": 0.36,
                "netId": 1,
                "gasPrices": {"fast": 1.5},
                "ethPrices": {"torn": "0.0022"},
                "health": {"status": "true", "error": ""},
            }
        return {
            "rewardAccount": "0x0A5B2bF3cCfB44C1D22F07Eed9553eCba752D4aD",
            "tornadoServiceFee": 0.385,
            "netId": 1,
            "gasPrices": {"fast": 2.0},
            "ethPrices": {"torn": "0.0022"},
            "health": {"status": "true", "error": ""},
        }

    monkeypatch.setattr(p2p_mod, "get_json_via_proxy", fake_get_json)
    best = RelayerRegistryVault.select_best_relayer()
    assert best.base_url == "https://eth.00relayer.xyz"
    assert best.service_fee_percent == 0.36
    assert best.reward_account.lower() == "0xda0b76cc92e94a6f972ed29c104bbe8d73c2f753"

    # 10 ETH note (10 * 10**18 wei) at 0.36% (36 bps) + 350,000 gas * 1.5 gwei
    fee_wei = best.compute_fee_wei(10 * 10**18, gas_limit=350_000)
    expected_service = (10 * 10**18 * 36) // 10_000
    expected_gas = int(1.5 * 1e9) * 350_000
    assert fee_wei == expected_service + expected_gas


def test_erc20_token_catalog_selection_units_and_denominations():
    """Matches `token_tests` in `edw_core::vault::tornadocash::amount`."""
    from kohaku.tornado.pools import (
        deposit_pools_for_asset,
        format_amount,
        parse_amount,
        resolve_asset,
    )

    cases = [
        ("USDC", 1, "1100", 6, 2),
        ("usdt", 1, "100", 6, 1),
        ("DAI", 1, "11100", 18, 3),
        ("WBTC", 1, "1.1", 8, 2),
        ("dai", 11_155_111, "100", 18, 1),
        ("ETH", 1, "1.1", 18, 2),
    ]

    for symbol, chain, amount_str, decimals, count in cases:
        asset = resolve_asset(symbol, chain)
        assert asset["decimals"] == decimals
        raw = parse_amount(amount_str, decimals)
        assert format_amount(raw, decimals) == amount_str
        pools = deposit_pools_for_asset(raw, chain, symbol)
        assert len(pools) == count
        assert all(p.asset.upper() == asset["symbol"] and p.chain_id == chain for p in pools)
        assert sum(p.amount_wei for p in pools) == raw

    # Unsupported or non-existent tokens
    for symbol in ["USDC", "USDT", "WBTC", "DOGE"]:
        with pytest.raises(ValueError):
            resolve_asset(symbol, 11_155_111)

    # Invalid amount formats
    for value in ["-1", "+1", "1e6", ".1", "1.", "1.0000001", "1..0"]:
        with pytest.raises(ValueError):
            parse_amount(value, 6)

    # 1 satoshi
    assert parse_amount("0.00000001", 8) == 1
    # Denomination mismatch
    with pytest.raises(ValueError):
        deposit_pools_for_asset(1, 1, "USDC")


def test_erc20_withdrawals_do_not_mix_assets_and_require_eth_sponsor():
    """Matches `withdrawals_do_not_mix_assets` in `edw_core::vault::tornadocash::amount`."""
    from dataclasses import dataclass
    from kohaku.tornado.pools import (
        get_pool,
        parse_amount,
        withdrawal_notes,
    )

    @dataclass
    class MockNote:
        pool_id: str
        currency: str
        amount_wei: int
        chain_id: int
        leaf_index: int | None
        spent: bool
        paymaster_address: str | None = None

    usdc_100_pool = get_pool("tornado-cash-1-usdc-100")
    usdt_100_pool = get_pool("tornado-cash-1-usdt-100")
    eth_01_pool = get_pool("tornado-cash-1-eth-0.1")

    valid_usdc = MockNote(
        pool_id=usdc_100_pool.id,
        currency="USDC",
        amount_wei=usdc_100_pool.amount_wei,
        chain_id=1,
        leaf_index=0,
        spent=False,
        paymaster_address=usdc_100_pool.paymaster_address,
    )
    valid_usdt = MockNote(
        pool_id=usdt_100_pool.id,
        currency="USDT",
        amount_wei=usdt_100_pool.amount_wei,
        chain_id=1,
        leaf_index=1,
        spent=False,
    )
    pending_usdc = MockNote(
        pool_id=usdc_100_pool.id,
        currency="USDC",
        amount_wei=usdc_100_pool.amount_wei,
        chain_id=1,
        leaf_index=None,  # pending
        spent=False,
    )
    spent_usdc = MockNote(
        pool_id=usdc_100_pool.id,
        currency="USDC",
        amount_wei=usdc_100_pool.amount_wei,
        chain_id=1,
        leaf_index=2,
        spent=True,
    )
    eth_sponsor = MockNote(
        pool_id=eth_01_pool.id,
        currency="ETH",
        amount_wei=eth_01_pool.amount_wei,
        chain_id=1,
        leaf_index=3,
        spent=False,
        paymaster_address=eth_01_pool.paymaster_address,
    )

    held = [valid_usdc, valid_usdt, pending_usdc, spent_usdc, eth_sponsor]
    amount = parse_amount("100", 6)

    # Must select ETH sponsor note at index 0 and USDC token note at index 1
    selected = withdrawal_notes(amount, held, "USDC", chain_id=1)
    assert len(selected) == 2
    assert selected[0] == eth_sponsor
    assert selected[1] == valid_usdc

    # Attempting to withdraw token without ETH sponsor fails
    with pytest.raises(ValueError, match="every ERC-20 withdrawal requires an additional mined shielded ETH note"):
        withdrawal_notes(amount, [valid_usdc], "USDC", chain_id=1)


