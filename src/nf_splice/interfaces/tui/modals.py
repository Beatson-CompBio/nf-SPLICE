"""Dialogs: long content, confirmations and focused editors.

Long text (diffs, reports, configs, source files) always opens here, in a
bounded, searchable viewer, never in a page's flow. Focus returns to the
widget that opened a dialog when it closes (Textual restores it).
"""

from __future__ import annotations

import os
import shlex
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Checkbox,
    DataTable,
    Input,
    Label,
    Markdown,
    OptionList,
    Select,
    Static,
    TextArea,
)

from nf_splice.interfaces.tui.themes import PALETTES
from nf_splice.interfaces.tui.widgets import plain

#: Largest text a viewer loads; beyond it the viewer says where the rest is.
MAX_VIEW = 2_000_000


def open_in_editor(app: Any, path: Path) -> str:
    """Open a file in $VISUAL/$EDITOR, suspending the interface."""
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if not editor:
        return f"Set $VISUAL or $EDITOR to open files from here; the file is {path}"
    with app.suspend():
        subprocess.run([*shlex.split(editor), str(path)], check=False)
    return f"Edited {path.name}; reloading the drafts."


class Dialog(ModalScreen[Any]):
    """Base dialog: Escape closes, the title is a heading."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "close", "Close")]
    DIALOG_ID = "dialog"

    def action_close(self) -> None:
        self.dismiss(None)


class HelpDialog(Dialog):
    """F1: what this step asks, what it produces and one example."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape,f1", "close", "Close")]

    def __init__(self, title: str, text: str) -> None:
        super().__init__()
        self._title = title
        self._text = text

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Static(plain(self._title), classes="dialog-title")
            with VerticalScroll(classes="dialog-body"):
                yield Markdown(self._text)
            with Horizontal(classes="dialog-actions"):
                yield Button("Close", id="dialog-close", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self.dismiss(None)


class ViewerDialog(Dialog):
    """Searchable read-only text, with copy-path and open-in-editor."""

    def __init__(
        self,
        title: str,
        text: str,
        *,
        path: Path | None = None,
        language: str | None = None,
    ) -> None:
        super().__init__()
        self._title = title
        if len(text) > MAX_VIEW:
            text = (
                text[:MAX_VIEW]
                + f"\n… truncated; the full text is in {path or 'the source'}"
            )
        self._text = text
        self._path = path
        self._language = language

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog dialog-wide"):
            yield Static(plain(self._title), classes="dialog-title")
            with Horizontal(classes="row"):
                yield Input(placeholder="Search…", id="viewer-search")
                yield Button("Find next", id="viewer-next", classes="compact")
            yield Static("", id="viewer-found", classes="muted")
            area = TextArea(
                self._text,
                read_only=True,
                id="viewer-text",
                soft_wrap=True,
                show_line_numbers=True,
            )
            if self._language:
                try:
                    area.language = self._language
                except Exception:  # an unavailable grammar: show plain text
                    pass
            yield area
            with Horizontal(classes="dialog-actions"):
                if self._path is not None:
                    yield Button("Copy path", id="viewer-copy")
                    yield Button("Open in editor", id="viewer-edit")
                yield Button("Close", id="dialog-close", variant="primary")

    def _find(self, start_after: bool) -> None:
        needle = self.query_one("#viewer-search", Input).value
        area = self.query_one("#viewer-text", TextArea)
        found = self.query_one("#viewer-found", Static)
        if not needle:
            found.update("")
            return
        lines = self._text.splitlines()
        row, column = area.cursor_location
        order = list(range(row, len(lines))) + list(range(0, row))
        for index in order:
            line = lines[index].lower()
            begin = column + 1 if start_after and index == row else 0
            position = line.find(needle.lower(), begin)
            if position >= 0:
                area.move_cursor((index, position))
                area.select_line(index)
                area.scroll_cursor_visible()
                found.update(plain(f"Line {index + 1}"))
                return
        found.update(plain("Not found"))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self._find(start_after=False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "viewer-next":
            self._find(start_after=True)
        elif event.button.id == "viewer-copy" and self._path is not None:
            self.app.copy_to_clipboard(str(self._path))
            self.notify(f"Copied {self._path}")
        elif event.button.id == "viewer-edit" and self._path is not None:
            message = open_in_editor(self.app, self._path)
            self.dismiss("edited")
            self.app.notify(message)
        else:
            self.dismiss(None)


class ConfirmDialog(Dialog):
    """An explicit decision with the exact consequence stated."""

    def __init__(
        self,
        title: str,
        consequence: str,
        *,
        confirm: str,
        cancel: str = "Cancel",
        danger: bool = False,
        reason: str | None = None,
    ) -> None:
        super().__init__()
        self._title = title
        self._consequence = consequence
        self._confirm = confirm
        self._cancel = cancel
        self._danger = danger
        self._reason = reason

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Static(plain(self._title), classes="dialog-title")
            yield Static(plain(self._consequence), classes="dialog-text")
            if self._reason is not None:
                yield Input(placeholder=self._reason, id="confirm-reason")
            with Horizontal(classes="dialog-actions"):
                yield Button(self._cancel, id="confirm-cancel")
                yield Button(
                    self._confirm,
                    id="confirm-ok",
                    variant="error" if self._danger else "primary",
                )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id != "confirm-ok":
            self.dismiss(None)
            return
        if self._reason is not None:
            text = self.query_one("#confirm-reason", Input).value.strip()
            if not text:
                self.notify("Give a reason first.", severity="warning")
                return
            self.dismiss(text)
            return
        self.dismiss(True)


class ThemeDialog(Dialog):
    """Choose one of the six curated themes (also in Ctrl+P)."""

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Static("Theme", classes="dialog-title")
            yield Static(
                "Every view, the AI assistant and the footer use the chosen "
                "theme. It is saved for you, outside any repository.",
                classes="dialog-text",
            )
            options = OptionList(*(item.title for item in PALETTES), id="theme-list")
            current = self.app.theme
            for index, item in enumerate(PALETTES):
                if item.name == current:
                    options.highlighted = index
            yield options
            with Horizontal(classes="dialog-actions"):
                yield Button("Close", id="dialog-close")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        self.dismiss(PALETTES[event.option_index].name)

    def on_option_list_option_highlighted(
        self, event: OptionList.OptionHighlighted
    ) -> None:
        self.app.theme = PALETTES[event.option_index].name

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self.dismiss(self.app.theme)


class QuitDialog(Dialog):
    """Leaving while the agent works: pause safely first, never orphan it."""

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Static("The agent is still working", classes="dialog-title")
            yield Static(
                "Quitting now would leave its work unfinished. Pause safely and "
                "quit asks it to stop at the next safe checkpoint, waits, and "
                "keeps the session paused so you can resume it later.",
                classes="dialog-text",
            )
            with Horizontal(classes="dialog-actions"):
                yield Button("Keep working", id="quit-stay")
                yield Button(
                    "Pause safely and quit", id="quit-pause", variant="primary"
                )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self.dismiss(event.button.id == "quit-pause")


class ListDialog(Dialog):
    """A searchable list with a detail line (drafts, sources, routes)."""

    def __init__(
        self,
        title: str,
        intro: str,
        columns: Sequence[str],
        rows: Sequence[Sequence[str]],
        *,
        actions: Sequence[tuple[str, str]] = (),
        details: Sequence[str] | None = None,
    ) -> None:
        super().__init__()
        self._title = title
        self._intro = intro
        self._columns = columns
        self._rows = [tuple(str(cell) for cell in row) for row in rows]
        self._actions = actions
        self._details = list(details) if details is not None else None

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog dialog-wide"):
            yield Static(plain(self._title), classes="dialog-title")
            yield Static(plain(self._intro), classes="dialog-text")
            yield Input(placeholder="Filter…", id="list-filter")
            table: DataTable[Any] = DataTable(id="list-table", cursor_type="row")
            yield table
            yield Static("", id="list-detail", classes="detail")
            with Horizontal(classes="dialog-actions"):
                for action_id, label in self._actions:
                    yield Button(label, id=f"list-{action_id}")
                yield Button("Close", id="dialog-close", variant="primary")

    def on_mount(self) -> None:
        table = self.query_one("#list-table", DataTable)
        table.add_columns(*self._columns)
        self._fill("")

    def _fill(self, text: str) -> None:
        table = self.query_one("#list-table", DataTable)
        table.clear()
        needle = text.lower()
        for index, row in enumerate(self._rows):
            if not needle or any(needle in cell.lower() for cell in row):
                table.add_row(*row, key=str(index))

    def selected(self) -> int | None:
        table = self.query_one("#list-table", DataTable)
        if not table.row_count:
            return None
        key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        return int(key) if key is not None else None

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "list-filter":
            self._fill(event.value)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        index = self.selected()
        if self._details is not None and index is not None:
            self.query_one("#list-detail", Static).update(plain(self._details[index]))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        identifier = event.button.id or ""
        if identifier.startswith("list-"):
            self.dismiss((identifier.removeprefix("list-"), self.selected()))
        else:
            self.dismiss(None)


class AccessDialog(Dialog):
    """Bulk access policy: who may supply the selected parameters."""

    def __init__(self, names: Sequence[str]) -> None:
        super().__init__()
        self._names = list(names)

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Static("Set access for selected parameters", classes="dialog-title")
            shown = ", ".join(self._names[:8]) + (
                f" and {len(self._names) - 8} more" if len(self._names) > 8 else ""
            )
            yield Static(
                plain(
                    f"{len(self._names)} parameter(s): {shown}. Who may supply them "
                    "when a job is submitted? Visibility is presentation only."
                ),
                classes="dialog-text",
            )
            yield Checkbox("User (the person submitting a job)", id="access-user")
            yield Checkbox("Platform (SPLICE itself)", id="access-platform")
            yield Checkbox("Agent (an AI agent acting for a user)", id="access-agent")
            yield Label("Shown as")
            yield Select(
                [
                    ("Keep current visibility", ""),
                    ("Standard", "standard"),
                    ("Advanced", "advanced"),
                    ("Hidden", "hidden"),
                ],
                value="",
                allow_blank=False,
                id="access-visibility",
            )
            with Horizontal(classes="dialog-actions"):
                yield Button("Cancel", id="access-cancel")
                yield Button(
                    f"Stage for {len(self._names)} parameter(s)",
                    id="access-apply",
                    variant="primary",
                )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id != "access-apply":
            self.dismiss(None)
            return
        principals = [
            name
            for name in ("user", "platform", "agent")
            if self.query_one(f"#access-{name}", Checkbox).value
        ]
        visibility = self.query_one("#access-visibility", Select).value
        self.dismiss(
            {
                "editable_by": principals,
                "visibility": str(visibility) if visibility else None,
            }
        )


class FormDialog(Dialog):
    """A short form of labelled inputs and selects; returns the values."""

    def __init__(
        self,
        title: str,
        intro: str,
        fields: Sequence[tuple[str, str, Any]],
        *,
        submit: str = "Save",
        validate: Callable[[dict[str, Any]], str | None] | None = None,
    ) -> None:
        """``fields`` are (name, label, default); a list default is a select."""
        super().__init__()
        self._title = title
        self._intro = intro
        self._fields = fields
        self._submit = submit
        self._validate = validate

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Static(plain(self._title), classes="dialog-title")
            if self._intro:
                yield Static(plain(self._intro), classes="dialog-text")
            with VerticalScroll(classes="dialog-body"):
                for name, label, default in self._fields:
                    yield Label(label, classes="field-label")
                    if isinstance(default, tuple):
                        options, value = default
                        yield Select(
                            [(text, key) for key, text in options],
                            value=value if value is not None else Select.NULL,
                            allow_blank=value is None,
                            id=f"form-{name}",
                        )
                    elif isinstance(default, bool):
                        yield Checkbox(label, value=default, id=f"form-{name}")
                    else:
                        yield Input(str(default or ""), id=f"form-{name}")
            yield Static("", id="form-error", classes="field-error")
            with Horizontal(classes="dialog-actions"):
                yield Button("Cancel", id="form-cancel")
                yield Button(self._submit, id="form-submit", variant="primary")

    def values(self) -> dict[str, Any]:
        found: dict[str, Any] = {}
        for name, _label, _default in self._fields:
            widget = self.query_one(f"#form-{name}")
            if isinstance(widget, Select):
                found[name] = None if widget.value is Select.NULL else widget.value
            elif isinstance(widget, Checkbox):
                found[name] = widget.value
            elif isinstance(widget, Input):
                found[name] = widget.value.strip()
        return found

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id != "form-submit":
            self.dismiss(None)
            return
        values = self.values()
        problem = self._validate(values) if self._validate else None
        if problem:
            self.query_one("#form-error", Static).update(plain(problem))
            return
        self.dismiss(values)
