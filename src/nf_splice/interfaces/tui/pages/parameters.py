"""Parameters: who may supply each value when a job is submitted.

Imported ``nextflow_schema.json`` parameters keep their fail-closed policy
(``editable_by: []``) until a person assigns access. Required values that
nobody may supply are shown as submission blockers with a fix. Access is
never granted implicitly; bulk changes are previewed and staged first.
"""

from __future__ import annotations

from typing import Any, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Input, Select, Static

from nf_splice.interfaces.tui.model import ParameterRow, WorkspaceModel
from nf_splice.interfaces.tui.navigation import StepState, Target
from nf_splice.interfaces.tui.pages.base import PageView
from nf_splice.interfaces.tui.widgets import Card, IssueList, plain

_VISIBILITY = ("standard", "advanced", "hidden")
FILTERS = (
    ("Needs a decision", "needs"),
    ("Required only", "required"),
    ("All parameters", "all"),
)


def _tick(value: bool) -> str:
    return "[x]" if value else "[ ]"


class ParametersPage(PageView):
    page_id = "parameters"
    form_layer = "inputs"
    help_text = (
        "**Parameters** come from nextflow_schema.json. For each, decide who "
        "may supply it when a job is submitted: a **user**, the **platform** "
        "(SPLICE itself) or an **agent**. Visibility (standard, advanced, "
        "hidden) is presentation only, never permission.\n\n**Keys:** u, p, g "
        "toggle user, platform and agent; v cycles visibility; space selects a "
        "row for bulk changes. Changes are staged until Save policies.\n\n"
        "**Example:** `input` (the sample sheet) is usually supplied by the "
        "user; `outdir` by the platform."
    )
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("u", "grant('user')", "User", show=False),
        Binding("p", "grant('platform')", "Platform", show=False),
        Binding("g", "grant('agent')", "Agent", show=False),
        Binding("v", "visibility", "Visibility", show=False),
        Binding("space", "mark", "Select row", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.staged: dict[str, tuple[tuple[str, ...], str]] = {}
        self.marked: set[str] = set()
        self.rows: dict[str, ParameterRow] = {}

    def body(self) -> ComposeResult:
        with Card(title="Submission blockers", id="parameter-blockers"):
            yield Static("", id="parameter-blocker-text")
            yield Vertical(id="parameter-blocker-actions")
        with Card(title="Access policies"):
            with Horizontal(classes="row"):
                yield Input(
                    placeholder="Search name or description…", id="parameter-search"
                )
                yield Select(
                    [(label, value) for label, value in FILTERS],
                    value="needs",
                    allow_blank=False,
                    id="parameter-filter",
                )
                yield Select(
                    [("All groups", "")],
                    value="",
                    allow_blank=False,
                    id="parameter-group",
                )
            yield Static("", id="parameter-counts", classes="muted")
            table: DataTable[Any] = DataTable(id="parameter-table", cursor_type="row")
            yield table
            yield Static("", id="parameter-detail", classes="detail")
            yield IssueList(id="parameter-issues")
        with Horizontal(classes="page-actions"):
            yield Button("Select visible", id="parameter-select-visible")
            yield Button("Clear selection", id="parameter-clear")
            yield Button("Set access for selected…", id="parameter-bulk")
            yield Button("Discard staged changes", id="parameter-discard")
            yield Button("Save policies", id="parameter-save", variant="primary")

    def on_mount(self) -> None:
        table = self.query_one("#parameter-table", DataTable)
        table.add_columns(
            "Sel",
            "Parameter",
            "Group",
            "Required",
            "Default",
            "User",
            "Platform",
            "Agent",
            "Shown",
            "",
        )

    # ------------------------------------------------------------ rows

    def _policy(self, row: ParameterRow) -> tuple[tuple[str, ...], str]:
        return self.staged.get(row.name, (row.editable_by, row.visibility))

    def _visible_rows(self) -> list[ParameterRow]:
        search = self.query_one("#parameter-search", Input).value.lower().strip()
        mode = self.query_one("#parameter-filter", Select).value
        group = self.query_one("#parameter-group", Select).value
        blocked = {
            item.name for item in (self.model.submission_blockers if self.model else ())
        }
        found = []
        for row in self.rows.values():
            access, _visibility = self._policy(row)
            if group and row.group != group:
                continue
            if mode == "required" and not row.required:
                continue
            if mode == "needs" and not (
                row.name in blocked or (row.required and not access)
            ):
                continue
            if (
                search
                and search not in row.name.lower()
                and search not in row.description.lower()
            ):
                continue
            found.append(row)
        return found

    def _cells(self, row: ParameterRow) -> tuple[str, ...]:
        access, visibility = self._policy(row)
        return (
            "●" if row.name in self.marked else "",
            row.name,
            row.group_title,
            "✓" if row.required else "",
            row.default,
            _tick("user" in access),
            _tick("platform" in access),
            _tick("agent" in access),
            visibility,
            "staged" if row.name in self.staged else "",
        )

    def _fill(self) -> None:
        table = self.query_one("#parameter-table", DataTable)
        selected = self._selected()
        table.clear()
        rows = self._visible_rows()
        for row in rows:
            table.add_row(*self._cells(row), key=row.name)
        if selected and selected in table.rows:
            table.move_cursor(row=table.get_row_index(selected))
        total = len(self.rows)
        needing = sum(
            1 for row in self.rows.values() if row.required and not self._policy(row)[0]
        )
        self.query_one("#parameter-counts", Static).update(
            plain(
                f"{total} imported · {len(rows)} shown · {needing} required without "
                f"access · {len(self.staged)} staged change(s) · {len(self.marked)} "
                "selected"
            )
        )
        self._detail()

    def _redraw(self, name: str) -> None:
        table = self.query_one("#parameter-table", DataTable)
        if name not in table.rows:
            return
        for column, value in zip(
            table.ordered_columns, self._cells(self.rows[name]), strict=True
        ):
            table.update_cell(name, column.key, value)

    def _selected(self) -> str | None:
        table = self.query_one("#parameter-table", DataTable)
        if not table.row_count:
            return None
        value = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        return str(value) if value is not None else None

    def _detail(self) -> None:
        name = self._selected()
        row = self.rows.get(name or "")
        widget = self.query_one("#parameter-detail", Static)
        if row is None:
            widget.update("")
            return
        access, visibility = self._policy(row)
        who = ", ".join(access) or "nobody"
        widget.update(
            plain(
                f"{row.name} ({row.type}; default {row.default}): "
                f"{row.description or 'no description'}\n"
                f"Editable by: {who} · shown as {visibility}"
            )
        )

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table.id == "parameter-table":
            self._detail()

    # ------------------------------------------------------------ model

    def refresh_page(self, model: WorkspaceModel) -> None:
        self.rows = {row.name: row for row in model.parameters}
        self.staged = {
            name: value
            for name, value in self.staged.items()
            if name in self.rows
            and value != (self.rows[name].editable_by, self.rows[name].visibility)
        }
        self.marked &= set(self.rows)
        group = self.query_one("#parameter-group", Select)
        current = group.value
        group.set_options(
            [("All groups", ""), *((title, name) for name, title in model.groups)]
        )
        group.value = (
            current if current in {name for name, _title in model.groups} else ""
        )
        self.loaded_sha = model.layer("inputs").sha256
        self._fill()
        self._blockers(model)
        issues = model.layer("inputs").issues
        self.query_one("#parameter-issues", IssueList).show(
            (item.severity, f"{item.entity or item.label}: {item.message}")
            for item in issues
        )

    def _blockers(self, model: WorkspaceModel) -> None:
        card = self.query_one("#parameter-blockers")
        blockers = model.submission_blockers
        card.display = bool(blockers)
        if not blockers:
            return
        lines = []
        for item in blockers[:8]:
            hint = (
                " The platform may legitimately supply an output directory."
                if item.output_directory
                else ""
            )
            lines.append(f"✕ {item.name}: {item.reason}.{hint}")
        if len(blockers) > 8:
            lines.append(f"… and {len(blockers) - 8} more (filter: Needs a decision)")
        self.query_one("#parameter-blocker-text", Static).update(
            plain(
                "A job cannot be submitted until someone may supply these:\n"
                + "\n".join(lines)
            )
        )
        holder = self.query_one("#parameter-blocker-actions", Vertical)
        holder.remove_children()
        row = Horizontal(classes="row")
        holder.mount(row)
        for item in blockers[:4]:
            row.mount(
                Button(
                    f"Fix {item.name} →",
                    name=f"parameter-fix-{item.name}",
                    classes="compact",
                )
            )

    def tag_text(self, model: WorkspaceModel, state: StepState) -> str:
        attention = len(model.submission_blockers) + len(model.layer("inputs").errors)
        text = f"{len(model.parameters)} IMPORTED"
        return text + (f" · {attention} NEED ATTENTION" if attention else "")

    def has_unsaved(self) -> bool:
        return bool(self.staged)

    def focus_target(self, target: Target) -> None:
        if target.entry and target.entry in self.rows:
            self.query_one("#parameter-filter", Select).value = "all"
            self.query_one("#parameter-group", Select).value = ""
            self.query_one("#parameter-search", Input).value = ""
            self._fill()
            table = self.query_one("#parameter-table", DataTable)
            if target.entry in table.rows:
                table.move_cursor(row=table.get_row_index(target.entry))
        self.query_one("#parameter-table", DataTable).focus()

    def selection_label(self) -> str:
        return self._selected() or ""

    # ------------------------------------------------------------ editing

    def _stage(self, name: str, access: tuple[str, ...], visibility: str) -> None:
        row = self.rows[name]
        if (access, visibility) == (row.editable_by, row.visibility):
            self.staged.pop(name, None)
        else:
            self.staged[name] = (access, visibility)
        self._redraw(name)

    def action_grant(self, principal: str) -> None:
        name = self._selected()
        if name is None:
            return
        access, visibility = self._policy(self.rows[name])
        updated = tuple(sorted(set(access) ^ {principal}))
        self._stage(name, updated, visibility)
        self._detail()

    def action_visibility(self) -> None:
        name = self._selected()
        if name is None:
            return
        access, visibility = self._policy(self.rows[name])
        index = _VISIBILITY.index(visibility) if visibility in _VISIBILITY else 0
        self._stage(name, access, _VISIBILITY[(index + 1) % len(_VISIBILITY)])
        self._detail()

    def action_mark(self) -> None:
        name = self._selected()
        if name is None:
            return
        self.marked.symmetric_difference_update({name})
        self._redraw(name)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "parameter-search":
            self._fill()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id in {"parameter-filter", "parameter-group"} and self.rows:
            self._fill()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button = event.button.name or event.button.id or ""
        if button.startswith("parameter-fix-"):
            event.stop()
            self.focus_target(
                Target("parameters", entry=button.removeprefix("parameter-fix-"))
            )
            self.say("Press u, p or g to say who may supply it, then Save policies.")
        elif button == "parameter-select-visible":
            event.stop()
            self.marked.update(row.name for row in self._visible_rows())
            self._fill()
        elif button == "parameter-clear":
            event.stop()
            self.marked.clear()
            self._fill()
        elif button == "parameter-discard":
            event.stop()
            self.staged.clear()
            self._fill()
        elif button == "parameter-bulk":
            event.stop()
            self._bulk()
        elif button == "parameter-save":
            event.stop()
            self.save()

    def _bulk(self) -> None:
        names = sorted(self.marked)
        if not names:
            self.say("Select rows first (space, or Select visible).", "warn")
            return
        from nf_splice.interfaces.tui.modals import AccessDialog

        def chosen(result: Any) -> None:
            if not result:
                return
            for name in names:
                _access, visibility = self._policy(self.rows[name])
                self._stage(
                    name,
                    tuple(sorted(result["editable_by"])),
                    result["visibility"] or visibility,
                )
            self._fill()
            self.say(
                f"Staged access for {len(names)} parameter(s); Save policies to "
                "write them."
            )

        self.app.push_screen(AccessDialog(names), chosen)

    def save(self) -> None:
        staged = dict(self.staged)
        if not staged:
            self.say("No staged policy changes.")
            return
        from nf_splice.layers.inputs import set_access

        root = self.workspace.repository
        context = self.workspace.change_context()

        def write() -> None:
            grouped: dict[tuple[tuple[str, ...], str], list[str]] = {}
            for name, value in sorted(staged.items()):
                grouped.setdefault(value, []).append(name)
            for (access, visibility), names in grouped.items():
                set_access(root, names, list(access), context, visibility=visibility)

        def saved(_result: Any) -> None:
            self.staged.clear()
            self.say(
                f"Saved {len(staged)} access policy change(s) in "
                ".splice-local/drafts/inputs.draft.yaml",
                "good",
            )

        self.workspace.write(
            "Saving parameter policies", write, then=saved, page=self, layer="inputs"
        )
