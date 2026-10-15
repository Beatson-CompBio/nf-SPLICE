"""Guided Textual wizard over the shared file-first services (ADR-0038)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, ListView, Markdown, Static

from nf_splice.agents.protocol import AgentProvider
from nf_splice.agents.state import InteractionMode
from nf_splice.domain.audit import ChangeOrigin
from nf_splice.interfaces.tui.screens import VIEWS
from nf_splice.interfaces.tui.state import (
    SessionStore,
    WizardSession,
    WizardSnapshot,
    build_snapshot,
    changed_files,
    repository_key,
)
from nf_splice.interfaces.tui.steps import (
    STEPS,
    next_step,
    previous_step,
    resume_step,
    step,
    unlocked,
)
from nf_splice.interfaces.tui.widgets import ProgressRail, StatusLine, StepView
from nf_splice.layers import ChangeContext
from nf_splice.services.audit import resolve_actor


class HelpScreen(ModalScreen[None]):
    """Contextual F1 help for the current step."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape,f1", "dismiss", "Close")]

    def __init__(self, title: str, text: str) -> None:
        super().__init__()
        self._title = title
        self._text = text

    def compose(self) -> ComposeResult:
        with Vertical(id="help-dialog"):
            yield Markdown(f"# {self._title}\n\n{self._text}")
            yield Button("Close", id="help-close")

    def on_button_pressed(self, _event: Button.Pressed) -> None:
        self.dismiss(None)


class NfSpliceApp(App[None]):
    """Manual, AI-assisted or autonomous authoring of a SPLICE bundle."""

    TITLE = "nf-splice"
    SUB_TITLE = "Guided SPLICE bundle wizard"
    CSS_PATH = "tui.tcss"
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("f1", "help", "Help"),
        Binding("ctrl+n", "continue", "Continue"),
        Binding("escape", "step_back", "Back"),
        Binding("ctrl+d", "defer", "Finish later"),
        Binding("ctrl+r", "reload", "Reload files"),
        Binding("ctrl+a", "assistant", "Ask AI"),
        Binding("ctrl+q", "quit", "Quit"),
    ]

    def __init__(
        self,
        repository: str | Path,
        *,
        sessions: SessionStore | None = None,
        actor: str | None = None,
        start: str | None = None,
        agent_provider: AgentProvider | None = None,
        allow_remote_model: bool = False,
    ) -> None:
        super().__init__()
        self.repository = Path(repository).resolve()
        self.sessions = sessions or SessionStore(None)
        self.actor_label = actor
        self.snapshot = WizardSnapshot(repository=self.repository, status=None)
        self.session = self.sessions.load(self.repository) or WizardSession(
            repository_key=repository_key(self.repository)
        )
        self.current = start or self.session.current_step
        self.inspect_only = False
        self.busy = False
        self.agent_provider = agent_provider
        self.allow_remote_model = allow_remote_model

    # ------------------------------------------------------------ layout

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main"):
            yield ProgressRail(id="rail")
            with Vertical(id="content"):
                yield Static("", id="step-title")
                yield Static("", id="step-explanation")
                yield VerticalScroll(id="body")
                with Horizontal(id="nav"):
                    yield Button("Back", id="nav-back")
                    yield Button("Finish later", id="nav-defer")
                    yield Button("Continue", id="nav-continue", variant="primary")
        yield StatusLine("", id="status")
        yield Footer()

    def on_mount(self) -> None:
        self.snapshot = build_snapshot(self.repository)
        changed = changed_files(self.session, self.snapshot)
        if changed:
            self.set_status(
                "Reloaded drafts changed outside the wizard: " + ", ".join(changed)
            )
        self.show_step(self.current)

    # ------------------------------------------------------------ services

    def change_context(self) -> ChangeContext:
        return ChangeContext(
            actor=resolve_actor(self.actor_label), origin=ChangeOrigin.MANUAL_TUI
        )

    def set_status(self, message: str, *, error: bool = False) -> None:
        self.query_one("#status", StatusLine).show(message, error=error)

    def perform(
        self,
        label: str,
        action: Callable[[], Any],
        *,
        then: Callable[[Any], None] | None = None,
    ) -> None:
        """Run a service call off the event loop, then refresh from disk."""
        if self.inspect_only or self.snapshot.read_only:
            self.set_status("Inspect-only mode: no changes are written.", error=True)
            return
        self.busy = True
        self.set_status(f"{label}…")

        def work() -> None:
            try:
                result = action()
            except Exception as error:
                self.call_from_thread(self._failed, error)
                return
            snapshot = build_snapshot(self.repository)
            self.call_from_thread(self._succeeded, label, result, snapshot, then)

        self.run_worker(work, thread=True, exclusive=True, group="actions")

    def _failed(self, error: Exception) -> None:
        self.busy = False
        self.set_status(str(error), error=True)

    def _succeeded(
        self,
        label: str,
        result: Any,
        snapshot: WizardSnapshot,
        then: Callable[[Any], None] | None,
    ) -> None:
        self.busy = False
        self.apply_snapshot(snapshot)
        self.set_status(f"{label}: done.")
        if then is not None:
            then(result)

    def apply_snapshot(self, snapshot: WizardSnapshot) -> None:
        self.snapshot = snapshot
        self._update_rail()
        view = self.current_view()
        if view is not None:
            view.refresh_view(snapshot)
        self._save_session()

    # ------------------------------------------------------------ navigation

    def current_view(self) -> StepView | None:
        found = list(self.query_one("#body", VerticalScroll).query(StepView))
        return found[0] if found else None

    def _visited(self) -> frozenset[str]:
        return frozenset(self.session.visited)

    def _update_rail(self) -> None:
        self.query_one("#rail", ProgressRail).update_steps(
            self.snapshot,
            self.current,
            self._visited(),
            frozenset(self.session.deferred),
        )

    def show_step(self, step_id: str) -> None:
        target = step(step_id)
        if not unlocked(target, self.snapshot, visited=self._visited()):
            self.set_status(
                f"{target.title} is locked until earlier steps are done.", error=True
            )
            return
        view = self.current_view()
        if view is not None:
            try:
                self.session.unsaved[view.step_id] = view.unsaved()
            except NoMatches:
                pass
            view.remove()
        self.current = step_id
        if step_id not in self.session.visited:
            self.session.visited.append(step_id)
        new_view = VIEWS[step_id]()
        self.query_one("#body", VerticalScroll).mount(new_view)
        self.query_one("#step-title", Static).update(f"[b]{target.title}[/b]")
        self.query_one("#step-explanation", Static).update(target.help)
        self._update_rail()
        self._save_session()

    def _save_session(self) -> None:
        self.session.current_step = self.current
        self.session.file_hashes = dict(self.snapshot.draft_hashes)
        try:
            self.sessions.save(self.repository, self.session)
        except (OSError, ValueError) as error:
            self.set_status(f"session not saved: {error}", error=True)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.item is not None and event.item.id:
            self.show_step(event.item.id.removeprefix("rail-"))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        actions = {
            "nav-back": self.action_step_back,
            "nav-continue": self.action_continue,
            "nav-defer": self.action_defer,
        }
        if event.button.id in actions:
            event.stop()
            actions[event.button.id]()

    def action_continue(self) -> None:
        self.show_step(next_step(self.current, self.snapshot, visited=self._visited()))

    def action_step_back(self) -> None:
        self.show_step(previous_step(self.current))

    def action_defer(self) -> None:
        if self.current not in self.session.deferred:
            self.session.deferred.append(self.current)
        self.set_status(
            f"{step(self.current).title} deferred; publishing stays blocked."
        )
        self.action_continue()

    def action_reload(self) -> None:
        self.apply_snapshot(build_snapshot(self.repository))
        self.set_status("Reloaded current files from disk.")

    def action_help(self) -> None:
        view = self.current_view()
        target = step(self.current)
        self.push_screen(
            HelpScreen(target.title, view.help_text() if view else target.help)
        )

    def action_assistant(self) -> None:
        """Ask AI: read-only contextual help on any step."""
        from nf_splice.interfaces.tui.screens.ask import AskScreen

        self.push_screen(AskScreen(self))

    def open_session(self, mode: InteractionMode) -> None:
        """Open the AI-assisted or autonomous session view."""
        from nf_splice.interfaces.tui.screens.session import SessionScreen

        self.push_screen(SessionScreen(self, mode))

    def resume(self) -> None:
        self.show_step(resume_step(self.snapshot, visited=self._visited()))


__all__ = ["STEPS", "NfSpliceApp"]
