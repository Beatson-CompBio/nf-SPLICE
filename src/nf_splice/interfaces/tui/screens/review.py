"""Unified readiness checklist with jump-to-fix links."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, Static

from nf_splice.interfaces.tui.state import WizardSnapshot
from nf_splice.interfaces.tui.widgets import StepView

_LAYER_STEP = {
    "bundle": "identity",
    "inputs": "inputs",
    "outputs": "outputs",
    "components": "components",
    "execution-profiles": "profiles",
    "provenance": "provenance",
}


class ReviewView(StepView):
    step_id = "review"
    explanation = "Every blocker must be resolved before the bundle can be published."

    def compose(self) -> ComposeResult:
        yield Static("", id="review-summary", classes="section")
        with Horizontal(classes="row", id="review-jumps"):
            for layer, target in _LAYER_STEP.items():
                yield Button(f"Fix {layer}", id=f"review-jump-{target}")

    def refresh_view(self, snapshot: WizardSnapshot) -> None:
        if snapshot.publish_ready:
            text = "All layers are ready. Continue to Build to review the plan diff."
        else:
            text = "Blockers:\n" + "\n".join(
                f"- {item}" for item in snapshot.publish_blockers
            )
        self.query_one("#review-summary", Static).update(text)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id and event.button.id.startswith("review-jump-"):
            event.stop()
            self.wizard.show_step(event.button.id.removeprefix("review-jump-"))
