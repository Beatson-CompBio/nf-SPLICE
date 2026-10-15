"""All drafts, external edits and per-field issues."""

from __future__ import annotations

import os
import shlex
import subprocess

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, DataTable, Static

from nf_splice.interfaces.tui.screens._common import issue_lines
from nf_splice.interfaces.tui.state import WizardSnapshot, changed_files
from nf_splice.interfaces.tui.widgets import StepView


class DraftsView(StepView):
    step_id = "drafts"
    explanation = (
        "Drafts are the editable source of truth. Edit them in any editor; the "
        "wizard re-reads them (Ctrl+R) and never overwrites your edits."
    )

    def compose(self) -> ComposeResult:
        yield DataTable(id="drafts-table")
        with Horizontal(classes="row"):
            yield Button("Reload from disk", id="drafts-reload")
            yield Button("Open selected in $EDITOR", id="drafts-edit")
        yield Static("", id="drafts-changed", classes="section")
        yield Static("", id="drafts-issues", classes="issues")

    def setup(self) -> None:
        table = self.query_one("#drafts-table", DataTable)
        table.add_columns("layer", "draft", "state", "errors", "warnings")
        table.cursor_type = "row"

    def refresh_view(self, snapshot: WizardSnapshot) -> None:
        table = self.query_one("#drafts-table", DataTable)
        table.clear()
        if snapshot.status is None:
            return
        for item in snapshot.status.artifacts:
            table.add_row(
                item.layer,
                item.draft,
                item.state.value,
                item.errors,
                item.warnings,
                key=item.layer,
            )
        changed = changed_files(self.wizard.session, snapshot)
        self.query_one("#drafts-changed", Static).update(
            "Changed outside this session: " + ", ".join(changed) if changed else ""
        )
        self._issues()

    def on_data_table_row_highlighted(self, _event: DataTable.RowHighlighted) -> None:
        self._issues()

    def _selected(self) -> str | None:
        table = self.query_one("#drafts-table", DataTable)
        if not table.row_count:
            return None
        return str(table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value)

    def _issues(self) -> None:
        layer = self._selected()
        if layer is not None:
            self.query_one("#drafts-issues", Static).update(
                issue_lines(self.wizard.repository, layer)
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        app = self.wizard
        if event.button.id == "drafts-reload":
            event.stop()
            app.action_reload()
        elif event.button.id == "drafts-edit":
            event.stop()
            editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
            layer = self._selected()
            status = app.snapshot.status
            if not editor or layer is None or status is None:
                app.set_status(
                    "Set $EDITOR to edit drafts from the wizard.", error=True
                )
                return
            path = app.repository / next(
                item.draft for item in status.artifacts if item.layer == layer
            )
            with app.suspend():
                subprocess.run([*shlex.split(editor), str(path)], check=False)
            app.action_reload()
