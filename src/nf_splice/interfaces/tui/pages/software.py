"""Software & containers: declared facts and the gaps worth resolving."""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, Checkbox, DataTable, Input, Select, Static

from nf_splice.interfaces.tui.model import ComponentRow, WorkspaceModel, bounded
from nf_splice.interfaces.tui.navigation import StepState, Target
from nf_splice.interfaces.tui.pages.base import PageView
from nf_splice.interfaces.tui.widgets import Card, IssueList, plain


class SoftwarePage(PageView):
    page_id = "software"
    form_layer = "components"
    help_text = (
        "**Software & containers** lists every module with its tool, version "
        "and container, from the module declarations. Resolve only real gaps.\n\n"
        "A **container reference** (a registry image such as quay.io/…) is not a "
        "**downloadable image file**. Downloading and checksumming an image is a "
        "separate action that needs your network approval; nothing is fetched "
        "when you open this page.\n\n**Example:** a module whose container could "
        "not be resolved shows *Needs review*; choose one of its declared "
        "references or enter a verified one."
    )

    def __init__(self) -> None:
        super().__init__()
        self.rows: tuple[ComponentRow, ...] = ()

    def body(self) -> ComposeResult:
        with Horizontal(classes="stats"):
            yield Static("", id="software-modules", classes="stat")
            yield Static("", id="software-versions", classes="stat")
            yield Static("", id="software-review", classes="stat")
        with Card(title="Module inventory"):
            with Horizontal(classes="row"):
                yield Input(
                    placeholder="Search component, tool or container…",
                    id="software-search",
                )
                yield Select(
                    [("Needs review", "review"), ("All modules", "all")],
                    value="review",
                    allow_blank=False,
                    id="software-filter",
                )
            table: DataTable[Any] = DataTable(id="software-table", cursor_type="row")
            yield table
            yield Static("", id="software-detail", classes="detail")
            with Horizontal(classes="row"):
                yield Button("View module source ↗", id="software-source")
                yield Button("Edit selected…", id="software-edit")
                yield Button(
                    "Add modules missing from the inventory…", id="software-missing"
                )
        yield IssueList(id="software-issues")
        with Card(title="Container policy and image files"):
            yield Static(
                "Source references are not proof of a downloaded, SHA-verified image. "
                "Verification downloads a file and needs your explicit network "
                "approval.",
                classes="muted",
            )
            yield Checkbox(
                "SPLICE ingestion requires a verified downloadable image for every "
                "container",
                id="software-require",
            )
            with Horizontal(classes="row"):
                yield Button("Save container policy", id="software-policy")
                yield Button("Download and verify an image…", id="software-verify")

    def on_mount(self) -> None:
        table = self.query_one("#software-table", DataTable)
        table.add_columns(
            "Component", "Tool", "Declared version", "Container", "Status"
        )

    def refresh_page(self, model: WorkspaceModel) -> None:
        self.rows = model.components
        self.loaded_sha = model.layer("components").sha256
        versions = sum(1 for row in self.rows if row.version)
        review = sum(1 for row in self.rows if row.unresolved)
        self.query_one("#software-modules", Static).update(
            plain(f"{len(self.rows)}\nModule records")
        )
        self.query_one("#software-versions", Static).update(
            plain(f"{versions}\nWith declared versions")
        )
        self.query_one("#software-review", Static).update(
            plain(f"{review}\nNeed review")
        )
        if not review and self.query_one("#software-filter", Select).value == "review":
            self.query_one("#software-filter", Select).value = "all"
        self._fill()
        data = model.layer("components").data
        policy = self.query_one("#software-require", Checkbox)
        if not self.has_unsaved():
            policy.value = bool(data.get("require_downloadable_images"))
        self._policy_loaded = data.get("require_downloadable_images")
        issues = [
            item
            for item in model.layer("components").issues
            if item.code != "identity_not_ready" or not model.layer("bundle").ready
        ]
        self.query_one("#software-issues", IssueList).show(
            (item.severity, item.message) for item in issues
        )
        self.query_one("#software-missing").display = any(
            "inventory" in item.message or item.code == "unlisted_module"
            for item in issues
        )

    def has_unsaved(self) -> bool:
        loaded = getattr(self, "_policy_loaded", None)
        if loaded is None:
            return False
        return bool(loaded) != self.query_one("#software-require", Checkbox).value

    def tag_text(self, model: WorkspaceModel, state: StepState) -> str:
        return (
            "EXACT METADATA ONLY"
            if state is StepState.READY
            else super().tag_text(model, state)
        )

    def _fill(self) -> None:
        table = self.query_one("#software-table", DataTable)
        selected = self.selected()
        table.clear()
        search = self.query_one("#software-search", Input).value.lower().strip()
        only_review = self.query_one("#software-filter", Select).value == "review"
        for row in self.rows:
            if only_review and not row.unresolved:
                continue
            if search and not any(
                search in value.lower()
                for value in (row.id, row.tool, row.container, *row.sources)
            ):
                continue
            table.add_row(
                bounded(row.id, 40),
                row.tool or "?",
                row.version or "?",
                bounded(row.container or "none", 24),
                "! Needs review" if row.unresolved else "✓ Recorded",
                key=str(row.index),
            )
        if selected is not None and str(selected) in table.rows:
            table.move_cursor(row=table.get_row_index(str(selected)))
        self._detail()

    def selected(self) -> int | None:
        table = self.query_one("#software-table", DataTable)
        if not table.row_count:
            return None
        value = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        return int(value) if value is not None else None

    def _row(self) -> ComponentRow | None:
        index = self.selected()
        return next((row for row in self.rows if row.index == index), None)

    def _detail(self) -> None:
        row = self._row()
        widget = self.query_one("#software-detail", Static)
        if row is None:
            widget.update("Select a component to see its declared source fields.")
            return
        lines = [
            f"{row.id} · {row.type or 'module'} · {row.path}",
            f"Tool {row.tool or '?'} {row.version or '(no declared version)'} · "
            f"container {row.container or 'none'}",
            *(f"  {source}" for source in row.sources[:4]),
            *(f"! {item}" for item in row.unresolved[:4]),
        ]
        widget.update(plain("\n".join(lines)))

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table.id == "software-table":
            self._detail()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "software-search":
            self._fill()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "software-filter" and self.model is not None:
            self._fill()

    def focus_target(self, target: Target) -> None:
        if target.index is not None and target.field == "components":
            self.query_one("#software-filter", Select).value = "all"
            self._fill()
            table = self.query_one("#software-table", DataTable)
            if str(target.index) in table.rows:
                table.move_cursor(row=table.get_row_index(str(target.index)))
        self.query_one("#software-table", DataTable).focus()

    def selection_label(self) -> str:
        row = self._row()
        return row.id if row is not None else ""

    # ------------------------------------------------------------ actions

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button = event.button.id or ""
        if button == "software-source":
            event.stop()
            row = self._row()
            if row is None:
                self.say("Select a component first.", "warn")
                return
            path = row.path if row.path.endswith(".nf") else f"{row.path}/main.nf"
            self.workspace.view_file(path)
        elif button == "software-edit":
            event.stop()
            self._edit()
        elif button == "software-missing":
            event.stop()
            self._add_missing()
        elif button == "software-policy":
            event.stop()
            self._save_policy()
        elif button == "software-verify":
            event.stop()
            self._verify()

    def _edit(self) -> None:
        row = self._row()
        if row is None or self.model is None:
            self.say("Select a component first.", "warn")
            return
        from nf_splice.interfaces.tui.modals import FormDialog
        from nf_splice.layers.base import edit_draft, ops_for

        containers = [
            (
                str(item.get("id")),
                f"{item.get('id')}: "
                + ", ".join(
                    f"{runtime}={reference}"
                    for runtime, reference in sorted(
                        (item.get("source_images") or {}).items()
                    )
                )[:70],
            )
            for item in self.model.containers
        ]
        fields = [
            ("tool_name", "Tool name", row.tool),
            ("tool_version", "Declared tool version", row.version),
            (
                "container",
                "Container (one declared in this inventory)",
                (containers, row.container or None),
            ),
        ]

        def done(values: Any) -> None:
            if not values:
                return
            data = self.model.layer("components").data if self.model else {}
            changes: dict[str, Any] = {}
            if values["tool_name"] != row.tool:
                changes[f"/components/{row.index}/tool/name"] = (
                    values["tool_name"] or None
                )
            if values["tool_version"] != row.version:
                changes[f"/components/{row.index}/tool/version"] = (
                    values["tool_version"] or None
                )
            if values["container"] and values["container"] != row.container:
                changes[f"/components/{row.index}/container_id"] = values["container"]
            if not changes:
                self.say("No component changes to save.")
                return
            self.workspace.write(
                f"Saving component {row.id}",
                lambda: edit_draft(
                    self.workspace.repository,
                    "components",
                    ops_for(data, changes),
                    self.workspace.change_context(),
                    action="update_component",
                ),
                then=lambda _r: self.say(
                    f"Saved {row.id}; edit 'unresolved' in the draft once the gap "
                    "is closed.",
                    "good",
                ),
                page=self,
                layer="components",
            )

        self.app.push_screen(
            FormDialog(
                f"Edit {row.id}",
                "Choose an actual declared reference or enter verified values; "
                "nf-SPLICE never invents a preferred container.",
                fields,
            ),
            done,
        )

    def _add_missing(self) -> None:
        from nf_splice.interfaces.tui.modals import ConfirmDialog
        from nf_splice.layers.components import (
            accept_unambiguous_components,
            discover_components,
        )

        def confirmed(result: Any) -> None:
            if not result:
                return

            def write() -> Any:
                discover_components(self.workspace.repository)
                return accept_unambiguous_components(
                    self.workspace.repository, self.workspace.change_context()
                )

            self.workspace.write(
                "Adding modules missing from the inventory",
                write,
                then=lambda _r: self.say(
                    "Added the unambiguous missing modules.", "good"
                ),
                page=self,
                layer="components",
            )

        self.app.push_screen(
            ConfirmDialog(
                "Add modules missing from the inventory?",
                "nf-SPLICE reads modules.json and the module sources again and adds "
                "each module whose tool, version and container are declared "
                "unambiguously. Ambiguous ones stay listed as issues for you; "
                "existing entries are not changed.",
                confirm="Add modules",
            ),
            confirmed,
        )

    def _save_policy(self) -> None:
        from nf_splice.layers.components import set_image_policy

        required = self.query_one("#software-require", Checkbox).value
        self.workspace.write(
            "Saving the container policy",
            lambda: set_image_policy(
                self.workspace.repository, required, self.workspace.change_context()
            ),
            then=lambda _r: self.say("Saved the container policy.", "good"),
            page=self,
            layer="components",
        )

    def _verify(self) -> None:
        if self.model is None or not self.model.containers:
            self.say("No containers are declared.", "warn")
            return
        from nf_splice.interfaces.tui.modals import FormDialog
        from nf_splice.layers.components import verify_distribution

        options = [
            (str(item.get("id")), str(item.get("id"))) for item in self.model.containers
        ]

        def check(values: dict[str, Any]) -> str | None:
            if not values.get("approve"):
                return "Tick the approval: this downloads a file over the network."
            if not str(values.get("url") or "").startswith("https://"):
                return "Give the https:// address of the image file."
            return None

        def done(values: Any) -> None:
            if not values:
                return
            self.workspace.write(
                f"Downloading and verifying {values['container']}",
                lambda: verify_distribution(
                    self.workspace.repository,
                    values["container"],
                    values["url"],
                    self.workspace.change_context(),
                ),
                then=lambda _r: self.say(
                    "Downloaded, checksummed and recorded the image file.", "good"
                ),
                page=self,
                layer="components",
            )

        self.app.push_screen(
            FormDialog(
                "Download and verify an image file",
                "nf-SPLICE downloads the file, checks it is an image for this "
                "container's sources and records its SHA-256. This uses the network.",
                [
                    ("container", "Container", (options, options[0][0])),
                    ("url", "https:// address of the image file", ""),
                    ("approve", "I approve downloading this file now", False),
                ],
                submit="Download and verify",
                validate=check,
            ),
            done,
        )
