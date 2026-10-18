"""Helpers for driving and reading the unified workspace in tests."""

from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path
from typing import Any

from textual.widgets import Button, DataTable, Input, Static

from nf_splice.interfaces.tui import NfSpliceApp


async def settle(app: NfSpliceApp, pilot: Any, rounds: int = 4) -> None:
    """Wait for workers (model, views, writes) and the re-renders they cause."""
    for _ in range(rounds):
        await app.workers.wait_for_complete()
        await pilot.pause()
    await app.workers.wait_for_complete()
    await pilot.pause()


async def wait_agent(app: NfSpliceApp, pilot: Any, timeout: float = 60.0) -> None:
    """Wait until the coordinator's background work has finished."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while (app.coordinator.busy or app.coordinator.asking) and loop.time() < deadline:
        await asyncio.sleep(0.05)
        await pilot.pause()
    assert not app.coordinator.busy, "the agent did not finish in time"
    await pilot.pause()
    app._agent_changed()
    await settle(app, pilot)


async def press(app: NfSpliceApp, pilot: Any, selector: str) -> None:
    """Press a button as a user would and wait for what it starts."""
    button = app.screen.query_one(selector, Button)
    button.press()
    await pilot.pause()
    await settle(app, pilot)


async def press_named(app: NfSpliceApp, pilot: Any, name: str) -> None:
    """Press a dynamically created button identified by its name."""
    for button in app.screen.query(Button):
        if button.name == name:
            button.press()
            await pilot.pause()
            await settle(app, pilot)
            return
    raise AssertionError(f"no button named {name!r}")


def page_text(app: NfSpliceApp) -> str:
    """Deterministic text of the top bar, rail and the current page."""
    lines = [str(app.query_one("#pipeline-name", Static).render())]
    lines += [str(item.label) for item in app.query(".rail-item").results(Button)]
    lines.append(f"== {app.current}")
    view = app.current_page()
    assert view is not None
    for widget in view.query("*"):
        if not widget.display or not all(
            ancestor.display for ancestor in widget.ancestors_with_self
        ):
            continue
        if isinstance(widget, DataTable):
            for index in range(widget.row_count):
                lines.append(" | ".join(str(cell) for cell in widget.get_row_at(index)))
        elif isinstance(widget, Input):
            lines.append(f"[{widget.placeholder}] {widget.value}")
        elif isinstance(widget, Button):
            lines.append(f"<{widget.label}>")
        elif isinstance(widget, Static):
            lines.append(str(widget.render()))
    return normalise("\n".join(lines))


def normalise(text: str) -> str:
    text = "\n".join(line.rstrip() for line in text.splitlines()).rstrip("\n") + "\n"
    text = re.sub(r"/[^\s'\"]*/(repo|cli|tui|multiroute)\b", r"<\1>", text)
    text = re.sub(r"\b[0-9a-f]{12,64}\b", "<hash>", text)
    return re.sub(r"session-[0-9a-z-]+", "<session>", text)


def screenshot(app: NfSpliceApp, name: str) -> Path | None:
    """Save an SVG screenshot when NF_SPLICE_SCREENSHOTS names a folder."""
    folder = os.environ.get("NF_SPLICE_SCREENSHOTS")
    if not folder:
        return None
    path = Path(folder) / f"{name}.svg"
    path.parent.mkdir(parents=True, exist_ok=True)
    app.save_screenshot(str(path))
    return path
