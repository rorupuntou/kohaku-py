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
