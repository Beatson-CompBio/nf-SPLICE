"""Welcome: choose how to work, then create, resume or inspect."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, Markdown

from nf_splice.agents.state import InteractionMode
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
        yield Markdown(
            "**Manual**: review each step yourself. Press Ctrl+A on any step to "
            "ask AI a question; it never changes anything.",
            id="welcome-manual",
        )
        with Horizontal(classes="row"):
            yield Button("Create new", id="welcome-create", variant="primary")
            yield Button("Resume existing", id="welcome-resume")
            yield Button("Inspect only", id="welcome-inspect")
        yield Markdown(
            "**Agentic AI**: let an agent do the integration work, either with "
            "you approving each stage, or unattended within a scope you approve.",
            id="welcome-agentic",
        )
        with Horizontal(classes="row"):
            yield Button("AI-assisted session", id="welcome-assisted")
            yield Button("Autonomous integration", id="welcome-autonomous")

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
        elif event.button.id == "welcome-assisted":
            event.stop()
            app.open_session(InteractionMode.ASSISTED)
        elif event.button.id == "welcome-autonomous":
            event.stop()
            app.open_session(InteractionMode.AUTONOMOUS)
        elif event.button.id == "welcome-inspect":
            event.stop()
            app.inspect_only = True
            app.set_status("Inspect-only mode: browsing without writing.")
            app.show_step("repository")
