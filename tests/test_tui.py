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

            # 5. Test Stealth Address generation
            app.action_switch_tab("tab-stealth")
            await pilot.pause()
            app.query_one("#btn-gen-stealth").press()
            await pilot.pause()
            stealth_box = app.query_one("#stealth-result-box")
            assert "One-Time Stealth Address" in str(stealth_box.content)

    asyncio.run(_run())
