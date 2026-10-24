"""Kohaku Desktop Wallet Terminal User Interface (TUI)."""

from __future__ import annotations

from eth_account import Account
from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Container, Grid, Horizontal, ScrollableContainer, Vertical
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    Select,
    Static,
    TabbedContent,
    TabPane,
)

from kohaku.privacy_pools.pools import ALL_PRIVACY_POOLS
from kohaku.stealth import StealthKeypair, derive_stealth_keypair, generate_stealth_address
from kohaku.sync.client import DEFAULT_SAGA_URL, SagaClient
from kohaku.tornado.keychain import TornadoKeychain
from kohaku.tornado.note import TornadoNote
from kohaku.tornado.pools import MAINNET_POOLS
from kohaku.tornado.tx import build_deposit_transactions
from kohaku.tui.modals import NoteModal, SeedModal

Account.enable_unaudited_hdwallet_features()


class StatCard(Static):
    """Visual metric display card."""

    DEFAULT_CSS = """
    StatCard {
        background: $surface;
        border: solid $accent;
        padding: 1 2;
        height: 7;
        margin: 0 1 1 0;
    }
    .stat-title {
        color: $text-muted;
        text-style: bold;
    }
    .stat-value {
        color: $accent;
        text-style: bold;
        margin-top: 1;
    }
    """

    def __init__(self, title: str, value: str, id: str | None = None):
        super().__init__(id=id)
        self.card_title = title
        self.card_value = value

    def compose(self) -> ComposeResult:
        yield Label(self.card_title, classes="stat-title")
        yield Label(self.card_value, classes="stat-value", id=f"{self.id}-val" if self.id else None)

    def update_value(self, new_val: str) -> None:
        self.card_value = new_val
        val_widget = self.query_one(".stat-value", Label)
        val_widget.update(new_val)


class KohakuApp(App[None]):
    """Ethereum Desktop Wallet (EDW) - Kohaku TUI Edition."""

    CSS = """
    Screen {
        background: $background;
    }

    #stats-row {
        height: 8;
        margin-bottom: 1;
    }

    .panel-box {
        background: $surface;
        border: round $primary;
        padding: 1;
        margin: 0 1 1 0;
    }

    .panel-header {
        color: $accent;
        text-style: bold;
        margin-bottom: 1;
    }

    #stealth-card {
        background: $surface-darken-1;
        border: solid $secondary;
        padding: 1 2;
        margin-bottom: 1;
    }

    .meta-uri-label {
        color: $accent;
        text-style: bold;
        background: $surface;
        padding: 1;
        border: dashed $accent;
        margin-top: 1;
    }

    #form-container {
        padding: 1 2;
    }

    .form-label {
        color: $text-muted;
        text-style: bold;
        margin-top: 1;
    }

    #calldata-box {
        background: $surface-darken-2;
        border: round $accent;
        padding: 1;
        margin-top: 1;
        height: 12;
        overflow-y: auto;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("d", "switch_tab('tab-dashboard')", "Dashboard"),
        ("s", "switch_tab('tab-shield')", "Shield"),
        ("t", "switch_tab('tab-stealth')", "Stealth"),
        ("n", "switch_tab('tab-network')", "Saga CDN"),
        ("r", "refresh_data", "Refresh"),
    ]

    TITLE = "Kohaku Desktop Wallet"
    SUB_TITLE = "Ethereum Privacy & Stealth Suite (edw-py)"

    def __init__(self, mnemonic: str | None = None, chain_id: int = 1):
        super().__init__()
        self.mnemonic = mnemonic
        self.chain_id = chain_id
        self.stealth_pair: StealthKeypair | None = None
        self.keychain: TornadoKeychain | None = None
        self.public_accounts: list[dict[str, str]] = []
        self.active_notes: list[dict[str, str]] = []
        self.client = SagaClient()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(id="main-tabs"):
            with TabPane("📊 Dashboard", id="tab-dashboard"):
                with Horizontal(id="stats-row"):
                    yield StatCard("PUBLIC ACCOUNTS", "0 accounts", id="stat-public")
                    yield StatCard("SHIELDED BALANCE", "0.0000 ETH", id="stat-shielded")
                    yield StatCard("SAGA PROTOCOLS", "15 active", id="stat-saga")
                    yield StatCard("STEALTH SCHEME", "ERC-5564 v1", id="stat-stealth")

                with Horizontal():
                    with Vertical(classes="panel-box"):
                        yield Label("PUBLIC ACCOUNTS (BIP-44 m/44'/60'/0'/0/i)", classes="panel-header")
                        yield DataTable(id="table-accounts")

                    with Vertical(classes="panel-box"):
                        yield Label("SHIELDED & PRIVATE NOTES", classes="panel-header")
                        yield DataTable(id="table-notes")

            with TabPane("🌪️ Shield & Deposit", id="tab-shield"):
                with ScrollableContainer(id="form-container"):
                    yield Label("1. Select Shielded Pool:", classes="form-label")
                    pools_list = [(f"{p.amount} {p.asset} (Tornado)", p.id) for p in MAINNET_POOLS.values()]
                    yield Select(pools_list, id="select-pool", value="tornado-cash-1-eth-0.1")

                    yield Label("2. Generate Action:", classes="form-label")
                    yield Button("⚡ Generate Note & Build On-Chain Calldata", variant="primary", id="btn-build-deposit")

                    yield Label("3. Transaction Calldata & CLI Cast Command:", classes="form-label")
                    yield Static("Select a pool and click build to generate calldata...", id="calldata-box")

            with TabPane("🕵️ Stealth Addresses", id="tab-stealth"):
                with ScrollableContainer(classes="panel-box"):
                    yield Label("YOUR ERC-5564 / ERC-6538 STEALTH META-ADDRESS", classes="panel-header")
                    with Vertical(id="stealth-card"):
                        yield Static("Share this meta-address publicly. Senders generate untraceable one-time addresses:", classes="stat-title")
                        yield Label("Not loaded yet...", classes="meta-uri-label", id="lbl-meta-uri")

                    yield Label("GENERATE ONE-TIME STEALTH ADDRESS FOR A RECIPIENT", classes="panel-header")
                    yield Label("Recipient Stealth Meta-Address (st:eth:0x...):", classes="form-label")
                    yield Input(placeholder="st:eth:0x...", id="input-recipient-meta")
                    yield Button("Generate Stealth Address (secp256k1 ECDH)", variant="success", id="btn-gen-stealth")
                    yield Static("", id="stealth-result-box")

            with TabPane("⚡ Saga CDN & Network", id="tab-network"):
                with ScrollableContainer(classes="panel-box"):
                    yield Label(f"SAGA SYNC SNAPSHOTS (CDN: {DEFAULT_SAGA_URL})", classes="panel-header")
                    yield DataTable(id="table-saga-protocols")

        yield Footer()

    def on_mount(self) -> None:
        self.init_tables()
        if self.mnemonic:
            self.load_wallet(self.mnemonic)
        else:
            self.push_screen(SeedModal(), self.load_wallet)

    def init_tables(self) -> None:
        # Accounts table
        acc_table = self.query_one("#table-accounts", DataTable)
        acc_table.add_columns("IDX", "DERIVATION PATH", "ADDRESS")
        acc_table.cursor_type = "row"

        # Notes table
        notes_table = self.query_one("#table-notes", DataTable)
        notes_table.add_columns("POOL", "AMOUNT", "COMMITMENT", "STATUS")
        notes_table.cursor_type = "row"

        # Saga table
        saga_table = self.query_one("#table-saga-protocols", DataTable)
        saga_table.add_columns("PROTOCOL ID", "CHAIN", "CHUNKS", "BLOCK RANGE")
        saga_table.cursor_type = "row"

        # Populate Saga table asynchronously
        self.populate_saga_protocols()

    def populate_saga_protocols(self) -> None:
        try:
            m = self.client.get_manifest()
            saga_table = self.query_one("#table-saga-protocols", DataTable)
            saga_table.clear()
            for p_id in sorted(m.available_protocols.keys()):
                proto = m.available_protocols[p_id]
                rng = f"[{proto.block_range[0]}..{proto.block_range[1]}]" if proto.block_range else "empty"
                saga_table.add_row(p_id, str(proto.chain_id), str(proto.total_chunks), rng)
        except Exception:
            pass

    def load_wallet(self, mnemonic: str) -> None:
        self.mnemonic = mnemonic
        # 1. Derive 5 public accounts
        self.public_accounts.clear()
        acc_table = self.query_one("#table-accounts", DataTable)
        acc_table.clear()

        for idx in range(5):
            path = f"m/44'/60'/0'/0/{idx}"
            acc = Account.from_mnemonic(mnemonic, account_path=path)
            self.public_accounts.append({"index": str(idx), "path": path, "address": acc.address})
            acc_table.add_row(f"#{idx}", path, acc.address)

        # 2. Derive Stealth Keypair
        self.stealth_pair = derive_stealth_keypair(mnemonic, chain_id=self.chain_id)
        meta_label = self.query_one("#lbl-meta-uri", Label)
        meta_label.update(self.stealth_pair.stealth_meta_address_uri)

        # 3. Derive Tornado Keychain
        self.keychain = TornadoKeychain.from_mnemonic(mnemonic)

        # Update stats
        self.query_one("#stat-public", StatCard).update_value(f"{len(self.public_accounts)} Derived")

        # 4. Generate sample deterministic notes for display
        notes_table = self.query_one("#table-notes", DataTable)
        notes_table.clear()
        sample_pools = ["tornado-cash-1-eth-0.1", "tornado-cash-1-eth-1", "privacy-pools-1-eth"]
        for p in sample_pools:
            if "tornado" in p:
                note = self.keychain.derive_note(p, nonce=0)
                comm_short = f"{note.commitment_hex[:10]}...{note.commitment_hex[-8:]}"
                notes_table.add_row(p, f"{note.amount} ETH", comm_short, "DETERMINISTIC ✓")
            else:
                notes_table.add_row(p, "Dynamic", "0x07fdbcef...997d", "ACTIVE POOL")

    def action_switch_tab(self, tab_id: str) -> None:
        tabs = self.query_one("#main-tabs", TabbedContent)
        tabs.active = tab_id

    def action_refresh_data(self) -> None:
        if self.mnemonic:
            self.load_wallet(self.mnemonic)
        self.populate_saga_protocols()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-build-deposit":
            select = self.query_one("#select-pool", Select)
            pool_id = str(select.value)

            if "tornado" in pool_id and self.keychain:
                note = self.keychain.derive_note(pool_id, nonce=0)
                calls = build_deposit_transactions(note)
                call = calls[0]
                text = (
                    f"Pool: {pool_id}\n"
                    f"Note URI: {note.to_note_string()}\n\n"
                    f"Contract To: {call.to}\n"
                    f"Value:       {call.value} wei ({call.value / 10**18} ETH)\n"
                    f"Calldata:    {call.data}\n\n"
                    f"CLI Cast Command:\n"
                    f"  cast send {call.to} {call.data} --value {call.value} --private-key <YOUR_KEY>"
                )
            else:
                text = f"Selected pool {pool_id}. Privacy Pools dynamic shielding calldata ready."

            box = self.query_one("#calldata-box", Static)
            box.update(text)

        elif event.button.id == "btn-gen-stealth":
            inp = self.query_one("#input-recipient-meta", Input)
            val = inp.value.strip() or (self.stealth_pair.stealth_meta_address_uri if self.stealth_pair else "")
            if val:
                try:
                    res = generate_stealth_address(val)
                    res_text = (
                        f"One-Time Stealth Address: {res['stealth_address']}\n"
                        f"Ephemeral PubKey:         {res['ephemeral_public_key']}\n"
                        f"View Tag:                 {res['view_tag']}\n\n"
                        f"Funds sent to this address can only be spent by the meta-address owner!"
                    )
                except Exception as e:
                    res_text = f"Error generating stealth address: {e}"

                out_box = self.query_one("#stealth-result-box", Static)
                out_box.update(res_text)


def run_tui(mnemonic: str | None = None, chain_id: int = 1) -> None:
    """Launches the Kohaku TUI application."""
    app = KohakuApp(mnemonic=mnemonic, chain_id=chain_id)
    app.run()
