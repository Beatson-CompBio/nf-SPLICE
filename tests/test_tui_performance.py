"""Release-blocking responsiveness on the synthetic scale fixture (fixture D).

Selecting a row and moving between visited pages read only the in-memory
view model: they never scan the repository or parse a draft, so their cost
does not grow with the number of files. The latency targets are the spec's
(cached row selection p95 < 100 ms; cached navigation p95 < 250 ms).

Selection and navigation are measured as the process CPU time a keypress
costs: the headless pilot adds fixed waits for an idle screen (about 85 ms
per key even for a bare DataTable) that a person at a terminal never sees,
so wall-clock times under the pilot overstate latency. Wall-clock times are
recorded alongside. Set ``NF_SPLICE_LATENCY_REPORT`` to a file to keep the
measured values.
"""

from __future__ import annotations

import asyncio
import json
import os
import platform
import statistics
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from textual.widgets import DataTable, Tree

from layer_fixtures import ADA, edit_draft_file
from nf_splice.drafts import yamlio
from nf_splice.interfaces.tui import NfSpliceApp
from nf_splice.interfaces.tui.modals import HelpDialog
from nf_splice.services.workspace import initialise
from scale_fixture import (
    MODULES,
    OUTPUTS,
    PARAMETERS,
    scale_outputs,
    write_scale_pipeline,
)
from tui_helpers import settle

pytestmark = pytest.mark.asyncio
ROW_P95_MS = 100.0
NAVIGATION_P95_MS = 250.0
VISITED = ("identity", "assays", "parameters", "outputs", "software", "execution")


@pytest.fixture(scope="module")
def scale_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("scale") / "pipeline"
    write_scale_pipeline(root)
    initialise(root, ADA)
    edit_draft_file(root, "outputs", lambda data: data.update(outputs=scale_outputs()))
    return root


class Counter:
    """Counts repository scans and draft parses while it is active."""

    def __init__(self) -> None:
        self.calls: dict[str, int] = {}

    def wrap(self, name: str, function: Any) -> Any:
        def counted(*args: Any, **kwargs: Any) -> Any:
            self.calls[name] = self.calls.get(name, 0) + 1
            return function(*args, **kwargs)

        return counted

    @property
    def total(self) -> int:
        return sum(self.calls.values())


@contextmanager
def counting() -> Iterator[Counter]:
    counter = Counter()
    with (
        mock.patch.object(Path, "rglob", counter.wrap("rglob", Path.rglob)),
        mock.patch.object(Path, "glob", counter.wrap("glob", Path.glob)),
        mock.patch.object(os, "walk", counter.wrap("walk", os.walk)),
        mock.patch.object(os, "scandir", counter.wrap("scandir", os.scandir)),
        mock.patch.object(
            yamlio, "load_yaml_draft", counter.wrap("parse", yamlio.load_yaml_draft)
        ),
    ):
        yield counter


def p95(values: list[float]) -> float:
    return sorted(values)[max(0, round(len(values) * 0.95) - 1)]


def _record(name: str, values: list[float]) -> None:
    target = os.environ.get("NF_SPLICE_LATENCY_REPORT")
    if not target:
        return
    path = Path(target)
    document = json.loads(path.read_text("utf-8")) if path.is_file() else {}
    document["machine"] = f"{platform.machine()} {platform.platform()}"
    document["python"] = platform.python_version()
    document[name] = {
        "samples": len(values),
        "p50_ms": round(statistics.median(values), 1),
        "p95_ms": round(p95(values), 1),
        "max_ms": round(max(values), 1),
    }
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


async def _open(app: NfSpliceApp, pilot: Any) -> None:
    await settle(app, pilot)
    for _ in range(600):  # the cold build of fixture D runs in a worker
        if app.model_ready:
            break
        await pilot.pause(0.05)
    assert app.model_ready
    assert len(app.model.parameters) == PARAMETERS
    assert len(app.model.components) >= MODULES
    assert len(app.model.outputs) == OUTPUTS


async def _select_rows(
    app: NfSpliceApp, pilot: Any, table: DataTable[Any] | Tree[Any], count: int
) -> tuple[list[float], list[float]]:
    table.focus()
    await pilot.pause()
    cpu, wall = [], []
    for index in range(count):
        started, clock = time.process_time(), time.perf_counter()
        await pilot.press("down" if index % 10 < 7 else "up")
        await pilot.pause()
        cpu.append((time.process_time() - started) * 1000)
        wall.append((time.perf_counter() - clock) * 1000)
    return cpu, wall


@pytest.mark.parametrize(
    ("page", "selector"),
    [
        ("assays", "#assay-tree"),
        ("parameters", "#parameter-table"),
        ("outputs", "#outputs-table"),
        ("software", "#software-table"),
    ],
)
async def test_selecting_rows_never_scans_and_stays_fast(
    scale_root: Path, page: str, selector: str
) -> None:
    app = NfSpliceApp(scale_root, user="Ada", start=page)
    async with app.run_test(size=(160, 50)) as pilot:
        await _open(app, pilot)
        await settle(app, pilot)
        widget = app.screen.query_one(selector)
        assert isinstance(widget, DataTable | Tree)
        with counting() as counter:
            times, wall = await _select_rows(app, pilot, widget, 100)
        _record(f"row_selection_cpu_{page}", times)
        _record(f"row_selection_wall_under_pilot_{page}", wall)
        assert counter.total == 0, counter.calls
        assert p95(times) < ROW_P95_MS, (page, p95(times))


async def test_moving_between_visited_pages_never_parses_and_stays_fast(
    scale_root: Path,
) -> None:
    app = NfSpliceApp(scale_root, user="Ada", start="overview")
    async with app.run_test(size=(160, 50)) as pilot:
        await _open(app, pilot)
        for page in VISITED:  # first visits mount each page once
            app.show_page(page)
            await settle(app, pilot)
        times, wall = [], []
        with counting() as counter:
            for _ in range(5):
                for page in VISITED:
                    started, clock = time.process_time(), time.perf_counter()
                    app.show_page(page)
                    await pilot.pause()
                    times.append((time.process_time() - started) * 1000)
                    wall.append((time.perf_counter() - clock) * 1000)
        _record("navigation_cached_cpu", times)
        _record("navigation_cached_wall_under_pilot", wall)
        assert counter.calls.get("parse", 0) == 0, counter.calls
        assert counter.calls.get("rglob", 0) == counter.calls.get("walk", 0) == 0
        assert p95(times) < NAVIGATION_P95_MS, p95(times)


async def test_the_interface_answers_while_the_cold_model_is_built(
    scale_root: Path,
) -> None:
    yamlio.clear_cache()  # a cold start: nothing parsed yet in this process
    app = NfSpliceApp(scale_root, user="Ada", start="overview")
    async with app.run_test(size=(160, 50)) as pilot:
        await pilot.pause(0.3)
        assert not app.model_ready  # the build is still running in its worker
        started = time.perf_counter()
        app.action_help()
        while not isinstance(app.screen, HelpDialog) or not app.screen.is_mounted:
            await asyncio.sleep(0.005)
        answered = (time.perf_counter() - started) * 1000
        _record("help_shown_during_cold_build_wall", [answered])
        # Contention with the build worker slows the interface but never
        # freezes it; the build itself shows progress in the status line.
        assert answered < 1000
        app.screen.dismiss(None)
        await _open(app, pilot)
