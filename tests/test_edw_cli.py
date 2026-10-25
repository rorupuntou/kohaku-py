from pathlib import Path
import pytest

from kohaku.edw.cli import (
    cmd_balance,
    cmd_invoice_new,
    cmd_next_fresh_address,
    cmd_profile_import,
    cmd_profile_list,
    cmd_profile_new,
)


class DummyArgs:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def test_edw_cli_full_workflow(tmp_path: Path, capsys):
    data_dir = tmp_path / "edw_data"
    chain_id = 1
    password = "test-master-key"

    # 1. Profile New
    args_new = DummyArgs(
        data_dir=data_dir,
        chain_id=chain_id,
        password=password,
        name="alice-privacy",
    )
    ret = cmd_profile_new(args_new)
    assert ret == 0
    captured = capsys.readouterr().out
    assert "Created new profile 'alice-privacy'" in captured
    assert "Anchor Address" in captured

    # 2. Profile List
    args_list = DummyArgs(
        data_dir=data_dir,
        chain_id=chain_id,
        password=password,
    )
    ret = cmd_profile_list(args_list)
    assert ret == 0
    captured = capsys.readouterr().out
    assert "alice-privacy" in captured

    # 3. Next Fresh Address
    args_nfa_peek = DummyArgs(
        data_dir=data_dir,
        chain_id=chain_id,
        password=password,
        peek=True,
    )
    ret = cmd_next_fresh_address(args_nfa_peek)
    assert ret == 0
    addr_peek = capsys.readouterr().out.split()[0]
    assert addr_peek.startswith("0x")

    args_nfa = DummyArgs(
        data_dir=data_dir,
        chain_id=chain_id,
        password=password,
        peek=False,
    )
    ret = cmd_next_fresh_address(args_nfa)
    assert ret == 0
    addr_fresh = capsys.readouterr().out.split()[0]
    assert addr_fresh == addr_peek  # First one was peeked

    # 4. Generate Invoice (Anonymous Payment Request)
    args_inv = DummyArgs(
        data_dir=data_dir,
        chain_id=chain_id,
        password=password,
        amount="0.1",
        currency="ETH",
        label="Grant funding",
    )
    ret = cmd_invoice_new(args_inv)
    assert ret == 0
    captured = capsys.readouterr().out
    assert "edw-invoice:v1:1:ETH:0.1:" in captured

    # 5. Check Balance
    args_bal = DummyArgs(
        data_dir=data_dir,
        chain_id=chain_id,
        password=password,
        verbose=True,
    )
    ret = cmd_balance(args_bal)
    assert ret == 0
    captured = capsys.readouterr().out
    assert "EDW-PY SOVEREIGN WALLET HOLDINGS" in captured
    assert "Pending Invoices:    1 draft ticket(s)" in captured


def test_edw_cli_shield_unshield_and_network(tmp_path: Path, capsys):
    from eth_account import Account
    from kohaku.edw.cli import (
        cmd_network,
        cmd_shield,
        cmd_unshield,
        open_or_init_database,
    )
    from kohaku.edw.tickets import TicketManager

    data_dir = tmp_path / "edw_shield_data"
    chain_id = 1
    password = "test-master-key"
    payer = Account.create()

    # 1. Multi-Shield 1.31 ETH -> [1, 0.3, 0.01]
    args_sh = DummyArgs(
        data_dir=data_dir,
        chain_id=chain_id,
        password=password,
        amount="1.31",
        label="BatchShield",
        private_key=payer.key.hex(),
        nonce=3,
    )
    ret = cmd_shield(args_sh)
    assert ret == 0
    out = capsys.readouterr().out
    assert "Decomposed Notes:    3 note(s)" in out
    assert "ERC-4337 UserOpHash:" in out
    assert "Nonce #3:" in out
    assert "Nonce #5:" in out

    # Mark the 3 created tickets as MINED and run cmd_unshield
    db = open_or_init_database(data_dir, chain_id, password=password)
    tm = TicketManager(db, profile_m=0, profile_x=0)
    for idx, t in enumerate(tm.list_tickets()):
        tm.mark_mined(t.commitment_hex, leaf_index=idx, block_number=26200000 + idx)

    args_un = DummyArgs(
        data_dir=data_dir,
        chain_id=chain_id,
        password=password,
        amount="1.01",
        to="0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
        exact=True,
    )
    ret = cmd_unshield(args_un)
    assert ret == 0
    out = capsys.readouterr().out
    assert "EXACT MATCH" in out
    assert "Selected Notes (2): 1.0100 ETH total" in out

    # 3. Network service management
    args_net = DummyArgs(
        data_dir=data_dir,
        chain_id=chain_id,
        password=password,
        net_action="bundler-add",
        url="https://bundler.example.org/rpc",
    )
    ret = cmd_network(args_net)
    assert ret == 0
    out = capsys.readouterr().out
    assert "https://bundler.example.org/rpc" in out

