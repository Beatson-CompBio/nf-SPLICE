"""Plan diff and explicit publication."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, Label, Static, Switch

from nf_splice.interfaces.tui.state import WizardSnapshot
from nf_splice.interfaces.tui.widgets import StepView
from nf_splice.services.lifecycle import plan_promotion, promote


class BuildView(StepView):
    step_id = "build"
    explanation = (
        "Publication is staged and atomic: bundle.json and the lock are written "
        "last and a failure restores the previous release."
    )

    def compose(self) -> ComposeResult:
        yield Static("", id="build-plan", classes="section")
        with Horizontal(classes="row"):
            yield Switch(value=False, id="build-replace")
            yield Label("I reviewed the diff; replace existing published files")
        yield Button("Publish bundle", id="build-publish", variant="primary")
        yield Static("", id="build-log", classes="section")

    def refresh_view(self, snapshot: WizardSnapshot) -> None:
        try:
            plan = plan_promotion(snapshot.repository)
        except ValueError as error:
            self.query_one("#build-plan", Static).update(str(error))
            return
        if not plan.ready:
            text = "Blocked:\n" + "\n".join(
                f"- {item.layer}{item.pointer}: {item.message}"
                for item in plan.blockers
            )
        else:
            text = "\n".join(
                f"{item.kind}: splice/{item.path}"
                + (f"\n{item.diff[:1500]}" if item.diff else "")
                for item in plan.changes
            )
        self.query_one("#build-plan", Static).update(text)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "build-publish":
            return
        event.stop()
        app = self.wizard
        replace = self.query_one("#build-replace", Switch).value

        def published(result: object) -> None:
            from nf_splice.services.readiness import lifecycle

            wrote = getattr(result, "wrote", ())
            lines = [f"wrote splice/{path}" for path in wrote] or ["No files changed."]
            lines.extend(lifecycle(app.repository).lines())
            self.query_one("#build-log", Static).update("\n".join(lines))

        app.perform(
            "Publishing bundle",
            lambda: promote(
                app.repository, None, app.change_context(), replace_existing=replace
            ),
            then=published,
        )
