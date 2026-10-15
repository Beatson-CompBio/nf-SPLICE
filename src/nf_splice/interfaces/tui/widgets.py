"""Shared wizard widgets: progress rail, status line and step view base."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from textual.containers import VerticalScroll
from textual.widgets import Label, ListItem, ListView, Static

from nf_splice.interfaces.tui.state import WizardSnapshot
from nf_splice.interfaces.tui.steps import STEPS, StepStatus, status

if TYPE_CHECKING:
    from nf_splice.interfaces.tui.app import NfSpliceApp

GLYPHS = {
    StepStatus.LOCKED: "·",
    StepStatus.TODO: "○",
    StepStatus.BLOCKED: "!",
    StepStatus.DEFERRED: "»",
    StepStatus.COMPLETE: "✓",
}


class ProgressRail(ListView):
    """Keyboard-navigable checklist of steps with their derived status."""

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(
            *(
                ListItem(
                    Label(item.title, id=f"rail-label-{item.id}"), id=f"rail-{item.id}"
                )
                for item in STEPS
            ),
            id=id,
        )

    def update_steps(
        self,
        snapshot: WizardSnapshot,
        current: str,
        visited: frozenset[str],
        deferred: frozenset[str],
    ) -> None:
        for item in STEPS:
            state = status(item, snapshot, visited=visited, deferred=deferred)
            marker = "▶ " if item.id == current else "  "
            labels = self.query(f"#rail-label-{item.id}")
            for label in labels:
                assert isinstance(label, Label)
                label.update(f"{marker}{GLYPHS[state]} {item.title}")


class StatusLine(Static):
    """Persistent message line; errors stay until replaced by a success."""

    def show(self, message: str, *, error: bool = False) -> None:
        self.set_class(error, "error")
        self.update(("Error: " if error else "") + message)


class StepView(VerticalScroll):
    """Base class of every step; subclasses render one focused task."""

    step_id: ClassVar[str] = ""
    title: ClassVar[str] = ""
    explanation: ClassVar[str] = ""

    @property
    def wizard(self) -> NfSpliceApp:
        from nf_splice.interfaces.tui.app import NfSpliceApp

        app = self.app
        assert isinstance(app, NfSpliceApp)
        return app

    def on_mount(self) -> None:
        self.setup()
        self.refresh_view(self.wizard.snapshot)
        self.restore(self.wizard.session.unsaved.get(self.step_id, {}))

    def setup(self) -> None:
        """Configure child widgets once they are mounted."""

    def refresh_view(self, snapshot: WizardSnapshot) -> None:
        """Re-render from a freshly derived snapshot."""

    def unsaved(self) -> dict[str, str]:
        """Return half-typed form values to keep in the session."""
        return {}

    def restore(self, values: dict[str, str]) -> None:
        """Restore half-typed form values from the session."""

    def help_text(self) -> str:
        return self.explanation

    @staticmethod
    def table_text(rows: list[list[Any]]) -> str:
        return "\n".join("  ".join(str(cell) for cell in row) for row in rows)
