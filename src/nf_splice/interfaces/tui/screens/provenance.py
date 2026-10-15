"""RO-Crate analysis and reviewed include/enrich/generate strategy."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, Static

from nf_splice.interfaces.tui.screens._common import issue_lines
from nf_splice.interfaces.tui.state import WizardSnapshot
from nf_splice.interfaces.tui.widgets import StepView
from nf_splice.layers.provenance import (
    analyse_ro_crate,
    choose_include,
    generate_minimal,
    prepare_enrichment,
)
from nf_splice.services.lifecycle import validate_layer


class ProvenanceView(StepView):
    step_id = "provenance"
    explanation = (
        "Your repository-root ro-crate-metadata.json is never modified. Include "
        "it unchanged when current, review an enriched copy when it is stale, or "
        "generate a minimal Workflow RO-Crate from reviewed identity."
    )

    def compose(self) -> ComposeResult:
        yield Static("", id="provenance-findings", classes="section")
        with Horizontal(classes="row"):
            yield Button("Include unchanged", id="provenance-include")
            yield Button("Review enriched copy", id="provenance-enrich")
            yield Button("Generate minimal", id="provenance-generate")
        yield Static("", id="provenance-preview", classes="section")
        yield Static("", id="provenance-issues", classes="issues")

    def refresh_view(self, snapshot: WizardSnapshot) -> None:
        analysis = analyse_ro_crate(snapshot.repository)
        if not analysis.present:
            text = (
                "No repository-root RO-Crate: generate a minimal one from "
                "reviewed identity."
            )
        else:
            text = (
                "\n".join(
                    f"{item.severity.value.upper()} {item.pointer} "
                    f"[{item.code}] {item.message}"
                    for item in analysis.findings
                )
                or "Root RO-Crate agrees with the reviewed identity."
            )
        self.query_one("#provenance-findings", Static).update(text)
        payload = validate_layer(snapshot.repository, "provenance").files.get(
            "ro-crate-metadata.json"
        )
        self.query_one("#provenance-preview", Static).update(
            payload.decode("utf-8")[:3000] if payload else ""
        )
        self.query_one("#provenance-issues", Static).update(
            issue_lines(snapshot.repository, "provenance")
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        app = self.wizard
        actions = {
            "provenance-include": ("Including root RO-Crate", choose_include),
            "provenance-enrich": ("Preparing enriched RO-Crate", prepare_enrichment),
            "provenance-generate": ("Generating minimal RO-Crate", generate_minimal),
        }
        if event.button.id in actions:
            event.stop()
            label, action = actions[event.button.id]
            app.perform(label, lambda: action(app.repository, app.change_context()))
