"""Preview and explicitly apply 0.1.0 state migration."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, Label, Static, Switch

from nf_splice.interfaces.tui.state import WizardSnapshot
from nf_splice.interfaces.tui.widgets import StepView
from nf_splice.services.migration import (
    MigrationError,
    apply_draft_migration,
    plan_draft_migration,
)


class MigrationView(StepView):
    step_id = "migration"
    explanation = (
        "Legacy splice/nf-splice.yaml is read-only migration input. Applying "
        "creates only absent drafts; the legacy file is never changed."
    )

    def compose(self) -> ComposeResult:
        yield Static("", id="migration-notes", classes="section")
        with Horizontal(classes="row"):
            yield Switch(value=False, id="migration-map-library")
            yield Label("Legacy library IDs are platform run IDs (reviewed mapping)")
        yield Button("Apply migration", id="migration-apply", variant="warning")

    def refresh_view(self, snapshot: WizardSnapshot) -> None:
        notes = self.query_one("#migration-notes", Static)
        if not snapshot.legacy_state:
            notes.update("No 0.1.0 authoring state was found; nothing to migrate.")
            self.query_one("#migration-apply", Button).disabled = True
            return
        try:
            plan = plan_draft_migration(
                snapshot.repository,
                map_library_to_run=self.query_one(
                    "#migration-map-library", Switch
                ).value,
            )
        except MigrationError as error:
            notes.update(str(error))
            return
        notes.update(
            "\n".join(
                f"{item.kind}: {item.layer}{item.pointer}: {item.message}"
                for item in plan.notes
            )
            + ("\nExisting drafts are preserved." if plan.existing else "")
        )

    def on_switch_changed(self, _event: Switch.Changed) -> None:
        self.refresh_view(self.wizard.snapshot)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "migration-apply":
            return
        event.stop()
        app = self.wizard
        mapping = self.query_one("#migration-map-library", Switch).value
        app.perform(
            "Migrating legacy state into drafts",
            lambda: apply_draft_migration(
                app.repository, app.change_context(), map_library_to_run=mapping
            ),
        )
