"""Repository inspection summary (read-only)."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Static

from nf_splice.interfaces.tui.state import WizardSnapshot
from nf_splice.interfaces.tui.widgets import StepView


class RepositoryView(StepView):
    step_id = "repository"
    explanation = "Evidence is read-only; it never becomes a decision on its own."

    def compose(self) -> ComposeResult:
        yield Static("", id="repository-summary", classes="section")
        yield Static("", id="repository-warnings", classes="issues")

    def refresh_view(self, snapshot: WizardSnapshot) -> None:
        status = snapshot.status
        if status is None:
            return
        inspection = status.inspection
        lines = [
            f"Revision: {inspection.repository_revision or 'not detected'}",
            f"splice/ tree: {inspection.splice_tree.state.value}",
            f"Evidence items: {len(inspection.evidence)}",
            *(f"  {item.kind.value}: {item.count}" for item in status.evidence_counts),
            "Layers:",
            *(f"  {item.layer}: {item.state.value}" for item in status.artifacts),
        ]
        self.query_one("#repository-summary", Static).update("\n".join(lines))
        self.query_one("#repository-warnings", Static).update(
            "\n".join(f"Warning: {item}" for item in status.warnings)
        )
