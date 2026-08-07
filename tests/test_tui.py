"""Textual Pilot tests for the shared workspace application shell."""

import asyncio
from pathlib import Path

from textual.widgets import ListView, Static

from nf_splice.interfaces.tui import NfSpliceApp
from nf_splice.services import ApplicationService


def test_tui_starts_with_shared_snapshot_and_navigates_layers(
    tmp_path: Path,
) -> None:
    (tmp_path / "main.nf").write_text("workflow {}\n", encoding="utf-8")
    snapshot = ApplicationService().inspect(tmp_path)
    app = NfSpliceApp(snapshot)

    async def exercise() -> None:
        async with app.run_test() as pilot:
            repository = app.query_one("#repository", Static)
            layer_detail = app.query_one("#layer-detail", Static)
            evidence = app.query_one("#evidence", Static)
            layers = app.query_one("#layers", ListView)

            assert str(tmp_path.resolve()) in str(repository.content)
            assert "Identity" in str(layer_detail.content)
            assert "Nextflow Source: 1" in str(evidence.content)
            assert layers.index == 0

            await pilot.press("down")
            await pilot.pause()

            assert layers.index == 1
            assert "Inputs" in str(layer_detail.content)

    asyncio.run(exercise())
