"""Components and container images (source vs downloadable distribution)."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, DataTable, Input, Label, Static, Switch

from nf_splice.interfaces.tui.screens._common import issue_lines
from nf_splice.interfaces.tui.state import WizardSnapshot
from nf_splice.interfaces.tui.widgets import FilePanel, StepView
from nf_splice.layers.base import read_layer
from nf_splice.layers.components import (
    accept_component,
    accept_unambiguous_components,
    discover_components,
    pending_components,
    set_image_policy,
    verify_distribution,
)


class ComponentsView(StepView):
    step_id = "components"
    explanation = (
        "components.draft.yaml lists every module with its tool, version and "
        "container, seeded from modules.json and the module sources; 'unresolved' "
        "shows what still needs a decision. Edit it with Open YAML. A registry "
        "(OCI/Docker) reference is not a downloadable image file: Docker and "
        "Singularity/Apptainer sources are kept separately, and a downloadable "
        "image is recorded only after nf-splice has downloaded and checksummed "
        "it (explicit network approval). Modules added to the pipeline later "
        "appear below as optional hints."
    )

    def compose(self) -> ComposeResult:
        yield FilePanel("components")
        yield DataTable(id="components-inventory")
        yield Static("Modules not yet in the draft (optional hints)", classes="section")
        with Horizontal(classes="row"):
            yield Button("Discover modules", id="components-discover")
            yield Button("Add all unambiguous", id="components-accept-all")
            yield Button("Add selected", id="components-accept")
        yield DataTable(id="components-pending")
        with Horizontal(classes="row"):
            yield Switch(value=False, id="components-require")
            yield Label(
                "Ingestion requires a verified downloadable image per container"
            )
            yield Button("Save image policy", id="components-policy")
        yield DataTable(id="components-containers")
        with Horizontal(classes="row"):
            yield Input(placeholder="container id", id="components-container-id")
            yield Input(placeholder="https:// image URL", id="components-url")
        with Horizontal(classes="row"):
            yield Switch(value=False, id="components-approve-network")
            yield Label("I approve downloading this image now")
            yield Button("Verify image", id="components-verify")
        yield Static("", id="components-issues", classes="issues")

    def setup(self) -> None:
        inventory = self.query_one("#components-inventory", DataTable)
        inventory.add_columns("component", "tool", "version", "container", "unresolved")
        pending = self.query_one("#components-pending", DataTable)
        pending.add_columns(
            "candidate", "versions", "proposed sources", "needs decision"
        )
        pending.cursor_type = "row"
        containers = self.query_one("#components-containers", DataTable)
        containers.add_columns(
            "container", "docker", "singularity/apptainer", "distribution", "sha256"
        )

    def refresh_view(self, snapshot: WizardSnapshot) -> None:
        pending = self.query_one("#components-pending", DataTable)
        pending.clear()
        state = read_layer(snapshot.repository, "components")
        if state.file.exists:
            for item in pending_components(snapshot.repository):
                pending.add_row(
                    item.id,
                    ", ".join(item.versions),
                    ", ".join(
                        f"{key}={value}" for key, value in item.proposed_sources.items()
                    ),
                    "; ".join(item.problems) or "-",
                    key=item.id,
                )
        containers = self.query_one("#components-containers", DataTable)
        containers.clear()
        data = (
            state.draft.data
            if state.draft is not None and isinstance(state.draft.data, dict)
            else {}
        )
        inventory = self.query_one("#components-inventory", DataTable)
        inventory.clear()
        for item in data.get("components") or []:
            if not isinstance(item, dict):
                continue
            tool = item.get("tool") or {}
            inventory.add_row(
                str(item.get("id")),
                str(tool.get("name") or ""),
                str(tool.get("version") or "?"),
                str(item.get("container_id") or "-"),
                "; ".join(item.get("unresolved") or []) or "-",
                key=str(item.get("id")),
            )
        self.query_one("#components-require", Switch).value = bool(
            data.get("require_downloadable_images")
        )
        for item in data.get("containers") or []:
            sources = item.get("source_images") or {}
            distribution = item.get("distribution") or {}
            containers.add_row(
                item.get("id"),
                sources.get("docker", ""),
                sources.get("singularity") or sources.get("apptainer") or "",
                distribution.get("download_uri", "none (source only)"),
                (distribution.get("sha256") or "")[:12],
                key=item.get("id"),
            )
        self.query_one("#components-issues", Static).update(
            issue_lines(snapshot.repository, "components")
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        app = self.wizard
        button = event.button.id
        if button == "components-discover":
            event.stop()
            app.perform(
                "Discovering modules", lambda: discover_components(app.repository)
            )
        elif button == "components-accept-all":
            event.stop()
            app.perform(
                "Accepting unambiguous components",
                lambda: accept_unambiguous_components(
                    app.repository, app.change_context()
                ),
            )
        elif button == "components-accept":
            event.stop()
            table = self.query_one("#components-pending", DataTable)
            if not table.row_count:
                return
            identifier = str(
                table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
            )
            app.perform(
                "Accepting component",
                lambda: accept_component(
                    app.repository, identifier, app.change_context()
                ),
            )
        elif button == "components-policy":
            event.stop()
            required = self.query_one("#components-require", Switch).value
            app.perform(
                "Saving image policy",
                lambda: set_image_policy(
                    app.repository, required, app.change_context()
                ),
            )
        elif button == "components-verify":
            event.stop()
            if not self.query_one("#components-approve-network", Switch).value:
                app.set_status(
                    "Approve the download first; nothing was fetched.", error=True
                )
                return
            identifier = self.query_one("#components-container-id", Input).value.strip()
            url = self.query_one("#components-url", Input).value.strip()
            app.perform(
                "Downloading and verifying image",
                lambda: verify_distribution(
                    app.repository, identifier, url, app.change_context()
                ),
            )
