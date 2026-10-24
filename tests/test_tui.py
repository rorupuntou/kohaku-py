import asyncio
from kohaku.tui.app import KohakuApp


def test_tui_app_mount_and_headless():
    async def _run():
        app = KohakuApp(chain_id=1)
        async with app.run_test() as pilot:
            assert app.chain_id == 1
            assert app.mnemonic is None
            tabbed = app.query_one("TabbedContent")
            assert tabbed is not None

    asyncio.run(_run())
