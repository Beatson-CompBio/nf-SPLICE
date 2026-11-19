"""The page base class: heading, contextual AI actions and cheap refreshes."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Static

from nf_splice.interfaces.tui.model import WorkspaceModel
from nf_splice.interfaces.tui.navigation import LABELS, Page, StepState, Target
from nf_splice.interfaces.tui.navigation import page as page_spec
from nf_splice.interfaces.tui.widgets import Chip, plain

if TYPE_CHECKING:
    from nf_splice.interfaces.tui.app import NfSpliceApp

_TONES = {
    StepState.READY: "good",
    StepState.PUBLISHED: "good",
    StepState.NEEDS_REVIEW: "warn",
    StepState.BLOCKED: "bad",
    StepState.IN_PROGRESS: "info",
    StepState.NOT_STARTED: "",
}


class PageView(VerticalScroll):
    """One task page; renders from the immutable model, never from disk."""

    page_id: ClassVar[str] = ""
    #: The layer whose draft bytes the page's unsaved form was loaded from.
    form_layer: ClassVar[str | None] = None
    help_text: ClassVar[str] = ""

    def __init__(self) -> None:
        super().__init__(id=f"page-{self.page_id}", classes="page")
        self.model: WorkspaceModel | None = None
        #: The draft sha256 a form was filled from (stale-write protection).
        self.loaded_sha: str | None = None
        #: A jump target to focus once the page has been composed.
        self.pending_target: Target | None = None

    @property
    def spec(self) -> Page:
        return page_spec(self.page_id)

    @property
    def workspace(self) -> NfSpliceApp:
        from nf_splice.interfaces.tui.app import NfSpliceApp

        app = self.app
        assert isinstance(app, NfSpliceApp)
        return app

    def compose(self) -> ComposeResult:
        with Horizontal(classes="page-top"):
            with Vertical(classes="page-heading"):
                yield Static(self.spec.title, classes="page-title")
                yield Static(self.spec.lead, classes="page-lead")
                with Horizontal(classes="page-ai"):
                    yield Button(
                        "◇ Ask AI about this screen",
                        id=f"ask-{self.page_id}",
                        classes="compact ai-context",
                    )
                    yield Button(
                        f"✧ {self.spec.assist_label}",
                        id=f"assist-{self.page_id}",
                        classes="compact ai-context",
                    )
            yield Chip("", id=f"tag-{self.page_id}", classes="page-tag")
        yield from self.body()

    def body(self) -> ComposeResult:
        yield from ()

    def on_mount(self) -> None:
        # Runs after a subclass's own on_mount (Textual dispatches along the
        # MRO), so tables and columns exist before the first render.
        if self.workspace.model_ready:
            self.show_model(self.workspace.model)
        if self.pending_target is not None:
            target, self.pending_target = self.pending_target, None
            self.call_after_refresh(self.focus_target, target)

    def show_model(self, model: WorkspaceModel) -> None:
        """Re-render from a new model; keep focus, cursor and unsaved text."""
        self.model = model
        state = model.step_state(self.page_id)
        self.set_tag(self.tag_text(model, state), _TONES[state])
        self.refresh_page(model)

    def tag_text(self, model: WorkspaceModel, state: StepState) -> str:
        return LABELS[state].upper()

    def set_tag(self, text: str, tone: str = "") -> None:
        for chip in self.query(f"#tag-{self.page_id}").results(Chip):
            chip.show(text, tone)

    def refresh_page(self, model: WorkspaceModel) -> None:
        """Subclasses update their widgets here (cheap, in-memory only)."""

    def focus_target(self, target: Target) -> None:
        """Move focus to the field or entry a jump names."""

    def has_unsaved(self) -> bool:
        return False

    def discard_unsaved(self) -> None:
        """Forget unsaved form values so the next refresh shows the file."""
        self.loaded_sha = None

    def selection_label(self) -> str:
        """What is selected, for Ask's context (empty when nothing)."""
        return ""

    def ai_context(self) -> dict[str, Any]:
        return {}

    def say(self, message: str, tone: str = "") -> None:
        self.workspace.set_status(message, tone)

    def stale(self) -> bool:
        """Whether the draft changed on disk since this form was filled."""
        if self.form_layer is None or self.loaded_sha is None:
            return False
        current = self.workspace.current_sha(self.form_layer)
        return current != self.loaded_sha


def stat(value: Any, label: str) -> Static:
    return Static(plain(f"{value}\n{label}"), classes="stat")
