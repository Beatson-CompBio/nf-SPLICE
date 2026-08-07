"""Textual application shell over a shared workspace snapshot."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Footer, Header, Label, ListItem, ListView, Static

from nf_splice.services import LayerSummary, WorkspaceSnapshot


def _display_name(value: str) -> str:
    return value.replace("_", " ").title()


class NfSpliceApp(App[None]):
    """Navigable read-only view of repository and integration state."""

    TITLE = "nf-splice"
    SUB_TITLE = "SPLICE integration workspace"
    CSS = """
    #repository { height: auto; padding: 1 2; background: $primary-background; }
    #workspace { height: 1fr; }
    #layers { width: 30; border-right: solid $primary; }
    #details { width: 1fr; padding: 1 2; }
    .section { margin-bottom: 1; }
    .heading { text-style: bold; color: $accent; }
    """

    def __init__(self, snapshot: WorkspaceSnapshot) -> None:
        super().__init__()
        self.snapshot = snapshot

    def compose(self) -> ComposeResult:
        """Compose a summary with keyboard-navigable integration layers."""
        inspection = self.snapshot.inspection
        revision = inspection.repository_revision or "not detected"
        yield Header()
        yield Static(
            f"Repository: {inspection.root}\n"
            f"Revision: {revision}\n"
            f"SPLICE tree: {inspection.splice_tree.state.value}\n"
            f"Evidence: {len(inspection.evidence)}",
            id="repository",
        )
        with Horizontal(id="workspace"):
            yield ListView(
                *(
                    ListItem(Label(_display_name(layer.name)))
                    for layer in self.snapshot.layers
                ),
                id="layers",
            )
            with VerticalScroll(id="details"):
                yield Static("Integration status", classes="heading")
                yield Static(
                    self._integration_text(), id="integration", classes="section"
                )
                yield Static("Selected layer", classes="heading")
                yield Static("", id="layer-detail", classes="section")
                yield Static("Warnings", classes="heading")
                yield Static(self._warnings_text(), id="warnings", classes="section")
                yield Static("Evidence", classes="heading")
                yield Static(self._evidence_text(), id="evidence", classes="section")
        yield Footer()

    def on_mount(self) -> None:
        """Select and focus the first integration layer."""
        layer_list = self.query_one("#layers", ListView)
        layer_list.index = 0
        layer_list.focus()
        self._show_layer(0)

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Update layer detail when keyboard navigation changes selection."""
        if event.list_view.id == "layers" and event.list_view.index is not None:
            self._show_layer(event.list_view.index)

    def _show_layer(self, index: int) -> None:
        layer = self.snapshot.layers[index]
        self.query_one("#layer-detail", Static).update(self._layer_text(layer))

    def _integration_text(self) -> str:
        unresolved = self.snapshot.authoring.unresolved_decisions
        unresolved_text = "not available" if unresolved is None else str(unresolved)
        return (
            f"Authoring state: {self.snapshot.authoring.state.value}\n"
            f"Unresolved decisions: {unresolved_text}\n"
            f"Build: {self.snapshot.build_status}\n"
            f"Validation: {self.snapshot.validation_status}"
        )

    @staticmethod
    def _layer_text(layer: LayerSummary) -> str:
        unresolved = layer.unresolved_decisions
        unresolved_text = "not available" if unresolved is None else str(unresolved)
        return (
            f"{_display_name(layer.name)}\n"
            f"Status: {layer.status.value}\n"
            f"Decisions: {layer.decision_count}\n"
            f"Unresolved: {unresolved_text}"
        )

    def _warnings_text(self) -> str:
        if not self.snapshot.warnings:
            return "No inspection warnings."
        return "\n".join(f"• {warning}" for warning in self.snapshot.warnings)

    def _evidence_text(self) -> str:
        if not self.snapshot.evidence_counts:
            return "No repository evidence detected."
        return "\n".join(
            f"{_display_name(item.kind.value)}: {item.count}"
            for item in self.snapshot.evidence_counts
        )
