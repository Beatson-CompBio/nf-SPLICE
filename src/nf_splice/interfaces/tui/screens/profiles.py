"""Execution profiles: metadata in the YAML, configuration in native files."""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, DataTable, Input, Select, Static

from nf_splice.domain.execution import (
    ContainerEngine,
    ExecutionExecutor,
    ExecutionProfileType,
)
from nf_splice.drafts import read_file
from nf_splice.interfaces.tui.screens._common import issue_lines
from nf_splice.interfaces.tui.state import WizardSnapshot
from nf_splice.interfaces.tui.widgets import FilePanel, StepView
from nf_splice.layers.base import read_layer
from nf_splice.layers.execution import (
    add_generated_profile,
    add_slurm_default_candidate,
    discover_execution,
    pending_profiles,
    profile_config,
    reject_profile,
    review_profile,
    set_default_profile,
    update_profile,
)


class ProfilesView(StepView):
    step_id = "profiles"
    explanation = (
        "Each profile in execution-profiles.draft.yaml names its configuration: "
        "a native Nextflow file in .splice-local/drafts/configs/ (edit it with "
        "Open config, in any editor) or a repository config adopted unchanged. "
        "Keep the 'User Pipeline Input Params' and 'SPLICE Pipeline Input Params' "
        "sections for values users may set and values the deployment sets. "
        "Choose exactly one default; site accounts and queues stay deployment "
        "configuration. Detected repository profiles are optional hints."
    )

    def compose(self) -> ComposeResult:
        yield FilePanel("execution-profiles", config=True)
        yield DataTable(id="profiles-table")
        yield Input(placeholder="name", id="profile-name")
        yield Input(placeholder="description", id="profile-description")
        yield Select(
            [(item.value, item.value) for item in ExecutionProfileType],
            prompt="type",
            id="profile-type",
        )
        yield Select(
            [(item.value, item.value) for item in ExecutionExecutor],
            prompt="executor",
            id="profile-executor",
        )
        yield Select(
            [(item.value, item.value) for item in ContainerEngine],
            prompt="container engine",
            id="profile-engine",
        )
        yield Select(
            [
                ("native config in the drafts", "draft"),
                ("adopt a repository config", "adopt"),
            ],
            prompt="configuration",
            id="profile-route",
        )
        yield Input(
            placeholder="config name (default) or repository path (conf/x.config)",
            id="profile-source",
        )
        with Horizontal(classes="row"):
            yield Button("Save profile", id="profiles-save", variant="success")
            yield Button("New profile", id="profiles-new")
            yield Button("Make default", id="profiles-make-default", variant="primary")
            yield Button("Open this config", id="profiles-open-config")
        with Horizontal(classes="row"):
            yield Select([], prompt="default profile", id="profiles-default")
            yield Button("Set default", id="profiles-set-default")
        yield Static("", id="profiles-config", classes="section")
        yield Static("Detected repository profiles (optional hints)", classes="section")
        with Horizontal(classes="row"):
            yield Button("Discover profiles", id="profiles-discover")
            yield Button("Add a Slurm scaffold", id="profiles-slurm")
        yield DataTable(id="profiles-pending")
        with Horizontal(classes="row"):
            yield Button("Add detected", id="profiles-review")
            yield Input(placeholder="reject reason", id="profile-reason")
            yield Button("Not supported", id="profiles-reject", variant="error")
        yield Static("", id="profiles-issues", classes="issues")

    def setup(self) -> None:
        table = self.query_one("#profiles-table", DataTable)
        table.add_columns("id", "name", "type", "executor", "engine", "config")
        table.cursor_type = "row"
        pending = self.query_one("#profiles-pending", DataTable)
        pending.add_columns("candidate", "executors", "engines", "config sources")
        pending.cursor_type = "row"

    def profiles(self) -> list[dict[str, Any]]:
        state = read_layer(self.wizard.repository, "execution-profiles")
        if state.draft is None or not isinstance(state.draft.data, dict):
            return []
        return [
            item
            for item in state.draft.data.get("profiles") or []
            if isinstance(item, dict)
        ]

    @staticmethod
    def _table_selection(table: DataTable[Any]) -> str | None:
        if not table.row_count:
            return None
        value = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        return str(value) if value is not None else None

    def selected_profile(self) -> dict[str, Any] | None:
        identifier = self._table_selection(self.query_one("#profiles-table", DataTable))
        return next(
            (item for item in self.profiles() if item.get("id") == identifier), None
        )

    def refresh_view(self, snapshot: WizardSnapshot) -> None:
        table = self.query_one("#profiles-table", DataTable)
        selected = self._table_selection(table)
        table.clear()
        profiles = self.profiles()
        for item in profiles:
            config = item.get("config") or {}
            table.add_row(
                str(item.get("id")),
                str(item.get("name") or ""),
                str(item.get("type") or ""),
                str(item.get("executor") or ""),
                str(item.get("container_engine") or ""),
                str(config.get("draft") or config.get("adopt") or config),
                key=str(item.get("id")),
            )
        if selected is not None and selected in table.rows:
            table.move_cursor(row=table.get_row_index(selected))
        pending = self.query_one("#profiles-pending", DataTable)
        pending.clear()
        if read_layer(snapshot.repository, "execution-profiles").file.exists:
            for candidate in pending_profiles(snapshot.repository):
                pending.add_row(
                    candidate.id,
                    ",".join(candidate.executors),
                    ",".join(candidate.container_engines),
                    ",".join(candidate.config_sources),
                    key=candidate.id,
                )
        state = read_layer(snapshot.repository, "execution-profiles")
        data = (
            state.draft.data
            if state.draft is not None and isinstance(state.draft.data, dict)
            else {}
        )
        default = self.query_one("#profiles-default", Select)
        default.set_options(
            [
                (f"{item.get('name')} ({item.get('id')})", str(item.get("id")))
                for item in profiles
            ]
        )
        if data.get("default_profile") in {item.get("id") for item in profiles}:
            default.value = data["default_profile"]
        self.show_profile()
        self.query_one("#profiles-issues", Static).update(
            issue_lines(snapshot.repository, "execution-profiles")
        )

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table.id == "profiles-table":
            self.show_profile()

    def show_profile(self) -> None:
        profile = self.selected_profile()
        if profile is None:
            self.query_one("#profiles-config", Static).update("")
            return
        self.query_one("#profile-name", Input).value = str(profile.get("name") or "")
        self.query_one("#profile-description", Input).value = str(
            profile.get("description") or ""
        )
        for selector, field in (
            ("#profile-type", "type"),
            ("#profile-executor", "executor"),
            ("#profile-engine", "container_engine"),
        ):
            select = self.query_one(selector, Select)
            if profile.get(field):
                select.value = str(profile[field])
            else:
                select.clear()
        config = profile.get("config") or {}
        route = "adopt" if "adopt" in config or config.get("source") else "draft"
        self.query_one("#profile-route", Select).value = route
        self.query_one("#profile-source", Input).value = str(
            config.get("adopt")
            or config.get("source")
            or str(config.get("draft") or "").removesuffix(".draft.config")
        )
        _strategy, path, problem = profile_config(self.wizard.repository, profile)
        text = (
            read_file(self.wizard.repository, path).text
            if path and path.startswith(".splice-local/")
            else (self.wizard.repository / path).read_text(encoding="utf-8")
            if path and (self.wizard.repository / path).is_file()
            else None
        )
        self.query_one("#profiles-config", Static).update(
            f"--- {path}\n{text}"[:6000] if text is not None else problem or ""
        )

    def _select(self, selector: str) -> str:
        value = self.query_one(selector, Select).value
        return "" if value is Select.BLANK else str(value)

    def _changes(self) -> dict[str, Any]:
        changes: dict[str, Any] = {}
        for field, value in (
            ("name", self.query_one("#profile-name", Input).value.strip()),
            (
                "description",
                self.query_one("#profile-description", Input).value.strip(),
            ),
            ("type", self._select("#profile-type")),
            ("executor", self._select("#profile-executor")),
            ("container_engine", self._select("#profile-engine")),
        ):
            if value:
                changes[field] = value
        source = self.query_one("#profile-source", Input).value.strip()
        if source:
            route = self._select("#profile-route") or "draft"
            changes["config_adopt" if route == "adopt" else "config_draft"] = source
        return changes

    def on_button_pressed(self, event: Button.Pressed) -> None:
        app = self.wizard
        button = event.button.id
        profile = self.selected_profile()
        if button == "profiles-save":
            event.stop()
            if profile is None:
                app.set_status("Select a profile first.", error=True)
                return
            identifier = str(profile["id"])
            changes = self._changes()
            app.perform(
                f"Saving profile {identifier}",
                lambda: update_profile(
                    app.repository, identifier, changes, app.change_context()
                ),
            )
        elif button == "profiles-new":
            event.stop()
            name = self.query_one("#profile-name", Input).value.strip()
            if not name:
                app.set_status("Give the new profile a name.", error=True)
                return
            app.perform(
                f"Adding profile {name}",
                lambda: add_generated_profile(
                    app.repository,
                    app.change_context(),
                    name=name,
                    description=self.query_one(
                        "#profile-description", Input
                    ).value.strip()
                    or f"{name} profile.",
                    profile_type=self._select("#profile-type") or "development",
                    executor=self._select("#profile-executor") or "local",
                    container_engine=self._select("#profile-engine") or "singularity",
                ),
            )
        elif button in {"profiles-make-default", "profiles-set-default"}:
            event.stop()
            identifier = (
                str(profile["id"])
                if button == "profiles-make-default" and profile is not None
                else self._select("#profiles-default")
            )
            if not identifier:
                return
            app.perform(
                "Setting the default profile",
                lambda: set_default_profile(
                    app.repository, identifier, app.change_context()
                ),
            )
        elif button == "profiles-open-config":
            event.stop()
            if profile is None:
                return
            _strategy, path, problem = profile_config(app.repository, profile)
            panel = self.query_one(FilePanel)
            if path is None:
                app.set_status(problem or "This profile has no config.", error=True)
            else:
                panel._edit(path)
        elif button == "profiles-discover":
            event.stop()
            app.perform(
                "Discovering profiles", lambda: discover_execution(app.repository)
            )
        elif button == "profiles-slurm":
            event.stop()
            app.perform(
                "Adding a Slurm scaffold",
                lambda: add_slurm_default_candidate(
                    app.repository, app.change_context()
                ),
            )
        elif button == "profiles-review":
            event.stop()
            hint = self._table_selection(self.query_one("#profiles-pending", DataTable))
            if hint is None:
                return
            candidate = hint
            route = self._select("#profile-route")
            source = self.query_one("#profile-source", Input).value.strip() or None
            app.perform(
                "Adding detected profile",
                lambda: review_profile(
                    app.repository,
                    candidate,
                    app.change_context(),
                    profile_type=self._select("#profile-type"),
                    description=self.query_one(
                        "#profile-description", Input
                    ).value.strip(),
                    executor=self._select("#profile-executor"),
                    container_engine=self._select("#profile-engine"),
                    config_source=source if route == "adopt" else None,
                ),
            )
        elif button == "profiles-reject":
            event.stop()
            hint = self._table_selection(self.query_one("#profiles-pending", DataTable))
            reason = self.query_one("#profile-reason", Input).value.strip()
            if hint is None or not reason:
                app.set_status(
                    "Select a detected profile and give a reason.", error=True
                )
                return
            candidate = hint
            app.perform(
                "Recording an unsupported profile",
                lambda: reject_profile(
                    app.repository, candidate, reason, app.change_context()
                ),
            )
