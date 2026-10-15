"""Validation report and reproducible CLI equivalents."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Static

from nf_splice.interfaces.tui.state import WizardSnapshot
from nf_splice.interfaces.tui.widgets import StepView
from nf_splice.services.lifecycle import validate_bundle

CLI_EQUIVALENT = (
    "The reviewed decisions are the committed draft files; reproduce and check "
    "them in CI with:\n"
    "  nf-splice draft validate\n"
    "  nf-splice build all --check --json\n"
    "  nf-splice validate --json\n"
)


class DoneView(StepView):
    step_id = "done"
    explanation = "Commit splice/ (drafts and published files) to share the bundle."

    def compose(self) -> ComposeResult:
        yield Static("", id="done-report", classes="section")
        yield Static(CLI_EQUIVALENT, id="done-cli", classes="section")

    def refresh_view(self, snapshot: WizardSnapshot) -> None:
        report = validate_bundle(snapshot.repository)
        lines = [
            f"Bundle valid: {'yes' if report.valid else 'no'} "
            f"({report.checked_files} contract files)"
        ]
        lines.extend(
            f"{item.severity.value}: {item.path} [{item.rule}] {item.message}"
            for item in report.issues
        )
        self.query_one("#done-report", Static).update("\n".join(lines))
