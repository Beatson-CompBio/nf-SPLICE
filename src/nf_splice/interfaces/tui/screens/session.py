"""AI-assisted and autonomous sessions in the wizard.

Both views drive the same :class:`~nf_splice.agents.SessionEngine` as the
``nf-splice session`` commands, against the same session files, so a session
started here can be continued from the terminal and the other way round.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Markdown, Static, Switch

from nf_splice.agents import (
    Budgets,
    ExecutionPolicy,
    InteractionMode,
    Permission,
    SessionEngine,
    SessionStatus,
    SessionStore,
)
from nf_splice.agents.prompts import proposal_text
from nf_splice.agents.report import report_text
from nf_splice.agents.stages import ORDER, StageStatus, spec
from nf_splice.domain.audit import ActorKind
from nf_splice.interfaces.tui.screens.ask import ASSISTANT_OFF
from nf_splice.services.audit import resolve_actor

if TYPE_CHECKING:
    from nf_splice.interfaces.tui.app import NfSpliceApp

_GLYPH = {
    StageStatus.COMPLETED: "✓",
    StageStatus.BLOCKED: "!",
    StageStatus.NEEDS_APPROVAL: "?",
    StageStatus.EXECUTING: "…",
    StageStatus.REPAIRING: "…",
    StageStatus.VALIDATION_FAILED: "!",
}
_FINISHED = {SessionStatus.COMPLETED, SessionStatus.CANCELLED, SessionStatus.BLOCKED}

SCOPE = {
    InteractionMode.ASSISTED: (
        "## AI-assisted session\n\n"
        "The agent works through the integration stage by stage. For each stage "
        "it shows the exact changes, the evidence, the uncertainties and the "
        "validation outcome; **nothing changes until you approve**. You can "
        "object, ask questions or answer its questions at any point."
    ),
    InteractionMode.AUTONOMOUS: (
        "## Autonomous integration\n\n"
        "The agent works through every stage **without asking**, within the "
        "scope you approve below: local, reversible draft edits through "
        "nf-splice's own services, each validated and audited as the agent's "
        "decision. It never runs your pipeline, installs software, uploads "
        "data or reads secrets. Anything it cannot decide with evidence is "
        "reported as a blocker you can resolve afterwards in an assisted "
        "session."
    ),
}


class SessionScreen(ModalScreen[None]):
    """Start, follow and steer one session."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "close", "Close")]

    def __init__(self, wizard: NfSpliceApp, mode: InteractionMode) -> None:
        super().__init__()
        self.wizard = wizard
        self.mode = mode
        self.engine: SessionEngine | None = None
        self.running = False

    # -------------------------------------------------------- layout

    def compose(self) -> ComposeResult:
        with Vertical(id="session-dialog"):
            yield Static("", id="session-title")
            if self.wizard.agent_provider is None:
                yield Markdown(ASSISTANT_OFF, id="session-off")
                yield Button("Close", id="session-close")
                return
            with Vertical(id="session-start"):
                yield Markdown(SCOPE[self.mode])
                yield Input(
                    value=self.wizard.actor_label or "",
                    placeholder="Your name (recorded as the person approving)",
                    id="session-actor",
                )
                yield Input(
                    placeholder="Example output from one completed run: directories "
                    "or listings, comma separated (optional)",
                    id="session-examples",
                )
                if self.mode is InteractionMode.AUTONOMOUS:
                    for switch, label, value in (
                        ("grant-build", "Publish the bundle into splice/", True),
                        (
                            "grant-overwrite",
                            "Replace published files that were edited by hand",
                            False,
                        ),
                        (
                            "grant-checks",
                            "Run nf-core lint if installed (runs `nextflow config`, "
                            "may use the network)",
                            False,
                        ),
                    ):
                        with Horizontal(classes="row"):
                            yield Switch(value=value, id=switch)
                            yield Label(label)
                    yield Input(
                        value="300",
                        placeholder="Maximum tool calls",
                        id="session-budget",
                    )
                with Horizontal(classes="row"):
                    yield Button(
                        "Approve scope and start"
                        if self.mode is InteractionMode.AUTONOMOUS
                        else "Start session",
                        id="session-begin",
                        variant="primary",
                    )
                    yield Button("Close", id="session-close")
            with Vertical(id="session-live"):
                yield Static("", id="session-stages")
                with VerticalScroll(id="session-log-scroll"):
                    yield Static("", id="session-log")
                yield Markdown("", id="session-proposal")
                with VerticalScroll(id="session-diff-scroll"):
                    yield Static("", id="session-diff", markup=False)
                yield Input(
                    placeholder="Your message: an objection, a question or an answer",
                    id="session-message",
                )
                with Horizontal(classes="row"):
                    if self.mode is InteractionMode.ASSISTED:
                        yield Button("Approve", id="session-approve", variant="success")
                        yield Button("Object", id="session-object", variant="error")
                        yield Button("Reply", id="session-reply")
                        yield Button("Continue", id="session-continue")
                        yield Button("Pause", id="session-pause")
                    else:
                        yield Button("Stop", id="session-stop", variant="error")
                        yield Button(
                            "Resume in assisted mode",
                            id="session-to-assisted",
                            variant="primary",
                        )
                    yield Button("Ask", id="session-ask")
                    yield Button("Close", id="session-close-live")

    def on_mount(self) -> None:
        if self.wizard.agent_provider is None:
            self._title("Agentic AI is off")
            return
        store = SessionStore(self.wizard.repository)
        existing = next(
            (
                item
                for item in store.sessions()
                if item.mode is self.mode and item.status not in _FINISHED
            ),
            None,
        )
        if existing is not None:
            self.engine = SessionEngine.open(
                self.wizard.repository, existing.id, self.wizard.agent_provider
            )
            self._live(True)
        else:
            self._live(False)
            self._title(f"{self.mode.value.capitalize()} session: not started")
        self.set_interval(0.5, self._poll)

    def _live(self, live: bool) -> None:
        self.query_one("#session-start").display = not live
        self.query_one("#session-live").display = live
        if live:
            self.refresh_session()

    def _title(self, text: str) -> None:
        self.query_one("#session-title", Static).update(
            f"[b]{text}[/b]" + self._disclosure()
        )

    def _disclosure(self) -> str:
        """Which provider and model runs, where inference happens, who pays."""
        provider = self.wizard.agent_provider
        if provider is None:
            return ""
        try:
            capabilities = provider.capabilities
        except Exception:  # a provider that cannot describe itself stays quiet
            return ""
        model = getattr(provider, "model", None)
        return (
            f"\n[dim]Provider {capabilities.name}"
            + (f" ({model})" if model else "")
            + f"; inference {capabilities.inference}; billing "
            f"{capabilities.billing}[/dim]"
        )

    # -------------------------------------------------------- rendering

    def refresh_session(self) -> None:
        engine = self.engine
        if engine is None:
            return
        state = engine.state
        self._title(
            f"{state.mode.value.capitalize()} session {state.id}: "
            f"{state.status.value.replace('_', ' ')}"
            + (" (working...)" if self.running else "")
        )
        self.query_one("#session-stages", Static).update(
            "  ".join(
                f"{_GLYPH.get(state.stages[stage].status, '○')} {spec(stage).title}"
                for stage in ORDER
            )
        )
        entries = state.conversation[-30:]
        self.query_one("#session-log", Static).update(
            "\n".join(
                f"[{entry.role}] {entry.text[:1500]}"
                for entry in entries
                if entry.kind != "proposal"
            ).replace("[", "\\[")
        )
        proposal = self.query_one("#session-proposal", Markdown)
        diff = self.query_one("#session-diff", Static)
        if state.pending is not None:
            proposal.update(
                "### Proposal waiting for you\n\n"
                + proposal_text(state.pending).replace("\n- ", "\n\n- ")
            )
            diff.update(state.pending.diff[:12000] or "(no file changes)")
        elif state.status in _FINISHED or state.status is SessionStatus.AWAITING_INPUT:
            proposal.update(
                "### Report\n\n```\n" + report_text(engine.report()) + "\n```"
            )
            diff.update("")
        else:
            proposal.update("")
            diff.update("")
        self._enable(state.status)

    def _enable(self, status: SessionStatus) -> None:
        busy = self.running
        pending = self.engine is not None and self.engine.state.pending is not None
        for selector, enabled in (
            ("#session-approve", pending and not busy),
            ("#session-object", pending and not busy),
            ("#session-reply", status is SessionStatus.AWAITING_INPUT and not busy),
            ("#session-continue", not busy and status not in _FINISHED),
            ("#session-pause", not busy and status not in _FINISHED),
            ("#session-stop", busy),
            ("#session-to-assisted", not busy and status in _FINISHED),
            ("#session-ask", not busy),
        ):
            for button in self.query(selector):
                button.disabled = not enabled

    def _poll(self) -> None:
        if self.running:
            self.refresh_session()

    # -------------------------------------------------------- actions

    def _actor(self) -> Any:
        label = self.query_one("#session-actor", Input).value.strip()
        actor = resolve_actor(label or self.wizard.actor_label)
        if actor.kind is not ActorKind.HUMAN:
            raise ValueError("enter your name: a person must approve the session")
        return actor

    def _run(
        self,
        label: str,
        coroutine: Callable[[], Coroutine[Any, Any, Any]],
        then: Callable[[Any], None] | None = None,
    ) -> None:
        self.running = True
        self.wizard.set_status(f"{label}...")
        self.refresh_session()

        def work() -> None:
            try:
                result = asyncio.run(coroutine())
            except Exception as error:
                self.app.call_from_thread(self._failed, error)
                return
            self.app.call_from_thread(self._done, label, result, then)

        self.run_worker(work, thread=True, exclusive=True, group="session")

    def _failed(self, error: Exception) -> None:
        self.running = False
        self.wizard.set_status(str(error), error=True)
        self.refresh_session()

    def _done(
        self, label: str, result: Any, then: Callable[[Any], None] | None
    ) -> None:
        self.running = False
        self.wizard.set_status(f"{label}: done.")
        self.refresh_session()
        if then is not None:
            then(result)

    def _start(self) -> None:
        try:
            actor = self._actor()
        except ValueError as error:
            self.wizard.set_status(str(error), error=True)
            return
        examples = [
            str(Path(item.strip()).expanduser().resolve())
            for item in self.query_one("#session-examples", Input).value.split(",")
            if item.strip()
        ]
        grants = {Permission.READ, Permission.DRAFT_EDIT, Permission.BUILD}
        budgets = Budgets()
        if self.mode is InteractionMode.AUTONOMOUS:
            if not self.query_one("#grant-build", Switch).value:
                grants.discard(Permission.BUILD)
            if self.query_one("#grant-overwrite", Switch).value:
                grants.add(Permission.OVERWRITE)
            if self.query_one("#grant-checks", Switch).value:
                grants |= {
                    Permission.EXTERNAL_TOOLS,
                    Permission.RUN_NEXTFLOW,
                    Permission.NETWORK,
                }
            try:
                budgets = Budgets(
                    max_tool_calls=int(
                        self.query_one("#session-budget", Input).value or 300
                    )
                )
            except ValueError as error:
                self.wizard.set_status(f"invalid budget: {error}", error=True)
                return
        policy = ExecutionPolicy(
            grants=sorted(grants, key=lambda item: item.value),
            budgets=budgets,
            examples=examples,
            allow_remote_model=self.wizard.allow_remote_model,
        )
        provider = self.wizard.agent_provider
        assert provider is not None
        try:
            self.engine = SessionEngine.create(
                self.wizard.repository,
                mode=self.mode,
                provider=provider,
                objective="Integrate this Nextflow pipeline with SPLICE.",
                policy=policy,
                actor=actor,
            )
        except Exception as error:
            self.wizard.set_status(str(error), error=True)
            return
        self._live(True)
        engine = self.engine
        self._run("Working", engine.advance)

    def _message(self) -> str:
        field = self.query_one("#session-message", Input)
        text = field.value.strip()
        field.value = ""
        return text

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        identifier = event.button.id or ""
        if identifier in {"session-close", "session-close-live"}:
            self.action_close()
            return
        if identifier == "session-begin":
            self._start()
            return
        engine = self.engine
        if engine is None:
            return
        try:
            actor = self._actor() if identifier != "session-ask" else None
        except ValueError as error:
            self.wizard.set_status(str(error), error=True)
            return
        if identifier == "session-approve" and actor is not None:
            self._run("Applying the approved changes", lambda: engine.approve(actor))
        elif identifier == "session-object" and actor is not None:
            text = self._message()
            if not text:
                self.wizard.set_status("Type what is wrong first.", error=True)
                return
            self._run(
                "Investigating your objection", lambda: engine.object(text, actor)
            )
        elif identifier == "session-reply" and actor is not None:
            text = self._message()
            if not text:
                self.wizard.set_status("Type your answer first.", error=True)
                return
            self._run("Planning with your answer", lambda: engine.reply(text, actor))
        elif identifier == "session-continue":
            self._run("Continuing", engine.advance)
        elif identifier == "session-pause" and actor is not None:
            engine.pause(actor)
            self.refresh_session()
        elif identifier == "session-stop":
            engine.request_cancel()
            self.wizard.set_status("Stopping at the next safe point...")
        elif identifier == "session-to-assisted" and actor is not None:
            engine.switch_mode(InteractionMode.ASSISTED, actor)
            self.mode = InteractionMode.ASSISTED
            self.dismiss(None)
            self.wizard.open_session(InteractionMode.ASSISTED)
        elif identifier == "session-ask":
            text = self._message()
            if not text:
                self.wizard.set_status("Type your question first.", error=True)
                return
            asker = resolve_actor(self.wizard.actor_label)

            async def ask() -> str:
                answer = await engine.ask(text, asker)
                return answer

            self._run("Asking", ask)

    def action_close(self) -> None:
        if self.running and self.engine is not None:
            self.engine.request_cancel()
        self.dismiss(None)
        self.wizard.action_reload()
