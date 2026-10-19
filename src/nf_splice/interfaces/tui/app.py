"""The unified nf-SPLICE workspace: manual authoring, Ask, Assist and autonomy.

One Textual application, one step rail, one set of drafts (ADR-0067). The AI
assistant is a dock beside every page, driven by one application-owned
:class:`~nf_splice.interfaces.tui.coordinator.AgentCoordinator`. Pages render
an immutable model built in a worker; writes go through the shared layer
services, never from the event loop, and are refused while the agent may be
writing the same drafts.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
from textual.events import Resize
from textual.widgets import Button, Checkbox, ContentSwitcher, Input, Static, TextArea

from nf_splice.agents.protocol import AgentProvider
from nf_splice.agents.providers.readiness import ProviderReadiness
from nf_splice.domain.audit import ActorKind, ChangeOrigin
from nf_splice.interfaces.tui.coordinator import (
    AgentCoordinator,
    AgentSnapshot,
    AgentState,
)
from nf_splice.interfaces.tui.dock import AgentDock
from nf_splice.interfaces.tui.model import (
    ModelCache,
    ReadinessView,
    WorkspaceModel,
    build_model,
    build_readiness,
    empty_model,
)
from nf_splice.interfaces.tui.navigation import (
    LABELS,
    PAGE_IDS,
    Target,
    next_page,
    page,
    previous_page,
    stage_for_page,
)
from nf_splice.interfaces.tui.pages import PAGE_CLASSES, PageView
from nf_splice.interfaces.tui.store import (
    NavigationState,
    NavigationStore,
    repository_key,
)
from nf_splice.interfaces.tui.themes import (
    DEFAULT_THEME,
    THEMES,
    load_theme_preference,
    save_theme_preference,
)
from nf_splice.interfaces.tui.widgets import (
    ActionBar,
    RailItem,
    StatusStrip,
    StepRail,
    TakeoverBar,
    TopBar,
)
from nf_splice.layers import ChangeContext
from nf_splice.services.audit import resolve_actor

#: Terminal sizes (columns) for the responsive layout.
WIDE = 120
#: From this width the AI dock sits beside the page; below it they alternate.
SPLIT = 140
MEDIUM = 80
NARROW = 60
MIN_HEIGHT = 20


class NfSpliceApp(App[Path | None]):
    """Prepare a SPLICE workflow bundle by hand, with AI help, or both.

    ``run()`` returns another working copy to open next (after Welcome
    prepared a safe copy, or the person chose one made earlier), else None.
    """

    TITLE = "nf-SPLICE"
    SUB_TITLE = "Workflow integration"
    CSS_PATH = "tui.tcss"
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("f1", "help", "Help"),
        Binding("ctrl+r", "reload", "Reload files"),
        Binding("ctrl+a", "assistant", "Ask AI / dock"),
        Binding("f6", "switch_pane", "Page ⇄ AI"),
        Binding("ctrl+q", "quit_safely", "Quit", priority=True),
        Binding("escape", "close_dock", "Close dock", show=False),
        Binding("ctrl+right", "step_continue", "Continue", show=False),
        Binding("ctrl+left", "step_back", "Back", show=False),
        *(
            Binding(str(number), f"welcome_option({number})", show=False)
            for number in range(1, 7)
        ),
    ]

    def __init__(
        self,
        repository: str | Path,
        *,
        navigation: NavigationStore | None = None,
        user: str | None = None,
        agent_provider: AgentProvider | None = None,
        allow_remote_model: bool = False,
        start: str | None = None,
        remember_theme: bool = False,
        inspect_only: bool = False,
    ) -> None:
        super().__init__()
        self.repository = Path(repository).resolve()
        self.navigation = navigation or NavigationStore(None)
        self.user = user
        self.remember_theme = remember_theme
        self.inspect_only = inspect_only
        self.saved_state = self.navigation.load(self.repository)
        self.current = start or (
            self.saved_state.current_page if self.saved_state else "welcome"
        )
        if self.current not in PAGE_IDS:
            self.current = "welcome"
        self.model: WorkspaceModel = empty_model(self.repository)
        self.model_ready = False
        self.cache = ModelCache()
        self.readiness: ReadinessView | None = None
        self._generations: dict[str, int] = {}
        self._writing = False
        self._last_busy = False
        self._dock_open = False
        self.coordinator = AgentCoordinator(
            self.repository,
            agent_provider,
            allow_remote_model=allow_remote_model,
            person=user,
            notify=self._agent_notify,
        )
        #: Whether AI can be used (None while it is being checked).
        self.ai_readiness: ProviderReadiness | None = (
            _offline_readiness(agent_provider) if agent_provider else None
        )
        #: Whether the provider came from --provider (kept until AI settings).
        self._explicit_provider = agent_provider is not None
        #: Working copies made earlier from this folder.
        self.known_copies: tuple[str, ...] = ()
        for theme in THEMES:
            self.register_theme(theme)
        self.theme = load_theme_preference() if remember_theme else DEFAULT_THEME

    # ------------------------------------------------------------ layout

    def compose(self) -> ComposeResult:
        yield TopBar(id="topbar")
        with Horizontal(id="main"):
            yield StepRail(id="rail")
            with Vertical(id="workspace"):
                yield TakeoverBar(id="takeover-bar")
                yield ContentSwitcher(id="pages")
                yield ActionBar(id="actionbar")
            yield AgentDock(id="dock")
        yield StatusStrip(id="statusbar")
        yield Static(
            "This terminal is too small for nf-SPLICE. Make it at least 60 "
            "columns by 20 lines; nothing has been changed.",
            id="too-small",
        )

    def on_mount(self) -> None:
        self.query_one("#dock").display = False
        self.query_one("#takeover-bar").display = False
        self.query_one("#too-small").display = False
        self._layout(self.size.width, self.size.height)
        self._show_ai_controls()
        self.coordinator.attach_latest()
        self.show_page(self.current)
        self.set_status("Reading your drafts…")
        self.refresh_model(first=True)
        self.set_interval(0.4, self._poll_agent)
        self._agent_changed()
        self.check_ai()
        if self.inspect_only:
            self.set_status("Inspect-only mode: browsing without writing.", "warn")

    def on_resize(self, event: Resize) -> None:
        self._layout(event.size.width, event.size.height)

    def _layout(self, width: int, height: int) -> None:
        screen = self.screen
        for name in ("wide", "medium", "narrow"):
            screen.remove_class(name)
        tiny = width < NARROW or height < MIN_HEIGHT
        screen.add_class(
            "wide" if width >= WIDE else "medium" if width >= MEDIUM else "narrow"
        )
        screen.set_class(width < SPLIT, "stacked")
        try:
            self.query_one("#rail", StepRail).set_compact(width < WIDE)
            self.query_one("#rail", StepRail).show(
                self.model.step_states(), self.current
            )
        except NoMatches:
            pass
        try:
            self.query_one("#too-small").display = tiny
            self.query_one("#main").display = not tiny
        except NoMatches:
            return

    # ------------------------------------------------------------ status

    def set_status(self, message: str, tone: str = "") -> None:
        try:
            self.query_one("#statusbar", StatusStrip).show(message, tone)
        except NoMatches:
            return

    def change_context(self) -> ChangeContext:
        return ChangeContext(
            actor=resolve_actor(self.user), origin=ChangeOrigin.MANUAL_TUI
        )

    def current_sha(self, layer: str) -> str | None:
        from nf_splice.layers.base import read_layer

        return read_layer(self.repository, layer).file.sha256

    # ------------------------------------------------------------ model

    def _generation(self, name: str) -> int:
        self._generations[name] = self._generations.get(name, 0) + 1
        return self._generations[name]

    def refresh_model(
        self, *, first: bool = False, then: Callable[[], None] | None = None
    ) -> None:
        """Rebuild the model in a worker; only the newest build is applied."""
        generation = self._generation("model")

        def work() -> None:
            try:
                model = build_model(self.repository, self.cache)
            except Exception as error:  # keep the interface usable
                self.call_from_thread(self._model_failed, generation, error)
                return
            self.call_from_thread(self._model_built, generation, model, first, then)

        self.run_worker(work, thread=True, group="model", exclusive=True)

    def _model_failed(self, generation: int, error: Exception) -> None:
        if generation == self._generations.get("model"):
            self.set_status(f"Could not read the drafts: {error}", "bad")

    def _model_built(
        self,
        generation: int,
        model: WorkspaceModel,
        first: bool,
        then: Callable[[], None] | None,
    ) -> None:
        if generation != self._generations.get("model"):
            return
        previous = self.model.key
        self.model = model
        self.model_ready = True
        if previous != model.key:
            self.readiness = (
                None
                if self.readiness and self.readiness.key != model.key
                else self.readiness
            )
        self._apply_model()
        if first and model.authorised:
            from nf_splice.services.source import remember_integration

            remember_integration(model.repository)
        if first:
            changed = (
                self.saved_state is not None
                and self.saved_state.model_key not in ("", model.key)
            )
            self.set_status(
                "Drafts changed outside nf-SPLICE since you last worked here; this "
                "view shows the current files."
                if changed
                else "Ready."
                if model.has_drafts
                else "No drafts yet: start on Welcome."
            )
        if then is not None:
            then()
        self._save_navigation()

    def _apply_model(self) -> None:
        model = self.model
        states = model.step_states()
        if self.coordinator.engine is not None and self.coordinator.busy:
            focus = self.coordinator.snapshot().stage
            if focus:
                for page_id in PAGE_IDS:
                    if stage_for_page(page_id) == focus:
                        from nf_splice.interfaces.tui.navigation import StepState

                        states[page_id] = StepState.IN_PROGRESS
        self.query_one("#rail", StepRail).show(states, self.current)
        current = self.current_page()
        if current is not None and self.model_ready:
            current.show_model(model)
        for view in self.query(PageView):
            if view is not current:
                view.model = None  # re-render when shown again
        self._update_topbar()
        self._update_actionbar()

    def request_readiness(self, *, force: bool = False) -> None:
        """Lifecycle and coverage for the current drafts (in a worker)."""
        if not self.model_ready:
            return
        model = self.model
        if not force and self.readiness is not None and self.readiness.key == model.key:
            self._deliver_readiness()
            return
        if not force and self._generations.get("readiness-key") == hash(model.key):
            return
        self._generations["readiness-key"] = hash(model.key)

        def build() -> ReadinessView:
            return build_readiness(model.repository, model.drafts_valid, model.key)

        def done(view: ReadinessView) -> None:
            self.readiness = view
            self._generations.pop("readiness-key", None)
            self._deliver_readiness()

        self.run_view("readiness", build, done)

    def _deliver_readiness(self) -> None:
        if self.readiness is None:
            return
        for view in self.query(PageView):
            handler = getattr(view, "show_readiness", None)
            if handler is not None and view.model is not None:
                handler(self.readiness)

    def run_view(
        self, name: str, build: Callable[[], Any], done: Callable[[Any], None]
    ) -> None:
        """Build a slower view off the event loop; stale results are dropped."""
        generation = self._generation(name)

        def work() -> None:
            try:
                result = build()
            except Exception as error:
                self.call_from_thread(self._view_failed, name, generation, error)
                return
            self.call_from_thread(self._view_built, name, generation, result, done)

        self.run_worker(work, thread=True, group=f"view-{name}", exclusive=True)

    def _view_built(
        self, name: str, generation: int, result: Any, done: Callable[[Any], None]
    ) -> None:
        if generation == self._generations.get(name):
            done(result)

    def _view_failed(self, name: str, generation: int, error: Exception) -> None:
        if generation == self._generations.get(name):
            self.set_status(f"Could not compute {name}: {error}", "bad")

    # ------------------------------------------------------------ writing

    def write(
        self,
        label: str,
        action: Callable[[], Any],
        *,
        then: Callable[[Any], None] | None = None,
        page: PageView | None = None,
        layer: str | None = None,
        force: bool = False,
    ) -> None:
        """Run a draft write in a worker, after the safety checks.

        Refused in inspect-only mode, while another write runs, while the
        agent may be writing drafts (offering a pause instead), and when the
        draft changed on disk since the form was filled (offering a reload).
        """
        if self.inspect_only or self.model.read_only:
            self.set_status("Inspect-only mode: no changes are written.", "warn")
            return
        if self._writing:
            self.set_status(
                "Another change is still being saved; try again in a moment.", "warn"
            )
            return
        if self.coordinator.writes_locked():
            self._offer_takeover(label)
            return
        if page is not None and layer is not None and not force and page.stale():
            self._stale_write(label, action, then, page, layer)
            return
        self._writing = True
        self.set_status(f"{label}…")
        generation = self._generation("model")

        def work() -> None:
            try:
                result = action()
            except Exception as error:
                self.call_from_thread(self._write_failed, label, error)
                return
            try:
                model = build_model(self.repository, self.cache)
            except Exception as error:
                self.call_from_thread(self._write_failed, label, error)
                return
            self.call_from_thread(self._written, generation, model, result, then)

        self.run_worker(work, thread=True, group="write")

    def _write_failed(self, label: str, error: Exception) -> None:
        self._writing = False
        self.set_status(f"{label} failed; nothing was changed: {error}", "bad")
        self.refresh_model()

    def _written(
        self,
        generation: int,
        model: WorkspaceModel,
        result: Any,
        then: Callable[[Any], None] | None,
    ) -> None:
        self._writing = False
        self.readiness = None
        if generation == self._generations.get("model"):
            self.model = model
            self.model_ready = True
            self._apply_model()
            self._save_navigation()
        else:
            self.refresh_model()
        if then is not None:
            then(result)

    def _stale_write(
        self,
        label: str,
        action: Callable[[], Any],
        then: Callable[[Any], None] | None,
        page: PageView,
        layer: str,
    ) -> None:
        from nf_splice.interfaces.tui.modals import ListDialog

        def chosen(result: Any) -> None:
            if not result:
                return
            choice = result[0]
            if choice == "reload":
                page.loaded_sha = None
                page.discard_unsaved()
                self.refresh_model()
                self.set_status(
                    "Reloaded the draft from disk; your unsaved values were discarded."
                )
            elif choice == "compare":
                self.open_draft(layer, view=True)

        self.push_screen(
            ListDialog(
                "The draft changed on disk",
                f"{label}: the draft was changed outside this form (in an editor, "
                "by the CLI or by the agent) after you started editing. nf-SPLICE "
                "never overwrites it silently.",
                ("Choice", "What happens"),
                (
                    ("Reload", "Discard my unsaved values and show the file"),
                    ("Compare", "Open the current file to compare"),
                    ("Cancel", "Keep editing; nothing is written"),
                ),
                actions=(
                    ("reload", "Reload from file"),
                    ("compare", "Compare"),
                    ("cancel", "Cancel"),
                ),
            ),
            chosen,
        )

    def _offer_takeover(self, label: str) -> None:
        from nf_splice.interfaces.tui.modals import ConfirmDialog

        def chosen(result: Any) -> None:
            if result:
                self.coordinator.request_pause()
                self.set_status(
                    "Pause requested: waiting for a safe checkpoint. You can edit once "
                    "the assistant says PAUSED.",
                    "warn",
                )

        self.push_screen(
            ConfirmDialog(
                "The agent is working on the drafts",
                f"{label} would change a draft the agent may be writing. Request a "
                "pause, wait until the assistant says PAUSED, then make your change. "
                "Nothing has been written.",
                confirm="Request pause & take over",
                cancel="Keep the agent working",
            ),
            chosen,
        )

    def require_person(self, then: Callable[[], None]) -> None:
        """Ask for the person's name once when an action must be attributed."""
        if resolve_actor(self.user).kind is ActorKind.HUMAN:
            then()
            return
        from nf_splice.interfaces.tui.modals import FormDialog

        def done(values: Any) -> None:
            if values and values.get("name"):
                self.user = values["name"]
                self.coordinator.set_person(values["name"])
                then()

        self.push_screen(
            FormDialog(
                "Your name",
                "This decision is recorded with the person who made it. Give the "
                "name to record (never an e-mail address); it is kept for this "
                "session. `nf-splice --user NAME tui` sets it in advance.",
                [("name", "Your name", "")],
                submit="Continue",
                validate=lambda values: None if values.get("name") else "Enter a name.",
            ),
            done,
        )

    # ------------------------------------------------------------ navigation

    def current_page(self) -> PageView | None:
        try:
            return self.query_one(f"#page-{self.current}", PageView)
        except NoMatches:
            return None

    def show_page(self, page_id: str, target: Target | None = None) -> None:
        if page_id not in PAGE_IDS:
            return
        switcher = self.query_one("#pages", ContentSwitcher)
        created = False
        try:
            view = switcher.query_one(f"#page-{page_id}", PageView)
        except NoMatches:
            view = PAGE_CLASSES[page_id]()
            switcher.mount(view)
            created = True
        switcher.current = f"page-{page_id}"
        self.current = page_id
        if not created and self.model_ready and view.model is not self.model:
            view.show_model(self.model)
        self.query_one("#rail", StepRail).show(self.model.step_states(), page_id)
        self._update_actionbar()
        self._save_navigation()
        self.call_after_refresh(self._update_dock_context)
        if page_id == "welcome" and target is None:
            focus_first = getattr(view, "focus_first_option", None)
            if focus_first is not None:
                self.call_after_refresh(focus_first)
        if target is not None and created:
            # A newly mounted page composes later; it focuses on mount.
            view.pending_target = target
        elif target is not None:
            self.call_after_refresh(view.focus_target, target)

    @property
    def stacked(self) -> bool:
        """Whether the page and the AI dock alternate (narrower terminals)."""
        return self.screen.has_class("stacked")

    def jump(self, target: Target) -> None:
        """Open the page and field a Fix button or an intervention names."""
        self.show_page(target.page, target)
        if self._dock_open and self.stacked:
            self.action_close_dock()

    def action_switch_pane(self) -> None:
        """F6: alternate between the page and the AI panel; nothing is lost.

        Below the split width the two take turns at full width; on wide
        terminals F6 moves focus between them. The page keeps its unsaved
        values and the session keeps running either way.
        """
        if not self._dock_open:
            self.open_dock()
            return
        if self.stacked:
            self.action_close_dock()
            return
        dock = self.query_one("#dock", AgentDock)
        if dock.has_focus_within:
            view = self.current_page()
            if view is not None:
                view.focus()
        else:
            dock.focus_first()

    def resume_session(self, note: str = "") -> None:
        """Resume the same session, never over unsaved form values."""
        view = self.current_page()
        if view is not None and view.has_unsaved():
            self.set_status(
                "Save or discard your changes on this page before resuming: the "
                "agent continues from the files on disk.",
                "warn",
            )
            return
        self._guard(lambda: self.coordinator.resume(note))

    def _update_takeover(self, snapshot: AgentSnapshot) -> None:
        try:
            bar = self.query_one("#takeover-bar", TakeoverBar)
        except NoMatches:
            return
        waiting = bool(snapshot.interventions) and not snapshot.busy
        bar.display = waiting and not self._dock_open
        if waiting:
            item = snapshot.interventions[0]
            bar.show(f"! The agent needs you: {item.decision}")

    def _update_actionbar(self) -> None:
        index = PAGE_IDS.index(self.current)
        label = "Review publication →" if self.current == "review" else "Continue →"
        try:
            bar = self.query_one("#actionbar", ActionBar)
        except NoMatches:
            return
        wide = self.screen.has_class("wide")
        bar.show(
            f"Step {index + 1} of {len(PAGE_IDS)}"
            + (" · All changes local" if wide else "")
            if wide or self.screen.has_class("medium")
            else f"{index + 1}/{len(PAGE_IDS)}",
            label,
        )
        bar.query_one("#nav-back").disabled = index == 0
        bar.query_one("#nav-continue").display = self.current != "publish"

    def _save_navigation(self) -> None:
        if self.inspect_only or not (self.model_ready and self.model.authorised):
            # Never write into a folder nobody authorised (or while inspecting).
            return
        try:
            self.navigation.save(
                self.repository,
                NavigationState(
                    repository_key=repository_key(self.repository),
                    current_page=self.current,
                    model_key=self.model.key,
                ),
            )
        except (OSError, ValueError) as error:
            self.set_status(f"Navigation state not saved: {error}", "warn")

    def _update_topbar(self) -> None:
        model = self.model
        pipeline = model.pipeline()
        name = str(pipeline.get("name") or model.repository.name)
        snapshot = self.coordinator.snapshot()
        driving = snapshot.state not in {
            AgentState.STOPPED,
            AgentState.COMPLETED,
            AgentState.READY,
            AgentState.OFF,
        }
        mode = "MANUAL"
        if driving and snapshot.mode == "assisted":
            mode = "AI-ASSISTED"
        elif driving and snapshot.mode == "autonomous":
            mode = "AUTONOMOUS"
        if self.inspect_only:
            mode = "INSPECT ONLY"
        if not model.has_drafts:
            state = ("○ NOT STARTED", "")
        elif model.published and model.drafts_valid:
            state = ("● PUBLISHED", "good")
        elif model.drafts_valid:
            state = ("✓ READY TO PUBLISH", "good")
        else:
            state = ("○ NEEDS REVIEW", "warn")
        self.query_one("#topbar", TopBar).show(name, mode, state, snapshot)
        self._show_ai_controls()

    # ------------------------------------------------------------ AI readiness

    @property
    def ai_usable(self) -> bool:
        """Assisted and Autonomous are offered only for a verified provider."""
        readiness = self.ai_readiness
        return (
            readiness is not None
            and readiness.usable
            and self.coordinator.tools_supported()
        )

    def check_ai(self, *, reconnect: bool = False) -> None:
        """Work out AI readiness off the event loop (it reads the set-up).

        A verified saved provider is connected so the dock can use it; a
        provider given with --provider is kept until AI settings change it.
        """
        explicit = self.coordinator.provider if self._explicit_provider else None
        repository = self.repository

        def build() -> tuple[ProviderReadiness, tuple[str, ...], Any]:
            from nf_splice.agents.providers.readiness import assess
            from nf_splice.services.source import copies_of

            copies = tuple(str(item["path"]) for item in copies_of(repository))
            if explicit is not None:
                return _readiness_of(explicit), copies, None
            readiness = assess()
            agent = None
            if readiness.usable and readiness.provider:
                from nf_splice.agents.providers import provider_for

                agent = provider_for(readiness.provider, model=readiness.model)
            return readiness, copies, agent

        def done(result: tuple[ProviderReadiness, tuple[str, ...], Any]) -> None:
            readiness, copies, agent = result
            self.ai_readiness = readiness
            self.known_copies = copies
            coordinator = self.coordinator
            if not coordinator.busy and not self._explicit_provider:
                if agent is not None and (reconnect or coordinator.provider is None):
                    coordinator.connect(agent)
                elif agent is None and reconnect and coordinator.provider is not None:
                    coordinator.connect(None)
            self._ai_changed()

        self.run_view("AI readiness", build, done)

    def _ai_changed(self) -> None:
        self._show_ai_controls()
        view = self.current_page()
        if view is not None and view.page_id == "welcome" and self.model_ready:
            view.refresh_page(self.model)

    def _show_ai_controls(self) -> None:
        """AI actions appear only where they can actually be used (CSS)."""
        if self.screen_stack:
            self.screen_stack[0].set_class(not self.ai_usable, "ai-off")

    def ai_settings(self) -> None:
        from nf_splice.interfaces.tui.provider_setup import ProviderSetupDialog

        if self.coordinator.busy:
            self.set_status(
                "The agent is working; pause it before changing the AI provider.",
                "warn",
            )
            return

        def closed(_result: Any) -> None:
            self._explicit_provider = False
            self.ai_readiness = None
            self._ai_changed()
            self.check_ai(reconnect=True)

        self.push_screen(ProviderSetupDialog(), closed)

    def start_ai(self, tab: str) -> None:
        """Welcome's Assisted / Autonomous: the same dock and safeguards."""
        if not self.model.authorised:
            self.set_status(
                "Prepare a safe working copy (or authorise this folder) first.", "warn"
            )
            return
        if not self.ai_usable:
            self.set_status(
                "AI assistance is not verified yet: open AI provider settings.", "warn"
            )
            return
        self.open_dock(tab)

    # ------------------------------------------------------------ working copy

    def switch_to(self, path: str | Path) -> None:
        """Close this workspace and open another working copy, on Welcome."""
        if self.coordinator.busy:
            self.set_status("Pause the agent before opening another copy.", "warn")
            return
        self._save_navigation()
        self.exit(result=Path(path))

    def prepare_copy(self) -> None:
        """Make the safe integration copy, then reopen the workspace there."""
        from nf_splice.interfaces.tui.modals import ConfirmDialog
        from nf_splice.services.source import default_destination

        source = self.repository
        destination = default_destination(str(source))

        def work() -> None:
            from nf_splice.services.source import (
                prepare_integration_copy,
                remember_integration,
            )

            try:
                copy = prepare_integration_copy(str(source))
            except Exception as error:
                self.call_from_thread(self._prepare_failed, str(error))
                return
            remember_integration(Path(copy.path))
            self.call_from_thread(self.switch_to, copy.path)

        def confirmed(result: Any) -> None:
            if result:
                self.set_status(f"Preparing the working copy {destination}…")
                self.run_worker(work, thread=True, group="prepare")

        self.push_screen(
            ConfirmDialog(
                "Prepare a safe working copy?",
                f"nf-SPLICE copies {source} to {destination}"
                + (
                    " and works on its own local Git branch"
                    if (source / ".git").exists()
                    else " and records it in a new local Git repository"
                )
                + ". The original folder is not changed. The workspace then "
                "opens on the copy.",
                confirm="Prepare the copy",
            ),
            confirmed,
        )

    def _prepare_failed(self, message: str) -> None:
        from nf_splice.interfaces.tui.modals import HelpDialog

        self.set_status("The working copy was not created; nothing changed.", "bad")
        self.push_screen(
            HelpDialog(
                "The working copy was not created",
                f"{message}\n\nYou can also prepare it from the command line "
                "(choosing the folder with --into PATH), which then opens the "
                f"workspace on the copy: `nf-splice source prepare {self.repository}`",
            )
        )

    def authorise_in_place(self) -> None:
        from nf_splice.interfaces.tui.modals import ConfirmDialog

        def work() -> None:
            from nf_splice.services.source import (
                authorise_in_place,
                remember_integration,
            )

            authorise_in_place(self.repository)
            remember_integration(self.repository)

        def confirmed(result: Any) -> None:
            if not result:
                return

            def done(_result: Any = None) -> None:
                self.cache.invalidate()
                self.refresh_model(
                    then=lambda: self.set_status(
                        "This folder is authorised for in-place authoring.", "warn"
                    )
                )

            self.run_view("in-place consent", work, done)

        self.push_screen(
            ConfirmDialog(
                "Work in the original folder?",
                f"nf-SPLICE will write splice/, .splice-local/ and a .gitignore rule "
                f"in {self.repository} itself, rather than in a safe copy. Your "
                "consent is recorded in .splice-local/integration.json.",
                confirm="Work in this folder",
                danger=True,
            ),
            confirmed,
        )

    # ------------------------------------------------------------ agent

    def _agent_notify(self) -> None:
        """Called by the coordinator from any thread."""
        if threading.get_ident() == getattr(self, "_thread_id", None):
            self._agent_changed()
            return
        try:
            self.call_from_thread(self._agent_changed)
        except RuntimeError:
            return

    def _poll_agent(self) -> None:
        if self.coordinator.busy or self.coordinator.asking or self._last_busy:
            self._agent_changed()

    def _agent_changed(self) -> None:
        try:
            snapshot = self.coordinator.snapshot()
        except Exception as error:
            self.set_status(f"Agent state unavailable: {error}", "bad")
            return
        busy = snapshot.busy
        if self._last_busy and not busy:
            # The agent may have changed drafts: show the current files.
            self.cache.invalidate()
            self.refresh_model()
        self._last_busy = busy
        try:
            self._update_topbar()
            self.query_one("#dock", AgentDock).render_snapshot(snapshot)
        except NoMatches:
            return
        self._update_takeover(snapshot)

    def _update_dock_context(self) -> None:
        view = self.current_page()
        try:
            selection = view.selection_label() if view is not None else ""
        except NoMatches:  # the page is still being composed
            selection = ""
        try:
            self.query_one("#dock", AgentDock).set_context(self.current, selection)
        except NoMatches:
            return

    def open_dock(self, tab: str | None = None) -> None:
        dock = self.query_one("#dock", AgentDock)
        dock.display = True
        self._dock_open = True
        self._update_dock_context()
        dock.show_tab(tab or dock.tab)
        snapshot = self.coordinator.snapshot()
        dock.render_snapshot(snapshot)
        self.screen.add_class("dock-open")
        self._update_takeover(snapshot)
        if self.stacked:
            dock.focus_first()

    def action_close_dock(self) -> None:
        """Presentation only: a running session keeps running."""
        if not self._dock_open:
            return
        self.query_one("#dock").display = False
        self._dock_open = False
        self.screen.remove_class("dock-open")
        self._update_takeover(self.coordinator.snapshot())
        view = self.current_page()
        if view is not None:
            view.focus()

    def action_assistant(self) -> None:
        if self._dock_open:
            self.action_close_dock()
        else:
            self.open_dock("ask")

    def _guard(self, action: Callable[[], None]) -> None:
        try:
            action()
        except PermissionError as error:
            self.open_dock()
            self.set_status(str(error), "warn")
            try:
                self.query_one("#dock-person", Input).focus()
            except NoMatches:
                pass
        except Exception as error:
            self.set_status(str(error), "bad")
        self._agent_changed()

    def start_assist(self, stage: str, guidance: str = "") -> None:
        self.open_dock("assist")
        self._guard(lambda: self.coordinator.assist(stage, guidance))

    def _assist_here(self) -> None:
        dock = self.query_one("#dock", AgentDock)
        stage = stage_for_page(self.current)
        if self.current in {"welcome", "overview"}:
            stage = "identity"
        if self.current == "review":
            self.open_dock("assist")
            self.set_status("Choose a blocker on Review and press Propose a fix.")
            return
        if self.current == "publish" or stage is None:
            self.open_dock("ask")
            dock.query_one("#ask-question").focus()
            return
        guidance = dock.text("#assist-guidance", clear=True)
        view = self.current_page()
        if (
            dock.query_one("#assist-selection", Checkbox).value
            and view is not None
            and view.selection_label()
        ):
            guidance = f"Focus on: {view.selection_label()}. {guidance}".strip()
        self.start_assist(stage, guidance)

    def _ask(self, text: str = "") -> None:
        dock = self.query_one("#dock", AgentDock)
        question = text or dock.text("#ask-question")
        if not question:
            question = page(self.current).ask_example
        context = dock.context()
        view = self.current_page()
        if view is not None:
            context |= view.ai_context()
        self._guard(lambda: self.coordinator.ask(question, context))

    def _dock_button(self, identifier: str) -> bool:
        coordinator = self.coordinator
        dock = self.query_one("#dock", AgentDock)
        if identifier in {"dock-close", "dock-back"}:
            self.action_close_dock()
        elif identifier == "takeover-return":
            self.open_dock(
                "autonomous"
                if coordinator.snapshot().mode == "autonomous"
                else "assist"
            )
        elif identifier == "takeover-resume":
            self.resume_session()
        elif identifier.startswith("dock-tab-"):
            dock.show_tab(identifier.removeprefix("dock-tab-"))
        elif identifier == "ask-send":
            self._ask()
        elif identifier == "ask-example":
            dock.query_one("#ask-question", TextArea).text = page(
                self.current
            ).ask_example
        elif identifier == "ask-cancel":
            coordinator.cancel_answer()
        elif identifier == "ask-to-assist":
            dock.show_tab("assist")
        elif identifier == "assist-start":
            self._assist_here()
        elif identifier in {"assist-pause", "auto-pause"}:
            self._guard(coordinator.request_pause)
            self.set_status("Pause requested: waiting for a safe checkpoint.", "warn")
        elif identifier == "proposal-approve":
            self._guard(coordinator.approve)
        elif identifier == "proposal-revise":
            text = dock.text("#proposal-revision")
            if not text:
                self.set_status("Say what should change in the proposal first.", "warn")
                return True
            self._guard(
                lambda: coordinator.revise(dock.text("#proposal-revision", clear=True))
            )
        elif identifier == "proposal-reject":
            self._guard(
                lambda: coordinator.reject(dock.text("#proposal-revision", clear=True))
            )
        elif identifier == "proposal-diff-view":
            proposal = coordinator.snapshot().proposal
            if proposal is not None:
                self.view_text(
                    f"Proposed changes ({proposal.id})",
                    proposal.diff or "(no diff)",
                    language="diff",
                )
        elif identifier in {"proposal-manual", "question-edit", "paused-manual"}:
            snapshot = coordinator.snapshot()
            stage = (
                snapshot.proposal.stage if snapshot.proposal else None
            ) or snapshot.stage
            target = (
                snapshot.interventions[0].target
                if snapshot.interventions
                else Target(self._page_for_stage(stage))
            )
            self.jump(target)
            self.set_status(
                "Edit the draft here. A pending proposal is withdrawn if the draft "
                "changes before you approve it."
            )
        elif identifier == "question-answer":
            text = dock.text("#question-reply", clear=True)
            self._guard(lambda: coordinator.reply(text))
        elif identifier in {"question-resume", "paused-resume", "intervention-resume"}:
            self.resume_session(dock.text("#intervention-note", clear=True))
        elif identifier == "intervention-answer":
            text = dock.text("#intervention-note", clear=True)
            if not text:
                self.set_status("Type your answer first.", "warn")
                return True
            if coordinator.snapshot().mode == "assisted":
                self._guard(lambda: coordinator.reply(text))
            else:
                self._guard(lambda: coordinator.resume(f"answer: {text}"))
        elif identifier == "intervention-skip":
            text = dock.text("#intervention-note", clear=True)
            if not text:
                self.set_status("Say why the decision is skipped first.", "warn")
                return True
            self._guard(lambda: coordinator.resume(f"skipped: {text}"))
        elif identifier == "intervention-open":
            snapshot = coordinator.snapshot()
            if snapshot.interventions:
                self.jump(snapshot.interventions[0].target)
        elif identifier == "intervention-evidence":
            snapshot = coordinator.snapshot()
            lines = []
            for item in snapshot.interventions:
                lines += [
                    f"## {item.stage_title}: {item.decision}",
                    f"Why: {item.reason}",
                    "Examined:",
                    *(f"- {value}" for value in item.evidence),
                    "Uncertain:",
                    *(f"- {value}" for value in item.uncertainties),
                    f"Suggestion: {item.suggestion}",
                    f"Field: {item.pointer or item.artefact}",
                    f"Checkpoint: {item.checkpoint or 'none'}",
                    "Technical details:",
                    *(f"  {value}" for value in item.diagnostics),
                    "",
                ]
            lines += ["## Recent activity", *snapshot.activity]
            self.view_text("Intervention evidence", "\n".join(lines))
        elif identifier in {"intervention-stop", "auto-stop", "paused-stop"}:
            self._confirm_stop()
        elif identifier == "paused-assist":
            dock.show_tab("assist")
        elif identifier == "paused-scope":
            dock.show_scope(True)
            dock.render_snapshot(coordinator.snapshot())
        elif identifier == "auto-start":
            self._start_autonomous()
        elif identifier == "finished-review":
            self.show_page("review")
        elif identifier == "finished-validate":
            self.action_reload()
        elif identifier == "finished-publish":
            self.show_page("publish")
        else:
            return False
        return True

    def _page_for_stage(self, stage: str | None) -> str:
        if stage is None:
            return self.current
        for page_id in PAGE_IDS:
            if stage_for_page(page_id) == stage:
                return page_id
        return "review"

    def _start_autonomous(self) -> None:
        dock = self.query_one("#dock", AgentDock)
        grants = dock.grants()
        budget = dock.budget()

        def go() -> None:
            dock.show_scope(False)
            self.coordinator.start_autonomous(grants, budget)
            self.set_status("Autonomous session started within the approved scope.")

        self._guard(go)

    def _confirm_stop(self) -> None:
        from nf_splice.interfaces.tui.modals import ConfirmDialog

        def chosen(result: Any) -> None:
            if result:
                self._guard(self.coordinator.stop)
                self.set_status(
                    "Stopping at the next safe point; the session will not resume."
                )

        self.push_screen(
            ConfirmDialog(
                "Stop the session for good?",
                "Stopping cancels this session at its next safe point. Its changes so "
                "far stay in the drafts, but a stopped session is never resumed: you "
                "would start a new one. To continue later instead, use Request pause.",
                confirm="Stop the session",
                danger=True,
            ),
            chosen,
        )

    def on_checkbox_changed(self, event: Any) -> None:
        if getattr(event.checkbox, "id", None) == "dock-consent":
            self.coordinator.consent(bool(event.value))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "dock-person" and event.value.strip():
            self.user = event.value.strip()
            self.coordinator.set_person(self.user)
            self.set_status(f"Changes and approvals are recorded as {self.user}.")

    # ------------------------------------------------------------ buttons

    def on_button_pressed(self, event: Button.Pressed) -> None:
        identifier = event.button.id or ""
        if isinstance(event.button, RailItem):
            event.stop()
            self.show_page(event.button.page_id)
            return
        simple: dict[str, Callable[[], None]] = {
            "nav-back": self.action_step_back,
            "nav-continue": self.action_step_continue,
            "nav-later": self.action_finish_later,
            "agent-status": lambda: self.open_dock(),
            "top-ask": lambda: self.open_dock("ask"),
            "top-assist": lambda: self.open_dock("assist"),
            "top-autonomous": lambda: self.open_dock("autonomous"),
            "tool-drafts": self.action_drafts,
            "tool-sources": self.action_sources,
            "tool-theme": self.action_theme,
            "tool-help": self.action_help,
            "welcome-start": self.start_manually,
            "welcome-prepare": self.prepare_copy,
            "welcome-open-copy": lambda: self.switch_to(self.known_copies[0]),
            "welcome-in-place": self.authorise_in_place,
            "welcome-inspect": self.inspect,
            "welcome-setup-ai": self.ai_settings,
            "welcome-ai-settings": self.ai_settings,
            "welcome-assisted": lambda: self.start_ai("assist"),
            "welcome-autonomous": lambda: self.start_ai("autonomous"),
            "welcome-exit": self.action_quit_safely,
            "overview-browse": self.action_sources,
            "overview-fresh": self.start_fresh,
        }
        if identifier in simple:
            event.stop()
            simple[identifier]()
            return
        if (
            identifier.startswith("ask-")
            and identifier.removeprefix("ask-") in PAGE_IDS
        ):
            event.stop()
            self.open_dock("ask")
            return
        if (
            identifier.startswith("assist-")
            and identifier.removeprefix("assist-") in PAGE_IDS
        ):
            event.stop()
            self.open_dock("assist")
            return
        if self._dock_button(identifier):
            event.stop()

    # ------------------------------------------------------------ actions

    def action_welcome_option(self, number: int) -> None:
        """Welcome's numbered options (text fields keep their digits)."""
        view = self.current_page()
        if self.screen is self.screen_stack[0] and view is not None:
            choose = getattr(view, "action_option", None)
            if choose is not None:
                choose(number)

    def action_step_continue(self) -> None:
        if self.current == "review" and not self.model.drafts_valid:
            self.set_status(
                "Publishing is blocked until Review is clear; you can still look.",
                "warn",
            )
        self.show_page(next_page(self.current))

    def action_step_back(self) -> None:
        self.show_page(previous_page(self.current))

    def action_reload(self) -> None:
        self.cache.invalidate()
        self.readiness = None
        self.refresh_model(
            then=lambda: self.set_status("Reloaded the current files from disk.")
        )

    def action_help(self) -> None:
        from nf_splice.interfaces.tui.modals import HelpDialog

        view = self.current_page()
        text = (view.help_text if view is not None else "") or page(self.current).lead
        text += (
            "\n\n---\n**Keys:** F1 help · Ctrl+P commands and theme · Ctrl+R reload "
            "files · Ctrl+A open or close the AI assistant · Ctrl+Q quit · Tab moves "
            "between controls · Enter activates."
        )
        self.push_screen(HelpDialog(page(self.current).title, text))

    def action_theme(self) -> None:
        from nf_splice.interfaces.tui.modals import ThemeDialog

        def chosen(name: Any) -> None:
            if name:
                self.theme = name
                if self.remember_theme:
                    save_theme_preference(name)
                self.set_status(f"Theme: {name}")

        self.push_screen(ThemeDialog(), chosen)

    def watch_theme(self, name: str) -> None:
        if self.remember_theme and name in {theme.name for theme in THEMES}:
            save_theme_preference(name)

    def action_finish_later(self) -> None:
        unsaved = [
            view.spec.title for view in self.query(PageView) if view.has_unsaved()
        ]

        def leave(result: Any = True) -> None:
            if result:
                self._save_navigation()
                self._exit_safely("Saved your place. Nothing was published.")

        if unsaved:
            from nf_splice.interfaces.tui.modals import ConfirmDialog

            self.push_screen(
                ConfirmDialog(
                    "Leave with unsaved changes?",
                    "Unsaved changes on: " + ", ".join(unsaved) + ". They are not "
                    "written to the drafts if you leave now.",
                    confirm="Leave without saving",
                    cancel="Stay",
                    danger=True,
                ),
                leave,
            )
        else:
            leave()

    def action_quit_safely(self) -> None:
        self.action_finish_later()

    def _exit_safely(self, message: str) -> None:
        if not self.coordinator.busy:
            self.exit(message=message)
            return
        from nf_splice.interfaces.tui.modals import QuitDialog

        def chosen(result: Any) -> None:
            if not result:
                return
            self.set_status("Waiting for the agent to reach a safe checkpoint…", "warn")

            def wait() -> None:
                self.coordinator.shutdown(timeout=600)
                self.call_from_thread(
                    lambda: self.exit(message="The session is paused; resume it later.")
                )

            self.run_worker(wait, thread=True, group="shutdown")

        self.push_screen(QuitDialog(), chosen)

    def start_manually(self) -> None:
        """Create the drafts once (existing drafts are kept), then Overview.

        With drafts already in place it continues at the first step that is
        not ready yet.
        """
        if self.model.all_drafts:
            self.resume_work()
            return
        if self.inspect_only or self.model.read_only:
            self.set_status("Inspect-only mode: drafts are not created.", "warn")
            return
        if not self.model.authorised:
            self.set_status(
                "This is the original pipeline: prepare a safe working copy first, "
                "or choose to work in this folder.",
                "warn",
            )
            return
        from nf_splice.services.workspace import initialise

        self.set_status("Preparing your editable drafts…")
        button = self.query_one("#welcome-start", Button)
        button.disabled = True

        def done(_result: Any) -> None:
            button.disabled = False
            self.show_page("overview")
            self.set_status(
                "Your six drafts are ready in .splice-local/drafts/.", "good"
            )

        def write() -> Any:
            return initialise(self.repository, self.change_context())

        self.write("Preparing your editable drafts", write, then=done)

    def resume_work(self) -> None:
        states = self.model.step_states()
        for page_id in PAGE_IDS[2:]:
            if states[page_id].value not in {"ready", "published"}:
                self.show_page(page_id)
                return
        self.show_page("review")

    def inspect(self) -> None:
        self.inspect_only = True
        self._update_topbar()
        self.set_status("Inspect-only mode: browsing without writing.", "warn")
        self.show_page("overview")

    def start_fresh(self) -> None:
        from nf_splice.interfaces.tui.modals import ConfirmDialog
        from nf_splice.services.workspace import start_fresh

        def confirmed(result: Any) -> None:
            if not result:
                return
            self.write(
                "Starting fresh from exact metadata",
                lambda: start_fresh(self.repository, self.change_context()),
                then=lambda report: self.set_status(
                    f"Backed up the previous drafts to {report.backup} and recreated "
                    "them from exact metadata.",
                    "good",
                ),
            )

        self.push_screen(
            ConfirmDialog(
                "Start fresh from exact metadata?",
                "Every current draft and config is copied to a private backup under "
                ".splice-local/backups/, then the drafts are recreated from exact "
                "metadata only. Your published splice/ files are not touched. You "
                "can restore the backup by copying it back.",
                confirm="Back up and start fresh",
                danger=True,
            ),
            confirmed,
        )

    # ------------------------------------------------------------ tools

    def view_text(
        self,
        title: str,
        text: str,
        *,
        path: Path | None = None,
        language: str | None = None,
    ) -> None:
        from nf_splice.interfaces.tui.modals import ViewerDialog

        def closed(result: Any) -> None:
            if result == "edited":
                self.action_reload()

        self.push_screen(
            ViewerDialog(title, text, path=path, language=language), closed
        )

    def view_file(self, relative: str) -> None:
        path = (self.repository / relative).resolve()
        if not path.is_relative_to(self.repository) or not path.is_file():
            self.set_status(
                f"{relative} is not a readable file in this repository.", "warn"
            )
            return

        def read() -> str:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                return handle.read(2_000_000)

        self.run_view(
            "file", read, lambda text: self.view_text(relative, text, path=path)
        )

    def edit_file(self, path: Path) -> None:
        from nf_splice.interfaces.tui.modals import open_in_editor

        if self.coordinator.writes_locked():
            self._offer_takeover(f"Editing {path.name}")
            return
        self.set_status(open_in_editor(self, path))
        self.action_reload()

    def open_draft(self, layer: str, *, view: bool = False) -> None:
        from nf_splice.layers.base import layer_spec

        path = self.repository / layer_spec(layer).draft
        if view or not path.is_file():
            self.view_file(layer_spec(layer).draft)
        else:
            self.edit_file(path)

    def action_drafts(self) -> None:
        from nf_splice.interfaces.tui.modals import ListDialog

        layers = list(self.model.layers.values())
        labels = {
            "bundle": "Identity and assays",
            "inputs": "Parameters",
            "outputs": "Outputs",
            "components": "Software & containers",
            "execution-profiles": "Execution",
            "provenance": "Provenance",
        }
        configs = sorted(self.model.configs)
        rows = [
            (
                labels.get(item.name, item.name),
                item.path,
                "missing"
                if not item.exists
                else "malformed"
                if item.malformed
                else f"{len(item.errors)} error(s)"
                if item.errors
                else "valid",
            )
            for item in layers
        ] + [
            (
                "Execution config",
                f".splice-local/drafts/configs/{name}",
                "native config",
            )
            for name in configs
        ]
        paths = [item.path for item in layers] + [
            f".splice-local/drafts/configs/{name}" for name in configs
        ]

        def chosen(result: Any) -> None:
            if not result or result[1] is None:
                return
            action, index = result
            relative = paths[index]
            if action == "view":
                self.view_file(relative)
            elif action == "edit":
                self.edit_file(self.repository / relative)

        self.push_screen(
            ListDialog(
                "Authoritative YAML drafts",
                "The drafts in .splice-local/drafts/ are the source of truth; every "
                "screen is a view over them. Edit them in any editor: nf-SPLICE "
                "reloads them and never overwrites your edits silently.",
                ("Step", "File", "State"),
                rows,
                actions=(("view", "View"), ("edit", "Open in editor")),
            ),
            chosen,
        )

    def action_sources(self) -> None:
        from nf_splice.interfaces.tui.sources import list_sources

        def show(entries: list[tuple[str, str, str]]) -> None:
            from nf_splice.interfaces.tui.modals import ListDialog

            def chosen(result: Any) -> None:
                if result and result[1] is not None:
                    self.view_file(entries[result[1]][0])

            self.push_screen(
                ListDialog(
                    "Browse pipeline sources",
                    "Recognised file types only. Exact keys are read from structured "
                    "metadata; documentation such as the README is for you to read, "
                    "never copied into a field.",
                    ("Path", "Kind", "Size"),
                    entries,
                    actions=(("view", "Preview"),),
                ),
                chosen,
            )

        self.run_view("sources", lambda: list_sources(self.repository), show)

    def browse_routes(self) -> None:
        from nf_splice.interfaces.tui.sources import route_rows

        def show(rows: list[tuple[str, str, str, str]]) -> None:
            from nf_splice.interfaces.tui.modals import ListDialog

            def chosen(result: Any) -> None:
                if not result or result[1] is None:
                    return
                action, index = result
                _status, instance, glob, _where = rows[index]
                if action == "add":
                    view = self.current_page()
                    if hasattr(view, "edit"):
                        example = glob.replace("*", "EXAMPLE")
                        view.edit(None, mode="add", example=example)  # type: ignore[union-attr]
                elif action == "exclude":
                    self.exclude_route(instance, glob)

            self.push_screen(
                ListDialog(
                    "Published routes (read-only evidence)",
                    "Routes the pipeline's code publishes, and whether an output "
                    "covers them. Nothing here is written to your catalogue unless "
                    "you add an output or exclude a route with a reason.",
                    ("Coverage", "Process", "Published path", "Declared at"),
                    rows,
                    actions=(
                        ("add", "Add an output for it"),
                        ("exclude", "Exclude it…"),
                    ),
                ),
                chosen,
            )

        self.run_view("routes", lambda: route_rows(self.repository), show)

    def exclude_route(self, instance: str, glob: str) -> None:
        from nf_splice.interfaces.tui.modals import FormDialog
        from nf_splice.layers.base import edit_draft, ops_for

        def done(values: Any) -> None:
            if not values:
                return
            data = self.model.layer("outputs").data
            existing = list(data.get("excluded_routes") or [])
            entry = {"glob": glob, "kind": values["kind"], "reason": values["reason"]}
            self.write(
                f"Excluding {glob}",
                lambda: edit_draft(
                    self.repository,
                    "outputs",
                    ops_for(data, {"/excluded_routes": [*existing, entry]}),
                    self.change_context(),
                    action="exclude_route",
                ),
                then=lambda _r: self.set_status(
                    f"Excluded {glob} with your reason.", "good"
                ),
            )

        self.push_screen(
            FormDialog(
                f"Exclude {glob}",
                f"{instance} publishes this path. Say why it is not in the catalogue; "
                "the reason is kept in outputs.draft.yaml.",
                [
                    (
                        "kind",
                        "Why",
                        (
                            [
                                (
                                    "intermediate",
                                    "An intermediate SPLICE need not show",
                                ),
                                (
                                    "false_positive",
                                    "Static analysis is wrong: it is not published",
                                ),
                                ("out_of_scope", "Outside this integration's scope"),
                            ],
                            None,
                        ),
                    ),
                    ("reason", "Reason", ""),
                ],
                submit="Exclude route",
                validate=lambda values: (
                    None
                    if values.get("kind") and values.get("reason")
                    else "Choose why and give a reason."
                ),
            ),
            done,
        )

    def suggest_assay(self) -> None:
        from nf_splice.interfaces.tui.modals import FormDialog

        contact = support_contact()

        def done(values: Any) -> None:
            if not values:
                return
            text = (
                "SPLICE assay vocabulary suggestion\n"
                f"Assay: {values['name']}\nDescription: {values['description']}\n"
                f"Pipeline: {self.model.pipeline().get('name') or self.repository.name}"
            )
            self.copy_to_clipboard(text)
            self.set_status(
                (
                    f"Suggestion copied; send it to {contact}."
                    if contact
                    else "Suggestion copied. Contact details are not configured: "
                    "share it with your SPLICE team."
                )
                + " It is not added to the vocabulary automatically.",
                "good",
            )

        self.push_screen(
            FormDialog(
                "Suggest an assay addition",
                (
                    f"Suggestions go to {contact}."
                    if contact
                    else "Contact details are not configured "
                    "(NF_SPLICE_SUPPORT_CONTACT). The suggestion is copied so you "
                    "can share it."
                )
                + " A suggestion is not added to the governed vocabulary "
                "automatically.",
                [("name", "Assay name", ""), ("description", "Short description", "")],
                submit="Copy suggestion",
                validate=lambda values: (
                    None if values.get("name") else "Name the assay."
                ),
            ),
            done,
        )

    def export_bundle(self) -> None:
        from nf_splice.interfaces.tui.modals import ConfirmDialog
        from nf_splice.services.export import export_archive

        def confirmed(result: Any) -> None:
            if result:
                self.write(
                    "Exporting a verified ZIP",
                    lambda: export_archive(self.repository, overwrite=True),
                    then=lambda report: self.set_status(
                        f"Exported and verified {report.path}", "good"
                    ),
                )

        self.push_screen(
            ConfirmDialog(
                "Export a ZIP of the bundle?",
                "Writes a verified ZIP of splice/ into .splice-local/exports/ "
                "(replacing an earlier export). Private drafts are never included.",
                confirm="Export ZIP",
            ),
            confirmed,
        )

    def commit_bundle(self) -> None:
        from nf_splice.interfaces.tui.modals import FormDialog
        from nf_splice.services.gitops import commit

        def done(values: Any) -> None:
            if values and values.get("message"):
                self.write(
                    "Committing splice/ locally",
                    lambda: commit(self.repository, values["message"]),
                    then=lambda result: self.set_status(
                        f"Committed locally: {result.get('commit') or result}. "
                        "Nothing was pushed.",
                        "good",
                    ),
                )

        self.push_screen(
            FormDialog(
                "Commit the bundle locally",
                "Commits only the validated splice/ to this working copy's current "
                "branch. Private drafts are never committed and nothing is pushed.",
                [("message", "Commit message", "Add SPLICE workflow bundle")],
                submit="Commit locally",
            ),
            done,
        )


def support_contact() -> str | None:
    """The configured SPLICE support contact, if any (never invented)."""
    import os

    value = os.environ.get("NF_SPLICE_SUPPORT_CONTACT", "").strip()
    return value or None


__all__ = ["LABELS", "AgentSnapshot", "NfSpliceApp"]


def _offline_readiness(provider: AgentProvider) -> ProviderReadiness | None:
    """An offline scripted provider is ready at once; others are checked."""
    from nf_splice.agents.providers.scripted import ScriptedProvider

    return _readiness_of(provider) if isinstance(provider, ScriptedProvider) else None


def _readiness_of(provider: AgentProvider) -> ProviderReadiness:
    """The readiness of a provider object given with --provider (or a test)."""
    from nf_splice.agents.providers import canonical
    from nf_splice.agents.providers.readiness import ReadinessLevel, assess
    from nf_splice.agents.providers.scripted import ScriptedProvider

    capabilities = provider.capabilities
    if isinstance(provider, ScriptedProvider):
        return ProviderReadiness(
            ReadinessLevel.VERIFIED,
            capabilities.name,
            None,
            inference="remote" if capabilities.remote else "offline (no model)",
            billing="none",
            detail="Offline replay of a script: nothing to verify.",
        )
    return assess(canonical(capabilities.name), getattr(provider, "model", None))
