"""Parameter access policies: one table, keyboard toggles, explicit save."""

from __future__ import annotations

import json
from typing import Any, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal
from textual.widgets import Button, DataTable, Static

from nf_splice.domain.access import Principal
from nf_splice.interfaces.tui.screens._common import issue_lines
from nf_splice.interfaces.tui.state import WizardSnapshot
from nf_splice.interfaces.tui.widgets import FilePanel, StepView
from nf_splice.layers.base import read_layer
from nf_splice.layers.inputs import import_inputs, iter_parameters, set_access
from nf_splice.services.input_policy import form_fields
from nf_splice.services.lifecycle import validate_layer

_VISIBILITY = ("standard", "advanced", "hidden")


class InputsView(StepView):
    step_id = "inputs"
    explanation = (
        "Every parameter stays in the contract. Toggle who may change it: "
        "u = user, p = platform, g = agent; v cycles visibility (presentation "
        "only, never permission). Staged changes are written only on Save."
    )
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("u", "grant('user')", "User"),
        Binding("p", "grant('platform')", "Platform"),
        Binding("g", "grant('agent')", "Agent"),
        Binding("v", "visibility", "Visibility"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.staged: dict[str, tuple[list[str], str | None]] = {}
        self.current: dict[str, tuple[list[str] | None, str | None]] = {}

    def compose(self) -> ComposeResult:
        yield FilePanel("inputs")
        yield DataTable(id="inputs-table")
        with Horizontal(classes="row"):
            yield Button("Save policies", id="inputs-save", variant="primary")
            yield Button("Import nextflow_schema.json", id="inputs-import")
        yield Static("", id="inputs-preview", classes="section")
        yield Static("", id="inputs-issues", classes="issues")

    def setup(self) -> None:
        table = self.query_one("#inputs-table", DataTable)
        table.add_columns(
            "parameter", "group", "type", "default", "editable by", "visibility", ""
        )
        table.cursor_type = "row"

    def refresh_view(self, snapshot: WizardSnapshot) -> None:
        state = read_layer(snapshot.repository, "inputs")
        table = self.query_one("#inputs-table", DataTable)
        table.clear()
        self.current = {}
        if state.draft is None or not isinstance(state.draft.data, dict):
            self.query_one("#inputs-issues", Static).update(
                issue_lines(snapshot.repository, "inputs")
            )
            return
        for parameter in iter_parameters(state.draft.data):
            visibility = (parameter.schema.get("x-splice-ui") or {}).get("visibility")
            policy = parameter.editable_by
            self.current[parameter.name] = (
                list(policy) if policy is not None else None,
                visibility,
            )
            staged = self.staged.get(parameter.name)
            shown_policy = staged[0] if staged else policy
            shown_visibility = staged[1] if staged else visibility
            table.add_row(
                parameter.name,
                parameter.group or "(root)",
                json.dumps(parameter.schema.get("type")),
                json.dumps(parameter.schema.get("default"))
                if "default" in parameter.schema
                else "",
                ",".join(shown_policy) if shown_policy is not None else "UNREVIEWED",
                shown_visibility
                or ("hidden" if parameter.schema.get("hidden") else "standard"),
                "*" if staged else "",
                key=parameter.name,
            )
        validation = validate_layer(snapshot.repository, "inputs")
        preview = validation.files.get("inputs.schema.json")
        if preview is not None:
            schema = json.loads(preview)
            fields = form_fields(schema, Principal.USER)
            self.query_one("#inputs-preview", Static).update(
                "User form preview: "
                + ", ".join(
                    f"{item.name}{'' if item.editable else ' (read-only)'}"
                    for item in fields
                )
            )
        self.query_one("#inputs-issues", Static).update(
            issue_lines(snapshot.repository, "inputs")
        )

    def _selected(self) -> str | None:
        table = self.query_one("#inputs-table", DataTable)
        if not table.row_count:
            return None
        value = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        return str(value) if value is not None else None

    def action_grant(self, principal: str) -> None:
        name = self._selected()
        if name is None:
            return
        policy, visibility = self.staged.get(name) or (
            list(self.current[name][0] or []),
            self.current[name][1],
        )
        updated = sorted(set(policy) ^ {principal})
        self.staged[name] = (updated, visibility)
        self._redraw_row(name)

    def action_visibility(self) -> None:
        name = self._selected()
        if name is None:
            return
        policy, visibility = self.staged.get(name) or (
            list(self.current[name][0] or []),
            self.current[name][1],
        )
        index = _VISIBILITY.index(visibility) if visibility in _VISIBILITY else 0
        self.staged[name] = (policy, _VISIBILITY[(index + 1) % len(_VISIBILITY)])
        self._redraw_row(name)

    def _redraw_row(self, name: str) -> None:
        table = self.query_one("#inputs-table", DataTable)
        policy, visibility = self.staged[name]
        table.update_cell(
            name, table.ordered_columns[4].key, ",".join(policy) or "nobody"
        )
        table.update_cell(name, table.ordered_columns[5].key, visibility or "standard")
        table.update_cell(name, table.ordered_columns[6].key, "*")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        app = self.wizard
        if event.button.id == "inputs-import":
            event.stop()
            app.perform("Importing parameters", lambda: import_inputs(app.repository))
        elif event.button.id == "inputs-save":
            event.stop()
            staged = dict(self.staged)
            if not staged:
                app.set_status("No staged policy changes.")
                return

            def save() -> Any:
                for name, (policy, visibility) in sorted(staged.items()):
                    set_access(
                        app.repository,
                        [name],
                        policy,
                        app.change_context(),
                        visibility=visibility,
                    )

            def cleared(_result: Any) -> None:
                self.staged.clear()
                self.refresh_view(app.snapshot)

            app.perform("Saving parameter policies", save, then=cleared)

    def unsaved(self) -> dict[str, str]:
        return {name: json.dumps(value) for name, value in self.staged.items()}

    def restore(self, values: dict[str, str]) -> None:
        for name, encoded in values.items():
            policy, visibility = json.loads(encoded)
            self.staged[name] = (list(policy), visibility)
        if values:
            self.refresh_view(self.wizard.snapshot)
