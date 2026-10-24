"""Modal dialogs for Kohaku TUI wallet."""

from __future__ import annotations

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
