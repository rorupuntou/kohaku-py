"""Modal dialogs for Kohaku TUI wallet."""

from __future__ import annotations

import json

from eth_account import Account
from textual.app import ComposeResult
from textual.containers import Grid, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static

Account.enable_unaudited_hdwallet_features()

DEV_TEST_SEED = "test test test test test test test test test test test junk"


class SeedModal(ModalScreen[str]):
    """Modal dialog prompting the user to provide or generate a mnemonic seed phrase."""

    DEFAULT_CSS = """
    SeedModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }

    #seed-dialog {
        width: 75;
        height: auto;
        border: solid $accent;
        background: $surface;
        padding: 1 2;
    }

    #dialog-title {
        text-align: center;
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    .modal-desc {
        color: $text-muted;
        margin-bottom: 1;
    }

    #mnemonic-input {
        margin-bottom: 1;
    }

    #button-bar {
        align: right middle;
        height: auto;
    }

    Button {
        margin-left: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="seed-dialog"):
            yield Label("🦊 Unlock Kohaku Desktop Wallet", id="dialog-title")
            yield Static(
                "Enter your 12- or 24-word mnemonic seed phrase to derive your accounts, "
                "stealth meta-address, and private notes:",
                classes="modal-desc",
            )
            yield Input(
                placeholder="word1 word2 word3 ... word12",
                id="mnemonic-input",
                password=True,
            )
            with Horizontal(id="button-bar"):
                yield Button("Dev Test Seed", variant="warning", id="btn-dev-seed")
                yield Button("Generate New", variant="default", id="btn-generate")
                yield Button("Unlock", variant="primary", id="btn-unlock")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-dev-seed":
            self.dismiss(DEV_TEST_SEED)
        elif event.button.id == "btn-generate":
            acc, mnemonic = Account.create_with_mnemonic()
            self.dismiss(mnemonic)
        elif event.button.id == "btn-unlock":
            input_widget = self.query_one("#mnemonic-input", Input)
            val = input_widget.value.strip()
            if val:
                self.dismiss(val)


class NoteModal(ModalScreen[None]):
    """Modal displaying full details of a Tornado Cash or Privacy Pools note."""

    DEFAULT_CSS = """
    NoteModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }

    #note-dialog {
        width: 80;
        height: auto;
        border: solid $accent;
        background: $surface;
        padding: 1 2;
    }

    #note-title {
        text-align: center;
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    .note-row {
        margin-bottom: 1;
    }

    .row-label {
        color: $text-muted;
        text-style: bold;
    }

    .row-val {
        color: $text;
    }

    #note-btn-close {
        align: center middle;
        margin-top: 1;
    }
    """

    def __init__(self, title: str, details: dict[str, str]):
        super().__init__()
        self.dialog_title = title
        self.details = details

    def compose(self) -> ComposeResult:
        with Vertical(id="note-dialog"):
            yield Label(self.dialog_title, id="note-title")
            for k, v in self.details.items():
                with Vertical(classes="note-row"):
                    yield Label(f"{k}:", classes="row-label")
                    yield Static(v, classes="row-val")
            with Horizontal(id="note-btn-close"):
                yield Button("Close", variant="primary", id="btn-close-note")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)


class BroadcastModal(ModalScreen[None]):
    """Modal to broadcast / dispatch withdrawal transaction on-chain or via Relayer."""

    DEFAULT_CSS = """
    BroadcastModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }
    #broadcast-dialog {
        width: 85;
        height: auto;
        border: solid $warning;
        background: $surface;
        padding: 1 2;
    }
    #broadcast-title {
        text-align: center;
        text-style: bold;
        color: $warning;
        margin-bottom: 1;
    }
    .broadcast-warning {
        color: $error;
        text-style: bold;
        margin-bottom: 1;
    }
    .modal-label {
        color: $text-muted;
        text-style: bold;
        margin-top: 1;
    }
    #broadcast-status {
        background: $surface-darken-1;
        border: dashed $accent;
        padding: 1;
        margin-top: 1;
        margin-bottom: 1;
        height: auto;
    }
    #broadcast-btn-bar {
        align: right middle;
        margin-top: 1;
    }
    #broadcast-btn-bar Button {
        margin-left: 1;
    }
    """

    def __init__(self, contract_address: str, calldata: str, pool_id: str, is_relayer: bool = False):
        super().__init__()
        self.contract_address = contract_address
        self.calldata = calldata
        self.pool_id = pool_id
        self.is_relayer = is_relayer

    def compose(self) -> ComposeResult:
        with Vertical(id="broadcast-dialog"):
            yield Label("🚀 On-Chain Broadcast & Relayer Dispatch", id="broadcast-title")
            yield Static(
                "⚠️ OPSEC CAUTION: Broadcasting will submit this transaction to the public network. "
                "Ensure your IP is protected (Tor / VPN) and the recipient is unlinked.",
                classes="broadcast-warning",
            )

            if self.is_relayer:
                yield Label("Relayer Endpoint URL:", classes="modal-label")
                yield Input(value="https://mainnet-tornado-relayer.example.org/v1/tornadoWithdraw", id="input-relayer-url")
            else:
                yield Label("Target Ethereum RPC Endpoint:", classes="modal-label")
                yield Input(value="http://127.0.0.1:8545", id="input-rpc-url")
                yield Label("Sender Private Key (Optional - for local signing & eth_sendRawTransaction):", classes="modal-label")
                yield Input(placeholder="0x... (leave empty if node has unlocked account)", password=True, id="input-private-key")

            yield Static("Ready to broadcast...", id="broadcast-status")

            with Horizontal(id="broadcast-btn-bar"):
                yield Button("Cancel", variant="default", id="btn-cancel-broadcast")
                yield Button("Confirm & Broadcast 🚀", variant="warning", id="btn-confirm-broadcast")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel-broadcast":
            self.dismiss(None)
        elif event.button.id == "btn-confirm-broadcast":
            status_box = self.query_one("#broadcast-status", Static)
            status_box.update("⏳ Submitting to network...")
            if self.is_relayer:
                url = self.query_one("#input-relayer-url", Input).value.strip()
                try:
                    from kohaku.edw.p2p import post_json_rpc
                    payload = {"contract": self.contract_address, "data": self.calldata}
                    res = post_json_rpc(url, payload)
                    status_box.update(f"✓ RELAYER ACCEPTED:\n{json.dumps(res, indent=2)}")
                except Exception as e:
                    status_box.update(f"❌ Relayer dispatch failed: {e}")
            else:
                rpc_url = self.query_one("#input-rpc-url", Input).value.strip()
                pk = self.query_one("#input-private-key", Input).value.strip()
                try:
                    from kohaku.edw.p2p import P2PBroadcaster
                    broadcaster = P2PBroadcaster(peers=[rpc_url])
                    if pk:
                        from eth_account import Account
                        acc = Account.from_key(pk)
                        nonce = broadcaster.rpc_call("eth_getTransactionCount", [acc.address, "pending"])
                        gas_price = broadcaster.rpc_call("eth_gasPrice")
                        tx_dict = {
                            "to": self.contract_address,
                            "data": bytes.fromhex(self.calldata[2:] if self.calldata.startswith("0x") else self.calldata),
                            "value": 0,
                            "gas": 450000,
                            "gasPrice": int(gas_price, 16) if isinstance(gas_price, str) else gas_price,
                            "nonce": int(nonce, 16) if isinstance(nonce, str) else nonce,
                            "chainId": 1,
                        }
                        signed = acc.sign_transaction(tx_dict)
                        res = broadcaster.broadcast_raw_tx(signed.raw_transaction.hex())
                        status_box.update(f"✓ BROADCAST SUCCESSFUL!\nTx Hash: {res.tx_hash}\nPeer: {res.peer}")
                    else:
                        tx_obj = {"to": self.contract_address, "data": self.calldata, "value": "0x0"}
                        res = broadcaster.rpc_call("eth_sendTransaction", [tx_obj])
                        status_box.update(f"✓ TRANSACTION BROADCAST!\nTx Hash: {res}\nRPC: {rpc_url}")
                except Exception as e:
                    status_box.update(f"❌ Broadcast failed: {e}")

