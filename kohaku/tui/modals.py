"""Modal dialogs for Kohaku TUI wallet."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from eth_account import Account
from eth_utils import to_checksum_address
from textual.app import ComposeResult
from textual.containers import Grid, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static

Account.enable_unaudited_hdwallet_features()

DEV_TEST_SEED = "test test test test test test test test test test test junk"

RPC_PRESETS: list[tuple[str, str]] = [
    ("PublicNode (Mainnet - Fast & Public)", "https://ethereum-rpc.publicnode.com"),
    ("1RPC / Automata (Mainnet - Anti-MEV / Privacy)", "https://1rpc.io/eth"),
    ("MEV Blocker (Mainnet - CoW DAO / Beaver)", "https://rpc.mevblocker.io"),
    ("Sepolia Testnet (PublicNode)", "https://ethereum-sepolia-rpc.publicnode.com"),
    ("Local Node (http://127.0.0.1:8545)", "http://127.0.0.1:8545"),
    ("Custom RPC Endpoint...", "custom"),
]

RELAYER_PRESETS: list[tuple[str, str]] = [
    ("00Relayer (eth.00relayer.xyz - Verified Mainnet)", "https://eth.00relayer.xyz/v1/tornadoWithdraw"),
    ("Tornado Community Relayer (tornadocash.eth.limo)", "https://relayer.tornadocash.eth.limo/v1/tornadoWithdraw"),
    ("Local Relayer Daemon (http://127.0.0.1:8000)", "http://127.0.0.1:8000/v1/tornadoWithdraw"),
    ("Custom Relayer Endpoint...", "custom"),
]


def fetch_eth_balance(address: str, rpc_url: str = "https://ethereum-rpc.publicnode.com", timeout: float = 6.0) -> float:
    """Fetches ETH balance of an address using eth_getBalance via JSON-RPC."""
    try:
        data = json.dumps({
            "jsonrpc": "2.0",
            "method": "eth_getBalance",
            "params": [to_checksum_address(address), "latest"],
            "id": 1,
        }).encode("utf-8")
        req = urllib.request.Request(
            rpc_url,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            wei = int(res.get("result", "0x0"), 16)
            return wei / 1e18
    except Exception:
        return 0.0


class SeedModal(ModalScreen[str]):
    """Modal dialog prompting the user to provide or generate a mnemonic seed phrase."""

    DEFAULT_CSS = """
    SeedModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }

    #seed-dialog {
        width: 82;
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

    #seed-status-msg {
        color: $success;
        text-style: bold;
        margin-bottom: 1;
        height: auto;
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
            yield Label("🦊 Unlock / Switch Kohaku Desktop Wallet", id="dialog-title")
            yield Static(
                "Enter your 12- or 24-word mnemonic seed phrase to derive your accounts, "
                "stealth meta-address, and private notes:",
                classes="modal-desc",
            )
            yield Input(
                placeholder="word1 word2 word3 ... word12",
                id="mnemonic-input",
                password=False,
            )
            yield Static("", id="seed-status-msg")
            with Horizontal(id="button-bar"):
                yield Button("Dev Test Seed", variant="warning", id="btn-dev-seed")
                yield Button("✨ Generate New", variant="default", id="btn-generate")
                yield Button("Unlock & Load 🚀", variant="primary", id="btn-unlock")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        status_box = self.query_one("#seed-status-msg", Static)
        inp = self.query_one("#mnemonic-input", Input)

        if event.button.id == "btn-dev-seed":
            inp.value = DEV_TEST_SEED
            status_box.update("✓ Dev test seed loaded. Click 'Unlock & Load' to initialize.")
        elif event.button.id == "btn-generate":
            acc, mnemonic = Account.create_with_mnemonic()
            inp.value = mnemonic
            status_box.update("✨ New 12-word mnemonic generated! Save it securely, then click 'Unlock & Load'.")
        elif event.button.id == "btn-unlock":
            val = inp.value.strip()
            if val:
                self.dismiss(val)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        val = event.value.strip()
        if val:
            self.dismiss(val)


class AccountModal(ModalScreen[None]):
    """Modal displaying full details, private key, and balance for a derived Ethereum account."""

    DEFAULT_CSS = """
    AccountModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }

    #account-dialog {
        width: 84;
        height: auto;
        border: solid $accent;
        background: $surface;
        padding: 1 2;
    }

    #account-title {
        text-align: center;
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    .account-row {
        margin-bottom: 1;
    }

    .account-label {
        color: $text-muted;
        text-style: bold;
    }

    .account-val {
        color: $text;
        background: $surface-darken-1;
        padding: 0 1;
    }

    .account-key-val {
        color: $warning;
        text-style: bold;
        background: $surface-darken-1;
        padding: 0 1;
    }

    #account-btn-bar {
        align: right middle;
        margin-top: 1;
        height: auto;
    }

    #account-btn-bar Button {
        margin-left: 1;
    }
    """

    def __init__(self, index: int, path: str, address: str, private_key: str, rpc_url: str = "https://ethereum-rpc.publicnode.com"):
        super().__init__()
        self.acc_index = index
        self.derivation_path = path
        self.address = to_checksum_address(address)
        self.private_key = private_key if private_key.startswith("0x") else f"0x{private_key}"
        self.rpc_url = rpc_url

    def compose(self) -> ComposeResult:
        with Vertical(id="account-dialog"):
            yield Label(f"🔑 Account #{self.acc_index} Keys & Details", id="account-title")

            with Vertical(classes="account-row"):
                yield Label("Derivation Path:", classes="account-label")
                yield Static(self.derivation_path, classes="account-val")

            with Vertical(classes="account-row"):
                yield Label("Public Address (EIP-55 Checksum):", classes="account-label")
                yield Static(self.address, classes="account-val")

            with Vertical(classes="account-row"):
                yield Label("Private Key (secp256k1):", classes="account-label")
                yield Static(self.private_key, classes="account-key-val")

            with Vertical(classes="account-row"):
                yield Label(f"Live Balance on L1 ({self.rpc_url}):", classes="account-label")
                yield Static("Querying RPC balance...", classes="account-val", id="account-balance-val")

            with Horizontal(id="account-btn-bar"):
                yield Button("📋 Copy Address", variant="default", id="btn-copy-address")
                yield Button("📋 Copy PrivKey", variant="warning", id="btn-copy-privkey")
                yield Button("🔄 Refresh Balance", variant="default", id="btn-refresh-balance")
                yield Button("Close", variant="primary", id="btn-close-account")

    def on_mount(self) -> None:
        self.query_balance()

    def query_balance(self) -> None:
        bal_box = self.query_one("#account-balance-val", Static)
        try:
            bal = fetch_eth_balance(self.address, self.rpc_url)
            bal_box.update(f"{bal:.6f} ETH")
        except Exception as e:
            bal_box.update(f"Error fetching balance: {e}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-close-account":
            self.dismiss(None)
        elif event.button.id == "btn-copy-address":
            self.app.copy_text(self.address)
            self.notify("Address copied to clipboard! 📋")
        elif event.button.id == "btn-copy-privkey":
            self.app.copy_text(self.private_key)
            self.notify("Private key copied to clipboard! 🔑 (Keep secret!)")
        elif event.button.id == "btn-refresh-balance":
            self.query_balance()



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
        width: 88;
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
        min-height: 3;
    }
    #broadcast-btn-bar {
        align: right middle;
        margin-top: 1;
    }
    #broadcast-btn-bar Button {
        margin-left: 1;
    }
    .action-row {
        height: auto;
        margin-top: 1;
        margin-bottom: 1;
    }
    """

    def __init__(
        self,
        contract_address: str,
        calldata: str,
        pool_id: str,
        is_relayer: bool = False,
        recipient: str = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
        relayer_address: str = "0xda0b76cc92e94a6f972Ed29C104BBe8d73c2f753",
        fee: int = 0,
        refund: int = 0,
        root: int | str = 0,
        nullifier_hash: int | str = 0,
        proof_hex: str = "",
        accounts: list[dict[str, str]] | None = None,
    ):
        super().__init__()
        self.contract_address = contract_address
        self.calldata = calldata
        self.pool_id = pool_id
        self.is_relayer = is_relayer
        self.recipient = recipient
        self.relayer_address = relayer_address
        self.fee = fee
        self.refund = refund
        self.root = root
        self.nullifier_hash = nullifier_hash
        self.proof_hex = proof_hex
        self.accounts = accounts or []

    def compose(self) -> ComposeResult:
        with Vertical(id="broadcast-dialog"):
            yield Label("🚀 On-Chain Broadcast & Relayer Dispatch", id="broadcast-title")
            yield Static(
                "⚠️ OPSEC CAUTION: Submitting will send this transaction to the network. "
                "Ensure your IP is protected (Tor / VPN) and the recipient address is unlinked.",
                classes="broadcast-warning",
            )

            yield Label("Delivery Mode:", classes="modal-label")
            yield Select(
                [
                    ("Direct L1 Transaction (User Pays Gas)", "direct"),
                    ("Tornado Relayer (Gasless Paymaster Delivery)", "relayer"),
                ],
                id="select-delivery-mode",
                value="relayer" if self.is_relayer else "direct",
                allow_blank=False,
            )

            with Vertical(id="container-relayer"):
                yield Label("Select Verified Tornado Relayer Preset:", classes="modal-label")
                yield Select(RELAYER_PRESETS, id="select-relayer-preset", value=RELAYER_PRESETS[0][1], allow_blank=False)
                yield Label("Relayer Endpoint URL (auto-appends /v1/tornadoWithdraw):", classes="modal-label")
                yield Input(value=RELAYER_PRESETS[0][1], id="input-relayer-url")
                with Horizontal(classes="action-row"):
                    yield Button("🔍 Ping Relayer Status (/v1/status)", variant="default", id="btn-ping-relayer")

            with Vertical(id="container-direct"):
                if self.accounts:
                    acc_options: list[tuple[str, str]] = []
                    for a in self.accounts:
                        short_addr = f"{a['address'][:6]}...{a['address'][-4:]}"
                        pk_val = a.get("private_key", "")
                        acc_options.append((f"Account #{a['index']} ({short_addr})", pk_val))
                    acc_options.append(("Custom Private Key Input...", "custom"))

                    yield Label("Sender Account (Auto-fill Private Key):", classes="modal-label")
                    init_pk = acc_options[0][1] if acc_options else ""
                    yield Select(acc_options, id="select-sender-account", value=init_pk, allow_blank=False)
                else:
                    init_pk = ""

                yield Label("Select Verified Ethereum L1 RPC Preset:", classes="modal-label")
                yield Select(RPC_PRESETS, id="select-rpc-preset", value=RPC_PRESETS[0][1], allow_blank=False)
                yield Label("Target Ethereum RPC Endpoint:", classes="modal-label")
                yield Input(value=RPC_PRESETS[0][1], id="input-rpc-url")

                yield Label("Sender Private Key (used for local signing & eth_sendRawTransaction):", classes="modal-label")
                yield Input(value=init_pk, placeholder="0x... (leave empty if node has unlocked account)", password=True, id="input-private-key")

                with Horizontal(classes="action-row"):
                    yield Button("🔍 Test RPC Connection", variant="default", id="btn-test-rpc")
                    yield Button("💰 Check Sender Balance", variant="default", id="btn-check-sender-bal")

                yield Static("Sender balance not checked yet...", id="sender-balance-box")

            yield Static("Ready to broadcast or dispatch...", id="broadcast-status")

            with Horizontal(id="broadcast-btn-bar"):
                yield Button("Cancel", variant="default", id="btn-cancel-broadcast")
                yield Button("Confirm & Broadcast 🚀", variant="warning", id="btn-confirm-broadcast")

    def on_mount(self) -> None:
        self.query_one("#container-relayer").display = self.is_relayer
        self.query_one("#container-direct").display = not self.is_relayer
        if not self.is_relayer:
            self.check_sender_balance()

    def check_sender_balance(self) -> None:
        box = self.query_one("#sender-balance-box", Static)
        try:
            rpc_url = self.query_one("#input-rpc-url", Input).value.strip()
            pk = self.query_one("#input-private-key", Input).value.strip()
            if pk:
                acc = Account.from_key(pk)
                addr = to_checksum_address(acc.address)
                bal = fetch_eth_balance(addr, rpc_url)
                if bal <= 0.000005:
                    box.update(
                        f"Sender: {addr}\n"
                        f"Balance: {bal:.6f} ETH\n"
                        f"⚠️ WARNING: Insufficient funds for gas! Have {bal} ETH, need ~0.00002 ETH on this network.\n"
                        f"Broadcasting from an empty address will fail on L1 public nodes."
                    )
                else:
                    box.update(f"Sender: {addr} | Balance: {bal:.6f} ETH (✓ Sufficient for gas)")
            else:
                box.update("Sender: Node unlocked account mode (eth_sendTransaction)")
        except Exception as e:
            box.update(f"Balance check notice: {e}")

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "select-delivery-mode":
            is_rel = str(event.value) == "relayer"
            self.query_one("#container-relayer").display = is_rel
            self.query_one("#container-direct").display = not is_rel
        elif event.select.id == "select-rpc-preset":
            val = str(event.value)
            if val != "custom" and event.value != Select.BLANK:
                self.query_one("#input-rpc-url", Input).value = val
                self.check_sender_balance()
        elif event.select.id == "select-relayer-preset":
            val = str(event.value)
            if val != "custom" and event.value != Select.BLANK:
                self.query_one("#input-relayer-url", Input).value = val
                if "00relayer" in val:
                    self.relayer_address = "0xda0b76cc92e94a6f972Ed29C104BBe8d73c2f753"
        elif event.select.id == "select-sender-account":
            val = str(event.value)
            if val != "custom" and event.value != Select.BLANK:
                self.query_one("#input-private-key", Input).value = val
                self.check_sender_balance()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        status_box = self.query_one("#broadcast-status", Static)

        if event.button.id == "btn-cancel-broadcast":
            self.dismiss(None)

        elif event.button.id == "btn-check-sender-bal":
            self.check_sender_balance()

        elif event.button.id == "btn-test-rpc":
            rpc_url = self.query_one("#input-rpc-url", Input).value.strip()
            status_box.update(f"⏳ Connecting to {rpc_url}...")
            try:
                data = json.dumps({"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 1}).encode("utf-8")
                req = urllib.request.Request(
                    rpc_url,
                    data=data,
                    headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
                )
                with urllib.request.urlopen(req, timeout=6) as resp:
                    res = json.loads(resp.read().decode("utf-8"))
                    block_hex = res.get("result", "0x0")
                    block_num = int(block_hex, 16)
                    status_box.update(f"✓ RPC CONNECTED!\nLatest Block: #{block_num:,} ({block_hex})\nEndpoint: {rpc_url}")
                self.check_sender_balance()
            except Exception as e:
                status_box.update(f"❌ RPC connection error: {e}")

        elif event.button.id == "btn-ping-relayer":
            url = self.query_one("#input-relayer-url", Input).value.strip()
            status_box.update("⏳ Pinging relayer status...")
            try:
                parsed = urllib.parse.urlparse(url)
                base_url = f"{parsed.scheme}://{parsed.netloc}"
                status_url = f"{base_url}/v1/status"
                req = urllib.request.Request(status_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=6) as resp:
                    st_data = json.loads(resp.read().decode("utf-8"))
                    reward_acc = st_data.get("rewardAccount", "0xda0b76cc92e94a6f972Ed29C104BBe8d73c2f753")
                    self.relayer_address = to_checksum_address(reward_acc)
                    fee = st_data.get("tornadoServiceFee", "N/A")
                    version = st_data.get("version", "N/A")
                    health = st_data.get("health", {})
                    status_box.update(
                        f"✓ RELAYER ONLINE (HTTP 200)\n"
                        f"Endpoint:       {base_url}\n"
                        f"Reward Account: {reward_acc} (auto-synced as fee recipient)\n"
                        f"Service Fee:    {fee}%\n"
                        f"Version:        {version}\n"
                        f"Health:         {health}"
                    )
            except Exception as e:
                status_box.update(f"❌ Relayer unreachable: {e}")

        elif event.button.id == "btn-confirm-broadcast":
            delivery_mode = str(self.query_one("#select-delivery-mode", Select).value)
            status_box.update("⏳ Submitting to network...")

            if delivery_mode == "relayer":
                raw_url = self.query_one("#input-relayer-url", Input).value.strip()
                if not raw_url:
                    status_box.update("❌ Please provide a relayer endpoint URL.")
                    return

                # Normalize relayer endpoint (auto-append /v1/tornadoWithdraw if omitted)
                parsed = urllib.parse.urlparse(raw_url)
                if not parsed.path or parsed.path == "/":
                    url = raw_url.rstrip("/") + "/v1/tornadoWithdraw"
                else:
                    url = raw_url

                try:
                    c_addr = to_checksum_address(self.contract_address)
                    recip_addr = to_checksum_address(self.recipient)

                    # Ensure fee recipient matches relayer reward account
                    if "00relayer" in url:
                        rel_addr = to_checksum_address("0xda0b76cc92e94a6f972Ed29C104BBe8d73c2f753")
                    else:
                        rel_addr = to_checksum_address(self.relayer_address)

                    root_int = int(self.root, 16) if isinstance(self.root, str) else int(self.root)
                    null_int = int(self.nullifier_hash, 16) if isinstance(self.nullifier_hash, str) else int(self.nullifier_hash)

                    p_hex = self.proof_hex
                    if not p_hex.startswith("0x"):
                        p_hex = "0x" + p_hex
                    if len(p_hex) < 514:
                        p_hex = "0x" + p_hex[2:].zfill(512)

                    payload = {
                        "contract": c_addr,
                        "proof": p_hex,
                        "args": [
                            f"0x{root_int:064x}",
                            f"0x{null_int:064x}",
                            recip_addr,
                            rel_addr,
                            f"0x{int(self.fee):064x}",
                            f"0x{int(self.refund):064x}",
                        ],
                    }

                    data_bytes = json.dumps(payload).encode("utf-8")
                    req = urllib.request.Request(
                        url,
                        data=data_bytes,
                        headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
                    )
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        res = json.loads(resp.read().decode("utf-8"))
                        status_box.update(f"✓ RELAYER DISPATCH ACCEPTED:\n{json.dumps(res, indent=2)}")
                except urllib.error.HTTPError as he:
                    err_body = he.read().decode("utf-8", errors="replace")
                    status_box.update(f"❌ Relayer response (HTTP {he.code}):\n{err_body}")
                except Exception as e:
                    status_box.update(f"❌ Relayer dispatch failed: {e}")

            else:
                rpc_url = self.query_one("#input-rpc-url", Input).value.strip()
                pk = self.query_one("#input-private-key", Input).value.strip()
                try:
                    from kohaku.edw.p2p import P2PBroadcaster
                    broadcaster = P2PBroadcaster(peers=[rpc_url])
                    target_addr = to_checksum_address(self.contract_address)
                    if pk:
                        acc = Account.from_key(pk)
                        acc_addr = to_checksum_address(acc.address)

                        # Check balance before broadcasting
                        bal = fetch_eth_balance(acc_addr, rpc_url)
                        if bal <= 0.000005:
                            status_box.update(
                                f"❌ Broadcast aborted: Insufficient funds for gas!\n"
                                f"Sender {acc_addr} has {bal:.6f} ETH on this network.\n"
                                f"You need ~0.00002 ETH to pay for transaction gas on Ethereum L1."
                            )
                            return

                        nonce = broadcaster.rpc_call("eth_getTransactionCount", [acc_addr, "pending"])
                        gas_price = broadcaster.rpc_call("eth_gasPrice")
                        tx_dict = {
                            "to": target_addr,
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
                        tx_obj = {"to": target_addr, "data": self.calldata, "value": "0x0"}
                        res = broadcaster.rpc_call("eth_sendTransaction", [tx_obj])
                        status_box.update(f"✓ TRANSACTION BROADCAST!\nTx Hash: {res}\nRPC: {rpc_url}")
                except Exception as e:
                    status_box.update(f"❌ Broadcast failed: {e}")



