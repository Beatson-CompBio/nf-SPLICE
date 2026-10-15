"""Helpers for driving and snapshotting the Textual wizard."""

from __future__ import annotations

import os
import re
from pathlib import Path

from textual.widgets import Button, DataTable, Input, Label, Select, Static, Switch

from nf_splice.interfaces.tui import NfSpliceApp

SNAPSHOTS = Path(__file__).parent / "snapshots" / "tui"


async def settle(app: NfSpliceApp, pilot: object) -> None:
    """Wait for service workers and the resulting re-render."""
    await app.workers.wait_for_complete()
    await pilot.pause()  # type: ignore[attr-defined]
    await pilot.pause()  # type: ignore[attr-defined]


async def press(app: NfSpliceApp, pilot: object, selector: str) -> None:
    """Press a button as a user would and wait for its action."""
    app.query_one(selector, Button).press()
    await settle(app, pilot)


def screen_text(app: NfSpliceApp) -> str:
    """Deterministic text rendering of the rail and the current step."""
    lines = [str(label.render()) for label in app.query("#rail Label")]
    lines.append(f"== {app.current}")
    view = app.current_view()
    assert view is not None
    for widget in view.query("*"):
        if isinstance(widget, DataTable):
            for index in range(widget.row_count):
                lines.append(" | ".join(str(cell) for cell in widget.get_row_at(index)))
        elif isinstance(widget, Input):
            lines.append(f"[{widget.placeholder}] {widget.value}")
        elif isinstance(widget, Select):
            value = "" if widget.value is Select.BLANK else widget.value
            lines.append(f"<{widget.id}> {value}")
        elif isinstance(widget, Switch):
            lines.append(f"({widget.id}) {widget.value}")
        elif isinstance(widget, Button):
            lines.append(f"<button {widget.label}>")
        elif isinstance(widget, Label | Static):
            lines.append(str(widget.render()))
    text = "\n".join(lines)
    text = "\n".join(line.rstrip() for line in text.splitlines()).rstrip("\n") + "\n"
    text = re.sub(r"/[^\s'\"]*/(repo|cli|tui)\b", r"<\1>", text)
    return re.sub(r"\b[0-9a-f]{12,64}\b", "<hash>", text)


def check_snapshot(name: str, text: str) -> None:
    """Compare with a reviewed, committed snapshot (update explicitly)."""
    path = SNAPSHOTS / f"{name}.txt"
    if os.environ.get("NF_SPLICE_UPDATE_SNAPSHOTS") == "1":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    assert path.is_file(), f"missing reviewed snapshot {path}"
    assert text == path.read_text(encoding="utf-8"), name
