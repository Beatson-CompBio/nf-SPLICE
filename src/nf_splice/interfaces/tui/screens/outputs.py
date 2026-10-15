"""Master-detail output candidate review."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal
from textual.suggester import SuggestFromList
from textual.widgets import Button, DataTable, Input, Select, Static

from nf_splice.domain import (
    SUGGESTED_OUTPUT_CATEGORIES,
    SUGGESTED_OUTPUT_STAGES,
    OutputEntityType,
    OutputFormat,
    OutputScope,
    expand_output_path_pattern,
)
from nf_splice.interfaces.tui.screens._common import issue_lines
from nf_splice.interfaces.tui.state import WizardSnapshot
from nf_splice.interfaces.tui.widgets import StepView
from nf_splice.layers.base import load_review_state, read_layer
from nf_splice.layers.outputs import (
    accept_output,
    candidate_evidence,
    discover_outputs,
    merge_outputs,
    pending_candidates,
    preview_outputs,
    reject_output,
    set_contract_version,
    split_output,
)


class OutputsView(StepView):
    step_id = "outputs"
    explanation = (
        "Select a candidate (row keys are stable candidate IDs), complete its "
        "meaning and accept (a), reject (r), mark for merge (space) then merge "
        "(m), or split (s) one pattern per output. Scope: job = whole workflow "
        "execution, sample = one sample, run = one platform file-level run. "
        "Categories and stages are free text."
    )
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("a", "accept", "Accept"),
        Binding("r", "reject", "Reject"),
        Binding("space", "mark", "Mark"),
        Binding("m", "merge", "Merge"),
        Binding("s", "split", "Split"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.marked: list[str] = []
        self.example_paths: list[str] = []

    def compose(self) -> ComposeResult:
        with Horizontal(classes="row"):
            yield Input(
                placeholder="Example output tree directory (optional)",
                id="outputs-tree",
            )
            yield Button("Discover", id="outputs-discover")
        with Horizontal(classes="row"):
            yield Input(
                placeholder="analysis-output schema version X.Y.Z", id="outputs-version"
            )
            yield Button("Set version", id="outputs-set-version")
        yield DataTable(id="outputs-candidates")
        yield Static("", id="outputs-evidence", classes="section")
        yield Input(placeholder="stable key", id="output-key")
        yield Input(placeholder="title", id="output-title")
        yield Input(placeholder="description", id="output-description")
        yield Input(
            placeholder="category (free text)",
            id="output-category",
            suggester=SuggestFromList(SUGGESTED_OUTPUT_CATEGORIES),
        )
        yield Input(
            placeholder="stage (optional free text)",
            id="output-stage",
            suggester=SuggestFromList(SUGGESTED_OUTPUT_STAGES),
        )
        yield Select(
            [(item.value, item.value) for item in OutputFormat],
            prompt="format",
            id="output-format",
        )
        yield Select(
            [(item.value, item.value) for item in OutputScope],
            prompt="scope",
            id="output-scope",
        )
        yield Select(
            [(item.value, item.value) for item in OutputEntityType],
            prompt="entity type",
            id="output-entity",
        )
        yield Input(
            placeholder="anchored path pattern(s), comma separated", id="output-pattern"
        )
        yield Static("", id="outputs-regex", classes="section")
        yield Input(placeholder="reject reason", id="output-reason")
        with Horizontal(classes="row"):
            yield Button("Accept", id="outputs-accept", variant="success")
            yield Button("Reject", id="outputs-reject", variant="error")
            yield Button("Merge marked", id="outputs-merge")
            yield Button("Split patterns", id="outputs-split")
            yield Button("Preview JSON", id="outputs-preview")
        yield Static("", id="outputs-tally", classes="section")
        yield Static("", id="outputs-json", classes="section")
        yield Static("", id="outputs-issues", classes="issues")

    def setup(self) -> None:
        table = self.query_one("#outputs-candidates", DataTable)
        table.add_columns("", "candidate", "suggested key", "pattern", "scope")
        table.cursor_type = "row"

    def refresh_view(self, snapshot: WizardSnapshot) -> None:
        table = self.query_one("#outputs-candidates", DataTable)
        selected = self.selected()
        table.clear()
        candidates = (
            pending_candidates(snapshot.repository)
            if read_layer(snapshot.repository, "outputs").file.exists
            else ()
        )
        self.marked = [
            item for item in self.marked if item in {c.id for c in candidates}
        ]
        for candidate in candidates:
            table.add_row(
                "●" if candidate.id in self.marked else "",
                candidate.id,
                candidate.suggested_key,
                candidate.path_pattern or "",
                candidate.likely_scope.value if candidate.likely_scope else "?",
                key=candidate.id,
            )
        if selected is not None and selected in table.rows:
            table.move_cursor(row=table.get_row_index(selected))
        self.show_candidate()
        state = read_layer(snapshot.repository, "outputs")
        data = (
            state.draft.data
            if state.draft is not None and isinstance(state.draft.data, dict)
            else {}
        )
        version = (data.get("contract") or {}).get("schema_version")
        if version and not self.query_one("#outputs-version", Input).value:
            self.query_one("#outputs-version", Input).value = str(version)
        review = load_review_state(snapshot.repository, "outputs").candidates
        tally: dict[str, int] = {}
        for entry in review.values():
            tally[entry.get("status", "?")] = tally.get(entry.get("status", "?"), 0) + 1
        self.query_one("#outputs-tally", Static).update(
            f"Reviewed outputs in draft: {len(data.get('outputs') or [])}. Candidates: "
            + ", ".join(f"{key}={value}" for key, value in sorted(tally.items()))
        )
        self.query_one("#outputs-issues", Static).update(
            issue_lines(snapshot.repository, "outputs")
        )

    def selected(self) -> str | None:
        table = self.query_one("#outputs-candidates", DataTable)
        if not table.row_count:
            return None
        value = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        return str(value) if value is not None else None

    def on_data_table_row_highlighted(self, _event: DataTable.RowHighlighted) -> None:
        self.show_candidate()

    def show_candidate(self) -> None:
        identifier = self.selected()
        candidate = (
            next(
                (
                    item
                    for item in pending_candidates(self.wizard.repository)
                    if item.id == identifier
                ),
                None,
            )
            if identifier
            else None
        )
        if candidate is None:
            return
        evidence = candidate_evidence(self.wizard.repository, candidate.id)
        self.query_one("#outputs-evidence", Static).update(
            "\n".join(
                f"{item['provenance']['source']}: {item['provenance']['location']} "
                f"(confidence {item['confidence']})"
                for item in evidence
            )
        )
        self.query_one("#output-key", Input).value = candidate.suggested_key
        self.query_one("#output-title", Input).value = candidate.suggested_title or ""
        self.query_one("#output-description", Input).value = (
            candidate.suggested_description or ""
        )
        self.query_one("#output-pattern", Input).value = candidate.path_pattern or ""
        for selector, value in (
            ("#output-format", candidate.suggested_format),
            ("#output-scope", candidate.likely_scope),
            ("#output-entity", candidate.likely_entity_type),
        ):
            select = self.query_one(selector, Select)
            if value is None:
                select.clear()
            else:
                select.value = value.value
        self._regex_preview()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "output-pattern":
            self._regex_preview()

    def _regex_preview(self) -> None:
        patterns = [
            item.strip()
            for item in self.query_one("#output-pattern", Input).value.split(",")
            if item.strip()
        ]
        lines = []
        for pattern in patterns:
            try:
                compiled = re.compile(expand_output_path_pattern(pattern))
            except (re.error, ValueError) as error:
                lines.append(f"{pattern}: invalid ({error})")
                continue
            matches = [path for path in self.example_paths if compiled.match(path)]
            lines.append(
                f"{pattern}: matches {len(matches)} example path(s) {matches[:3]}"
            )
        self.query_one("#outputs-regex", Static).update("\n".join(lines))

    def _value(self, selector: str) -> str:
        value = self.query_one(selector, Select).value
        return "" if value is Select.BLANK else str(value)

    def collected(
        self, patterns: list[str] | None = None, key: str | None = None
    ) -> dict[str, Any]:
        output: dict[str, Any] = {
            "key": key or self.query_one("#output-key", Input).value.strip(),
            "title": self.query_one("#output-title", Input).value.strip(),
            "description": self.query_one("#output-description", Input).value.strip(),
            "category": self.query_one("#output-category", Input).value.strip(),
            "formats": [self._value("#output-format")],
            "scopes": [self._value("#output-scope")],
            "entity_types": [self._value("#output-entity")],
            "path_patterns": patterns
            or [
                item.strip()
                for item in self.query_one("#output-pattern", Input).value.split(",")
                if item.strip()
            ],
        }
        stage = self.query_one("#output-stage", Input).value.strip()
        if stage:
            output["stage"] = stage
        return output

    def action_accept(self) -> None:
        identifier = self.selected()
        if identifier is None:
            return
        app = self.wizard
        output = self.collected()
        app.perform(
            f"Accepting {output['key']}",
            lambda: accept_output(
                app.repository, identifier, output, app.change_context()
            ),
        )

    def action_reject(self) -> None:
        identifier = self.selected()
        reason = self.query_one("#output-reason", Input).value.strip()
        if identifier is None:
            return
        if not reason:
            self.wizard.set_status("Enter a reject reason first.", error=True)
            return
        app = self.wizard
        app.perform(
            "Rejecting candidate",
            lambda: reject_output(
                app.repository, identifier, reason, app.change_context()
            ),
        )

    def action_mark(self) -> None:
        identifier = self.selected()
        if identifier is None:
            return
        if identifier in self.marked:
            self.marked.remove(identifier)
        else:
            self.marked.append(identifier)
        self.query_one("#outputs-candidates", DataTable).update_cell(
            identifier,
            self.query_one("#outputs-candidates", DataTable).ordered_columns[0].key,
            "●" if identifier in self.marked else "",
        )

    def action_merge(self) -> None:
        if len(self.marked) < 2:
            self.wizard.set_status(
                "Mark at least two candidates (space) to merge.", error=True
            )
            return
        app = self.wizard
        marked = list(self.marked)
        output = self.collected()

        def done(_result: Any) -> None:
            self.marked.clear()

        app.perform(
            "Merging candidates",
            lambda: merge_outputs(app.repository, marked, output, app.change_context()),
            then=done,
        )

    def action_split(self) -> None:
        identifier = self.selected()
        patterns = [
            item.strip()
            for item in self.query_one("#output-pattern", Input).value.split(",")
            if item.strip()
        ]
        if identifier is None or len(patterns) < 2:
            self.wizard.set_status(
                "Enter two or more comma-separated patterns to split.", error=True
            )
            return
        base = self.query_one("#output-key", Input).value.strip()
        outputs = [
            self.collected([pattern], key=f"{base}_{index + 1}")
            for index, pattern in enumerate(patterns)
        ]
        app = self.wizard
        app.perform(
            "Splitting candidate",
            lambda: split_output(
                app.repository, identifier, outputs, app.change_context()
            ),
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        app = self.wizard
        handlers = {
            "outputs-accept": self.action_accept,
            "outputs-reject": self.action_reject,
            "outputs-merge": self.action_merge,
            "outputs-split": self.action_split,
        }
        if event.button.id in handlers:
            event.stop()
            handlers[event.button.id]()
        elif event.button.id == "outputs-discover":
            event.stop()
            text = self.query_one("#outputs-tree", Input).value.strip()
            tree = Path(text).expanduser() if text else None
            if tree is not None and tree.is_dir():
                self.example_paths = sorted(
                    path.relative_to(tree).as_posix()
                    for path in tree.rglob("*")
                    if path.is_file()
                )
            app.perform(
                "Discovering outputs",
                lambda: discover_outputs(app.repository, example_output_tree=tree),
            )
        elif event.button.id == "outputs-set-version":
            event.stop()
            version = self.query_one("#outputs-version", Input).value.strip()
            app.perform(
                "Setting contract version",
                lambda: set_contract_version(
                    app.repository, version, app.change_context()
                ),
            )
        elif event.button.id == "outputs-preview":
            event.stop()
            try:
                text = preview_outputs(app.repository, "json")
            except ValueError as error:
                app.set_status(str(error), error=True)
                return
            self.query_one("#outputs-json", Static).update(text[:4000])
