"""Outputs: author the results SPLICE should expose, one at a time.

A new catalogue starts with no entries (ADR-0068). People add, duplicate,
edit and remove outputs with a two-step form; published routes are browsed
as read-only evidence and never become entries by themselves. Route coverage
is reported separately and affects ingestion readiness, not publication.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, DataTable, Input, Static

from nf_splice.interfaces.tui.model import OutputRow, ReadinessView, WorkspaceModel
from nf_splice.interfaces.tui.navigation import StepState, Target
from nf_splice.interfaces.tui.pages.base import PageView
from nf_splice.interfaces.tui.widgets import Card, IssueList, plain

#: The first version of a new analysis-output document's schema.
FIRST_VERSION = "1.0.0"


class OutputsPage(PageView):
    page_id = "outputs"
    form_layer = "outputs"
    help_text = (
        "**Outputs** are the results people should find in SPLICE after a run. "
        "Describe one meaningful output, then add or duplicate more.\n\n"
        "**Applies to:** *job* = one run of the whole pipeline; *sample* = one "
        "sample's results; *run* = one platform file-level unit.\n\n"
        "**Example:** *Gene counts*, key `gene_counts`, format `tsv`, applies to "
        "one sample, published at `quantification/{sample}/counts.tsv`.\n\n"
        "Published routes you leave out make output coverage incomplete: that "
        "is reported for ingestion readiness and never blocks publication."
    )

    def __init__(self) -> None:
        super().__init__()
        self.rows: tuple[OutputRow, ...] = ()
        self.readiness: ReadinessView | None = None

    def body(self) -> ComposeResult:
        with Card(id="outputs-empty", classes="placeholder"):
            yield Static("▤", classes="placeholder-icon")
            yield Static("No output entries yet", classes="placeholder-title")
            yield Static(
                "Add your first result, for example a MultiQC report or a count "
                "matrix. The form helps with format, scope and published path.",
                classes="muted",
            )
            yield Button("+ Add an output", id="outputs-add-first", variant="primary")
        with Card(title="Output catalogue", id="outputs-catalogue"):
            yield Input(
                placeholder="Search key, title or category…", id="outputs-search"
            )
            with Horizontal(classes="row toolbar"):
                yield Button(
                    "+ Add", id="outputs-add", variant="primary", classes="compact"
                )
                yield Button("Duplicate", id="outputs-duplicate", classes="compact")
                yield Button("Edit", id="outputs-edit", classes="compact")
                yield Button(
                    "Remove", id="outputs-remove", variant="error", classes="compact"
                )
            table: DataTable[Any] = DataTable(id="outputs-table", cursor_type="row")
            yield table
            yield Static("", id="outputs-detail", classes="detail")
        yield Static("", id="outputs-saved", classes="notice good")
        with Horizontal(id="outputs-after-save", classes="row"):
            yield Button("Add another", id="outputs-add-another")
            yield Button("Duplicate this", id="outputs-duplicate-this")
        yield IssueList(id="outputs-issues")
        with Card(title="Analysis-output data version", id="outputs-version-card"):
            yield Static("", id="outputs-version-text")
            with Horizontal(classes="row"):
                yield Button(
                    f"Use {FIRST_VERSION} (first version of this catalogue)",
                    id="outputs-version-first",
                )
                yield Input(
                    placeholder="X.Y.Z", id="outputs-version", restrict=r"[0-9.]*"
                )
                yield Button("Set version", id="outputs-version-set")
        with Card(
            title="Coverage of the pipeline's published routes", id="outputs-coverage"
        ):
            yield Static("", id="outputs-coverage-text")
            with Horizontal(classes="row"):
                yield Button("Browse routes (read-only) ↗", id="outputs-routes")
                yield Button("Open outputs.draft.yaml ↗", id="outputs-yaml")

    def on_mount(self) -> None:
        table = self.query_one("#outputs-table", DataTable)
        table.add_columns(
            "Key",
            "Title",
            "Category",
            "Format",
            "Applies to",
            "Published path",
            "Status",
        )
        self.query_one("#outputs-saved").display = False
        self.query_one("#outputs-after-save").display = False

    # ------------------------------------------------------------ render

    def refresh_page(self, model: WorkspaceModel) -> None:
        self.rows = model.outputs
        self.loaded_sha = model.layer("outputs").sha256
        empty = not self.rows
        self.query_one("#outputs-empty").display = empty
        self.query_one("#outputs-catalogue").display = not empty
        self._fill()
        version = (model.layer("outputs").data.get("contract") or {}).get(
            "schema_version"
        )
        text = (
            f"✓ {version}: the version of this workflow's analysis_output.json "
            "schema. Raise it when that document's shape changes; it is not the "
            "pipeline's release version."
            if version
            else "Needs confirmation: the version of this workflow's "
            "analysis_output.json schema. It is separate from the pipeline "
            f"release ({model.pipeline().get('version') or 'unknown'}). A new "
            f"catalogue usually starts at {FIRST_VERSION}."
        )
        self.query_one("#outputs-version-text", Static).update(plain(text))
        self.query_one("#outputs-version-first").display = not version
        issues = [
            item
            for item in model.layer("outputs").issues
            if item.code != "identity_not_ready" or not model.layer("bundle").ready
        ]
        self.query_one("#outputs-issues", IssueList).show(
            (
                item.severity,
                f"{item.entity + ' ' if item.entity else ''}{item.label}: "
                f"{item.message}",
            )
            for item in issues
        )
        self._coverage()
        self.workspace.request_readiness()

    def show_readiness(self, readiness: ReadinessView) -> None:
        self.readiness = readiness
        self._coverage()

    def _coverage(self) -> None:
        readiness = self.readiness
        widget = self.query_one("#outputs-coverage-text", Static)
        if readiness is None or (self.model and readiness.key != self.model.key):
            widget.update("Assessing which published routes the catalogue covers…")
            return
        coverage = readiness.coverage
        summary = str(coverage.get("summary") or "")
        status = coverage.get("status")
        glyph = {"complete": "✓", "incomplete": "!", "unverified": "?"}.get(
            str(status), "-"
        )
        widget.update(
            plain(
                f"{glyph} {summary[:1].upper() + summary[1:]}.\n"
                "Coverage affects SPLICE ingestion readiness only; a valid, "
                "deliberately limited catalogue can still be published. Browse the "
                "routes to add outputs for them or exclude them with a reason."
            )
        )

    def _fill(self) -> None:
        table = self.query_one("#outputs-table", DataTable)
        selected = self.selected()
        table.clear()
        search = self.query_one("#outputs-search", Input).value.lower().strip()
        for row in self.rows:
            if search and not any(
                search in value.lower() for value in (row.key, row.title, row.category)
            ):
                continue
            table.add_row(
                row.key,
                row.title,
                row.category,
                ", ".join(row.formats),
                ", ".join(row.scopes),
                (row.patterns[0] if row.patterns else "")[:48],
                "✓ Complete" if row.complete else f"! {len(row.problems)} to fix",
                key=row.key or f"#{row.index}",
            )
        if selected and selected in table.rows:
            table.move_cursor(row=table.get_row_index(selected))
        self._detail()

    def selected(self) -> str | None:
        table = self.query_one("#outputs-table", DataTable)
        if not table.row_count:
            return None
        value = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        return str(value) if value is not None else None

    def _row(self, key: str | None) -> OutputRow | None:
        return next(
            (row for row in self.rows if (row.key or f"#{row.index}") == key), None
        )

    def _detail(self) -> None:
        row = self._row(self.selected())
        widget = self.query_one("#outputs-detail", Static)
        if row is None:
            widget.update("")
            return
        lines = [
            f"{row.title or row.key} · {', '.join(row.formats) or '?'} · "
            f"{', '.join(row.scopes) or '?'} · {', '.join(row.entity_types) or '?'}",
            *(f"path: {pattern}" for pattern in row.patterns[:3]),
            *(f"! {problem}" for problem in row.problems[:3]),
        ]
        widget.update(plain("\n".join(lines)))

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table.id == "outputs-table":
            self._detail()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id == "outputs-table":
            self.edit(self.selected())

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "outputs-search":
            self._fill()

    def tag_text(self, model: WorkspaceModel, state: StepState) -> str:
        return f"{len(model.outputs)} DESCRIBED"

    def focus_target(self, target: Target) -> None:
        if target.field == "schema_version":
            self.query_one("#outputs-version", Input).focus()
            return
        if target.field == "coverage":
            self.query_one("#outputs-routes", Button).focus()
            return
        if target.index is not None:
            row = next((item for item in self.rows if item.index == target.index), None)
            if row is not None:
                table = self.query_one("#outputs-table", DataTable)
                key = row.key or f"#{row.index}"
                if key in table.rows:
                    table.move_cursor(row=table.get_row_index(key))
                self.edit(
                    key, step=2 if target.field in {"path_patterns", "scopes"} else 1
                )
                return
        if not self.rows:
            self.query_one("#outputs-add-first", Button).focus()
        else:
            self.query_one("#outputs-table", DataTable).focus()

    def selection_label(self) -> str:
        return self.selected() or ""

    def ai_context(self) -> dict[str, Any]:
        row = self._row(self.selected())
        return {"output": dict(row.data)} if row is not None else {}

    # ------------------------------------------------------------ editing

    def _categories(self) -> list[str]:
        return [row.category for row in self.rows if row.category]

    def edit(
        self, key: str | None, *, step: int = 1, mode: str = "edit", example: str = ""
    ) -> None:
        from nf_splice.interfaces.tui.editors import OutputEditor

        row = self._row(key) if key else None
        if mode != "add" and row is None:
            self.say("Select an output first.", "warn")
            return
        initial: dict[str, Any] = dict(row.data) if row is not None else {}
        if mode == "duplicate":
            initial["title"] = f"{initial.get('title') or initial.get('key')} (copy)"
        editor = OutputEditor(
            initial=initial,
            mode=mode,
            existing_keys=[item.key for item in self.rows],
            categories=self._categories(),
            example=example,
        )

        def done(result: Any) -> None:
            if result:
                self._save(
                    result,
                    mode,
                    row.key if row is not None and mode == "edit" else None,
                )

        self.app.push_screen(editor, done)
        if step == 2 and mode == "edit":
            self.call_after_refresh(lambda: editor._show_step(2))

    def _save(self, output: dict[str, Any], mode: str, original: str | None) -> None:
        from nf_splice.layers.outputs import add_output, update_output

        root = self.workspace.repository
        context = self.workspace.change_context()

        def write() -> Any:
            if mode == "edit" and original is not None:
                changes = {
                    name: value
                    for name, value in output.items()
                    if name != "key" or value != original
                }
                return update_output(root, original, changes, context)
            return add_output(root, output, context)

        def saved(_result: Any) -> None:
            self.query_one("#outputs-saved", Static).update(
                plain(
                    f"✓ Saved {output['title']} ({output['key']}) in outputs.draft.yaml"
                )
            )
            self.query_one("#outputs-saved").display = True
            self.query_one("#outputs-after-save").display = True
            self._last_key = output["key"]
            self.say(f"Saved output {output['key']}", "good")

        self.workspace.write(
            f"Saving output {output['key']}",
            write,
            then=saved,
            page=self,
            layer="outputs",
        )

    def remove_selected(self) -> None:
        key = self.selected()
        row = self._row(key)
        if row is None or not row.key:
            self.say("Select an output first.", "warn")
            return
        from nf_splice.interfaces.tui.modals import ConfirmDialog
        from nf_splice.layers.outputs import remove_output

        def confirmed(result: Any) -> None:
            if not result:
                return
            self.workspace.write(
                f"Removing output {row.key}",
                lambda: remove_output(
                    self.workspace.repository, row.key, self.workspace.change_context()
                ),
                then=lambda _r: self.say(f"Removed output {row.key}", "good"),
                page=self,
                layer="outputs",
            )

        self.app.push_screen(
            ConfirmDialog(
                f"Remove {row.title or row.key}?",
                f"This removes the output '{row.key}' from outputs.draft.yaml. Other "
                "outputs are unchanged; you can add it again later.",
                confirm="Remove output",
                danger=True,
            ),
            confirmed,
        )

    def set_version(self, version: str) -> None:
        import re

        if not re.fullmatch(r"\d+\.\d+\.\d+", version):
            self.say("Enter the version as X.Y.Z, for example 1.0.0.", "warn")
            self.query_one("#outputs-version", Input).focus()
            return
        from nf_splice.layers.outputs import set_contract_version

        self.workspace.write(
            f"Setting the analysis-output data version to {version}",
            lambda: set_contract_version(
                self.workspace.repository, version, self.workspace.change_context()
            ),
            then=lambda _r: self.say(
                f"Analysis-output data version set to {version}", "good"
            ),
            page=self,
            layer="outputs",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button = event.button.id or ""
        actions: dict[str, Callable[[], None]] = {
            "outputs-add-first": lambda: self.edit(None, mode="add"),
            "outputs-add": lambda: self.edit(None, mode="add"),
            "outputs-add-another": lambda: self.edit(None, mode="add"),
            "outputs-duplicate": lambda: self.edit(self.selected(), mode="duplicate"),
            "outputs-duplicate-this": lambda: self.edit(
                getattr(self, "_last_key", self.selected()), mode="duplicate"
            ),
            "outputs-edit": lambda: self.edit(self.selected()),
            "outputs-remove": self.remove_selected,
            "outputs-version-first": lambda: self.set_version(FIRST_VERSION),
            "outputs-version-set": lambda: self.set_version(
                self.query_one("#outputs-version", Input).value.strip()
            ),
            "outputs-routes": self.workspace.browse_routes,
            "outputs-yaml": lambda: self.workspace.open_draft("outputs"),
        }
        if button in actions:
            event.stop()
            actions[button]()
