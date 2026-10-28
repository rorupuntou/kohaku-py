import asyncio
from pathlib import Path
from kohaku.tui.app import KohakuApp

TEST_SEED = "test test test test test test test test test test test junk"


def test_tui_app_mount_and_headless():
    async def _run():
        app = KohakuApp(chain_id=1)
        async with app.run_test() as pilot:
            assert app.chain_id == 1
            assert app.mnemonic is None
            tabbed = app.query_one("TabbedContent")
            assert tabbed is not None

    asyncio.run(_run())


def test_tui_interactive_wallet_lifecycle():
    async def _run():
        app = KohakuApp(mnemonic=TEST_SEED, chain_id=1)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.mnemonic == TEST_SEED
            assert len(app.public_accounts) == 5
            assert len(app.derived_notes) == 3

            # 1. Test Dashboard Note derivation
            app.query_one("#btn-add-note").press()
            await pilot.pause()
            assert len(app.derived_notes) == 4

            # 1.1 Test View Account Key & Details (AccountModal)
            app.query_one("#btn-view-acc-key").press()
            await pilot.pause()
            from kohaku.tui.modals import AccountModal
            assert any(isinstance(s, AccountModal) for s in app.screen_stack)
            app.screen.query_one("#btn-close-account").press()
            await pilot.pause()

            # 2. Test Note sync
            app.query_one("#btn-sync-notes").press()
            await pilot.pause()

            # 3. Test Shield Calldata generation
            app.action_switch_tab("tab-shield")
            await pilot.pause()
            app.query_one("#btn-build-deposit").press()
            await pilot.pause()
            calldata_box = app.query_one("#calldata-box")
            assert "0x" in str(calldata_box.content)

            # 4. Test Withdraw Tab & ZK Proof Simulation
            app.action_switch_tab("tab-withdraw")
            await pilot.pause()

            # Test synthetic proof verification
            app.query_one("#btn-verify-zk").press()
            await pilot.pause()
            res_box = app.query_one("#withdraw-result-box")
            assert "SYNTHETIC MOCK PROOF" in str(res_box.content)

            # Test custom proof file verification against fixture
            fixture_path = str(Path(__file__).parent / "fixtures" / "groth16_snarkjs_bn254.json")
            app.query_one("#select-proof-mode").value = "file"
            app.query_one("#input-proof-file-path").value = fixture_path
            app.query_one("#btn-verify-zk").press()
            await pilot.pause()
            assert "GROTH16 PROOF VALIDATED" in str(res_box.content)

            # Test Build Withdraw Transaction Calldata
            app.query_one("#btn-fill-acc0").press()
            app.query_one("#btn-build-withdraw").press()
            await pilot.pause()
            assert "0x21a0adb6" in str(res_box.content)
            assert "cast send" in str(res_box.content)
            assert app.last_withdrawal is not None

            # Test Copy Cast command and calldata
            app.query_one("#btn-copy-cast").press()
            await pilot.pause()
            assert "cast send" in app._clipboard

            app.query_one("#btn-copy-calldata").press()
            await pilot.pause()
            assert "0x21a0adb6" in app._clipboard

            # Test Export Payload JSON
            export_file = Path.cwd() / f"withdrawal_{app.last_withdrawal['pool_id']}.json"
            if export_file.exists():
                export_file.unlink()
            app.query_one("#btn-export-payload").press()
            await pilot.pause()
            assert export_file.exists()
            export_file.unlink()

            # Test Broadcast Modal Open and Cancel
            app.query_one("#btn-broadcast-dialog").press()
            await pilot.pause()
            from kohaku.tui.modals import BroadcastModal
            assert any(isinstance(s, BroadcastModal) for s in app.screen_stack)
            app.screen.query_one("#btn-cancel-broadcast").press()
            await pilot.pause()

            # 5. Test Stealth Address generation
            app.action_switch_tab("tab-stealth")
            await pilot.pause()
            app.query_one("#btn-gen-stealth").press()
            await pilot.pause()
            stealth_box = app.query_one("#stealth-result-box")
            assert "One-Time Stealth Address" in str(stealth_box.content)

    asyncio.run(_run())


def test_broadcast_modal_direct_and_relayer_presets():
    from kohaku.tui.modals import BroadcastModal, RPC_PRESETS, RELAYER_PRESETS
    from textual.app import App
    from textual.widgets import Select, Input

    class DummyApp(App[None]):
        def on_mount(self) -> None:
            self.push_screen(
                BroadcastModal(
                    contract_address="0x12d66f87a04a9e220743712ce6d9bb1b5616b8fc",
                    calldata="0x21a0adb6" + "00" * 256,
                    pool_id="tornado-cash-1-eth-0.1",
                    is_relayer=True,
                    recipient="0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
                    relayer_address="0xda0b76cc92e94a6f972Ed29C104BBe8d73c2f753",
                    fee=5_000_000_000_000_000,
                    refund=0,
                    root=12345,
                    nullifier_hash=67890,
                    proof_hex="0x" + "00" * 256,
                )
            )

    async def _run():
        app = DummyApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            modal = app.screen
            assert isinstance(modal, BroadcastModal)

            # Check relayer container is visible and direct is hidden
            assert modal.query_one("#container-relayer").display is True
            assert modal.query_one("#container-direct").display is False

            # Select different relayer preset
            relayer_select = modal.query_one("#select-relayer-preset", Select)
            relayer_select.value = RELAYER_PRESETS[1][1]
            await pilot.pause()
            relayer_input = modal.query_one("#input-relayer-url", Input)
            assert relayer_input.value == RELAYER_PRESETS[1][1]

            # Switch mode to direct L1
            mode_select = modal.query_one("#select-delivery-mode", Select)
            mode_select.value = "direct"
            await pilot.pause()
            assert modal.query_one("#container-relayer").display is False
            assert modal.query_one("#container-direct").display is True

            # Select different RPC preset
            rpc_select = modal.query_one("#select-rpc-preset", Select)
            rpc_select.value = RPC_PRESETS[1][1]
            await pilot.pause()
            rpc_input = modal.query_one("#input-rpc-url", Input)
            assert rpc_input.value == RPC_PRESETS[1][1]

            # Test dismiss via cancel button
            modal.query_one("#btn-cancel-broadcast").press()
            await pilot.pause()
            assert not any(isinstance(s, BroadcastModal) for s in app.screen_stack)

    asyncio.run(_run())

