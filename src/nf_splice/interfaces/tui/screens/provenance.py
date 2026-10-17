"""The pipeline's RO-Crate graph: authored in the draft, checked against identity."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, Static

from nf_splice.interfaces.tui.screens._common import issue_lines
from nf_splice.interfaces.tui.state import WizardSnapshot
from nf_splice.interfaces.tui.widgets import FilePanel, StepView
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
        "provenance.draft.yaml holds the pipeline's RO-Crate graph, seeded from "
        "the repository-root crate (a copy; the original is never modified) or "
        "built from the identity. Edit it with Open YAML, or use a shortcut: "
        "adopt the current root crate, correct a copy from the reviewed "
        "identity, or rebuild it from the identity. nf-splice adds the splice/ "
        "bundle entities when it builds."
    )

    def compose(self) -> ComposeResult:
        yield FilePanel("provenance")
        yield Static("", id="provenance-findings", classes="section")
        with Horizontal(classes="row"):
            yield Button("Adopt root crate", id="provenance-include")
            yield Button("Correct from identity", id="provenance-enrich")
            yield Button("Rebuild from identity", id="provenance-generate")
        yield Static("", id="provenance-preview", classes="section")
        yield Static("", id="provenance-issues", classes="issues")

    def refresh_view(self, snapshot: WizardSnapshot) -> None:
        analysis = analyse_ro_crate(snapshot.repository)
        if not analysis.present:
            text = (
                "No repository-root RO-Crate: the draft's graph was built from "
                "the identity."
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
