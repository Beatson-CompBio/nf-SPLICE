"""Execution profiles: adopted or generated configs and one default."""

from __future__ import annotations

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
from nf_splice.interfaces.tui.widgets import StepView
from nf_splice.layers.base import read_layer
from nf_splice.layers.execution import (
    add_slurm_default_candidate,
    config_draft_path,
    discover_execution,
    pending_profiles,
    reject_profile,
    review_profile,
    set_default_profile,
)


class ProfilesView(StepView):
    step_id = "profiles"
    explanation = (
        "Select which detected profiles the platform supports. Adopt a config "
        "unchanged, or generate one with the 'User Pipeline Input Params' and "
        "'SPLICE Pipeline Input Params' sections. Choose exactly one default; "
        "site accounts and queues stay operator configuration."
    )

    def compose(self) -> ComposeResult:
        with Horizontal(classes="row"):
            yield Button("Discover profiles", id="profiles-discover")
            yield Button("Add SPLICE Slurm candidate", id="profiles-slurm")
        yield DataTable(id="profiles-pending")
        yield Select(
            [(item.value, item.value) for item in ExecutionProfileType],
            prompt="type",
            id="profile-type",
        )
        yield Input(placeholder="description", id="profile-description")
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
            [("adopt existing config", "adopt"), ("generate config", "generate")],
            prompt="config route",
            id="profile-route",
        )
        yield Input(
            placeholder="config source for adopt (e.g. conf/local.config)",
            id="profile-source",
        )
        with Horizontal(classes="row"):
            yield Button("Support selected", id="profiles-review", variant="success")
            yield Input(placeholder="reject reason", id="profile-reason")
            yield Button("Reject selected", id="profiles-reject", variant="error")
        with Horizontal(classes="row"):
            yield Select([], prompt="default profile", id="profiles-default")
            yield Button("Set default", id="profiles-set-default", variant="primary")
        yield Static("", id="profiles-config", classes="section")
        yield Static("", id="profiles-issues", classes="issues")

    def setup(self) -> None:
        table = self.query_one("#profiles-pending", DataTable)
        table.add_columns("candidate", "executors", "engines", "config sources")
        table.cursor_type = "row"

    def refresh_view(self, snapshot: WizardSnapshot) -> None:
        table = self.query_one("#profiles-pending", DataTable)
        table.clear()
        state = read_layer(snapshot.repository, "execution-profiles")
        if state.file.exists:
            for item in pending_profiles(snapshot.repository):
                table.add_row(
                    item.id,
                    ",".join(item.executors),
                    ",".join(item.container_engines),
                    ",".join(item.config_sources),
                    key=item.id,
                )
        data = (
            state.draft.data
            if state.draft is not None and isinstance(state.draft.data, dict)
            else {}
        )
        profiles = [
            item for item in data.get("profiles") or [] if isinstance(item, dict)
        ]
        default = self.query_one("#profiles-default", Select)
        default.set_options(
            [(f"{item['name']} ({item['id']})", item["id"]) for item in profiles]
        )
        if data.get("default_profile") in {item["id"] for item in profiles}:
            default.value = data["default_profile"]
        previews = []
        for profile in profiles:
            if (profile.get("config") or {}).get("strategy") == "generated":
                path = config_draft_path(profile["id"])
                text = read_file(snapshot.repository, path).text or ""
                previews.append(f"--- {path}\n{text}")
        self.query_one("#profiles-config", Static).update("\n".join(previews))
        self.query_one("#profiles-issues", Static).update(
            issue_lines(snapshot.repository, "execution-profiles")
        )

    def _select(self, selector: str) -> str:
        value = self.query_one(selector, Select).value
        return "" if value is Select.BLANK else str(value)

    def _selected(self) -> str | None:
        table = self.query_one("#profiles-pending", DataTable)
        if not table.row_count:
            return None
        return str(table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        app = self.wizard
        button = event.button.id
        if button == "profiles-discover":
            event.stop()
            app.perform(
                "Discovering profiles", lambda: discover_execution(app.repository)
            )
        elif button == "profiles-slurm":
            event.stop()
            app.perform(
                "Adding SPLICE Slurm candidate",
                lambda: add_slurm_default_candidate(
                    app.repository, app.change_context()
                ),
            )
        elif button == "profiles-review":
            event.stop()
            selected = self._selected()
            if selected is None:
                return
            identifier: str = selected
            route = self._select("#profile-route")
            source = self.query_one("#profile-source", Input).value.strip() or None
            app.perform(
                "Supporting profile",
                lambda: review_profile(
                    app.repository,
                    identifier,
                    app.change_context(),
                    profile_type=self._select("#profile-type"),
                    description=self.query_one("#profile-description", Input).value,
                    executor=self._select("#profile-executor"),
                    container_engine=self._select("#profile-engine"),
                    config_source=source if route != "generate" else None,
                    generate={} if route == "generate" else None,
                ),
            )
        elif button == "profiles-reject":
            event.stop()
            rejected = self._selected()
            reason = self.query_one("#profile-reason", Input).value
            if rejected is not None:
                candidate: str = rejected
                app.perform(
                    "Rejecting profile",
                    lambda: reject_profile(
                        app.repository, candidate, reason, app.change_context()
                    ),
                )
        elif button == "profiles-set-default":
            event.stop()
            selected = self._select("#profiles-default")
            if selected:
                app.perform(
                    "Setting default profile",
                    lambda: set_default_profile(
                        app.repository, selected, app.change_context()
                    ),
                )
