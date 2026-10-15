"""Welcome: create, resume or inspect only."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, Markdown

from nf_splice.interfaces.tui.state import WizardSnapshot
from nf_splice.interfaces.tui.widgets import StepView
from nf_splice.services.workspace import initialise


class WelcomeView(StepView):
    step_id = "welcome"
    explanation = (
        "nf-splice keeps one editable draft per layer under splice/drafts/. "
        "Nothing is published until you review the plan and build explicitly. "
        "Detected values are suggestions until you confirm or edit them."
    )

    def compose(self) -> ComposeResult:
        yield Markdown("", id="welcome-summary")
        with Horizontal(classes="row"):
            yield Button("Create new", id="welcome-create", variant="primary")
            yield Button("Resume existing", id="welcome-resume")
            yield Button("Inspect only", id="welcome-inspect")

    def refresh_view(self, snapshot: WizardSnapshot) -> None:
        drafts = (
            "Drafts exist for this repository: resume to continue where you left off."
            if snapshot.has_drafts
            else "No drafts exist yet: create new drafts from repository evidence."
        )
        self.query_one("#welcome-summary", Markdown).update(
            f"**Repository:** `{snapshot.repository.name}`\n\n{drafts}"
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        app = self.wizard
        if event.button.id == "welcome-create":
            event.stop()
            app.perform(
                "Creating drafts from evidence",
                lambda: initialise(app.repository, app.change_context()),
                then=lambda _result: app.show_step("repository"),
            )
        elif event.button.id == "welcome-resume":
            event.stop()
            app.resume()
        elif event.button.id == "welcome-inspect":
            event.stop()
            app.inspect_only = True
            app.set_status("Inspect-only mode: browsing without writing.")
            app.show_step("repository")
