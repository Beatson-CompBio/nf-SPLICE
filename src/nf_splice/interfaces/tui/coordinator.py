"""One owner for agent work in the workspace: Ask, Assist and autonomy.

The :class:`AgentCoordinator` belongs to the application, not to a screen or
the dock, so closing the dock never cancels a session (ADR-0067). It runs the
shared :class:`~nf_splice.agents.SessionEngine` in one background thread at
a time, projects the engine's persisted state into an immutable
:class:`AgentSnapshot` for the interface, and keeps the distinctions the
engine relies on:

- *Ask* answers with read-only tools (:func:`~nf_splice.agents.ask_for_help`)
  and can run while a session works; it never changes a file.
- *Assist* asks the engine for one stage's proposal; nothing is applied
  until a person approves it, and a proposal made before the drafts changed
  is withdrawn rather than applied.
- *Autonomy* runs within the grants the person approved. ``request_pause``
  asks for a stop at the next safe point and reports ``PAUSE REQUESTED``
  until the engine has actually stopped; ``stop`` cancels the session for
  good, and a cancelled session is never resumed.
- While the agent may write drafts, :meth:`writes_locked` is true and the
  interface refuses conflicting manual edits until a pause is confirmed.

Nothing here talks to a provider SDK directly, and nothing is synthesised on
a person's behalf: every approval, rejection, pause and resume names the
person who made it.
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from nf_splice.agents import (
    Budgets,
    ExecutionPolicy,
    InteractionMode,
    Permission,
    SessionEngine,
    SessionStatus,
    SessionStore,
    ask_for_help,
)
from nf_splice.agents.protocol import AgentProvider
from nf_splice.agents.stages import Stage, StageStatus, spec
from nf_splice.domain.audit import Actor, ActorKind
from nf_splice.interfaces.tui.model import bounded
from nf_splice.interfaces.tui.navigation import Target, target_for
from nf_splice.layout import SESSIONS_DIR
from nf_splice.services.audit import resolve_actor


class AgentState(str, Enum):
    """The one agent state the header shows, on every page."""

    OFF = "off"
    READY = "ready"
    THINKING = "thinking"
    PROPOSAL = "proposal"
    RUNNING = "running"
    AWAITING_YOU = "awaiting_you"
    PAUSE_REQUESTED = "pause_requested"
    PAUSED = "paused"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


STATE_LABELS = {
    AgentState.OFF: "AI OFF",
    AgentState.READY: "AI READY",
    AgentState.THINKING: "THINKING",
    AgentState.PROPOSAL: "PROPOSAL WAITING",
    AgentState.RUNNING: "AUTONOMOUS RUNNING",
    AgentState.AWAITING_YOU: "NEEDS YOUR INPUT",
    AgentState.PAUSE_REQUESTED: "PAUSE REQUESTED",
    AgentState.PAUSED: "PAUSED",
    AgentState.BLOCKED: "BLOCKED",
    AgentState.COMPLETED: "COMPLETED",
    AgentState.FAILED: "FAILED",
    AgentState.STOPPED: "STOPPED",
}
STATE_GLYPHS = {
    AgentState.OFF: "◇",
    AgentState.READY: "◇",
    AgentState.THINKING: "…",
    AgentState.PROPOSAL: "?",
    AgentState.RUNNING: "▶",
    AgentState.AWAITING_YOU: "!",
    AgentState.PAUSE_REQUESTED: "‖",
    AgentState.PAUSED: "‖",
    AgentState.BLOCKED: "✕",
    AgentState.COMPLETED: "✓",
    AgentState.FAILED: "✕",
    AgentState.STOPPED: "■",
}
#: States that ask for a person's attention (shown with a warning style).
ATTENTION = frozenset(
    {
        AgentState.PROPOSAL,
        AgentState.AWAITING_YOU,
        AgentState.PAUSED,
        AgentState.BLOCKED,
        AgentState.FAILED,
    }
)

#: Least privilege: what any session may do; everything else is a separate
#: grant the person ticks (publishing, overwriting, external checks).
BASE_GRANTS = (Permission.READ, Permission.DRAFT_EDIT)
OPTIONAL_GRANTS = (
    (Permission.BUILD, "Publish a validated bundle into splice/"),
    (Permission.OVERWRITE, "Replace published files that differ or were edited"),
    (Permission.EXPORT, "Write a verified ZIP export into .splice-local/"),
    (
        Permission.EXTERNAL_TOOLS,
        "Run installed external checkers (nf-core, validators)",
    ),
    (Permission.NETWORK, "Let those checkers use the network"),
)


@dataclass(frozen=True, slots=True)
class ProviderView:
    """What the person must see before any work begins."""

    name: str
    model: str
    inference: str
    billing: str
    remote: bool
    tool_calling: bool
    reasoning: str
    continuation: bool
    cancellation: bool


@dataclass(frozen=True, slots=True)
class ProposalView:
    id: str
    stage: str
    stage_title: str
    summary: str
    evidence: tuple[str, ...]
    uncertainties: tuple[str, ...]
    preview_issues: tuple[str, ...]
    validation_gate: str
    diff: str
    changed_files: tuple[str, ...]
    operations: int


@dataclass(frozen=True, slots=True)
class Intervention:
    """A decision the agent left for a person, with where to make it."""

    stage: str
    stage_title: str
    decision: str
    #: Why the agent could not decide (its own words, else the findings).
    reason: str
    #: What it examined, in plain words (no tool payloads).
    evidence: tuple[str, ...]
    suggestion: str
    pointer: str
    checkpoint: str
    artefact: str
    target: Target
    uncertainties: tuple[str, ...] = ()
    #: Validation findings and the operations the session ran, verbatim,
    #: for the expandable technical details only.
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AgentSnapshot:
    """An immutable projection of the agent's state for the interface."""

    state: AgentState
    provider: ProviderView | None
    consent_needed: bool
    unavailable: str
    session_id: str | None
    mode: str | None
    stage: str | None
    stage_title: str
    focus: str | None
    grants: tuple[str, ...]
    tool_calls: int
    max_tool_calls: int
    stages: tuple[tuple[str, str], ...]
    activity: tuple[str, ...]
    proposal: ProposalView | None
    interventions: tuple[Intervention, ...]
    question: str
    answer: str
    answer_question: str
    asking: bool
    busy: bool
    task: str
    error: str
    notice: str
    person: str | None

    @property
    def label(self) -> str:
        return STATE_LABELS[self.state]

    @property
    def glyph(self) -> str:
        return STATE_GLYPHS[self.state]

    @property
    def attention(self) -> bool:
        return self.state in ATTENTION


_FINISHED = {SessionStatus.COMPLETED, SessionStatus.CANCELLED}


#: Plain words for the analyses an agent may cite as evidence.
CHECK_PHRASES = {
    "analyse_routes": "the pipeline's publication routes",
    "route_coverage": "which published routes the catalogue covers",
    "parameter_usage": "where each parameter is used",
    "component_inventory": "the module and container inventory",
    "analyse_execution": "the execution profiles and configs",
    "analyse_ro_crate": "the RO-Crate",
    "search_assay_catalogue": "the SPLICE assay vocabulary",
    "show_assay": "an assay's vocabulary entry",
    "list_example_outputs": "the example outputs",
    "reconcile_example_outputs": "the example outputs against the catalogue",
    "validate_layer": "the draft's validation",
    "contract_reference": "the field contract",
    "read_draft": "the current draft",
}
#: Operations that change drafts: never shown as evidence.
_WRITES = ("replace_draft", "write_config", "patch_draft", "set_", "add_", "remove_")


def _evidence(checks: list[str]) -> tuple[str, ...]:
    """What the agent examined, readable: no payloads, no write operations."""
    found: list[str] = []
    for value in checks:
        text = value.strip()
        for marker in (" {", " [", "("):
            if marker in text and text.split(marker, 1)[0].isidentifier():
                text = text.split(marker, 1)[0]
        if text.startswith(_WRITES):
            continue
        label = CHECK_PHRASES.get(text, text if not text.isidentifier() else "")
        if not label:
            label = text.replace("_", " ")
        label = bounded(label, 160)
        if label not in found:
            found.append(label)
    return tuple(found[:6])


def _changed_files(diff: str) -> tuple[str, ...]:
    found = []
    for line in diff.splitlines():
        if line.startswith("+++ "):
            name = line[4:].strip().removeprefix("b/")
            if name != "/dev/null" and name not in found:
                found.append(name)
    return tuple(found)


@dataclass(slots=True)
class _Work:
    task: str
    label: str
    thread: threading.Thread
    started: float = field(default_factory=time.monotonic)


class AgentCoordinator:
    """Owns the provider, the active session and the agent's background work."""

    def __init__(
        self,
        repository: str | Path,
        provider: AgentProvider | None = None,
        *,
        allow_remote_model: bool = False,
        person: str | None = None,
        notify: Callable[[], None] | None = None,
    ) -> None:
        self.repository = Path(repository).resolve()
        self.provider = provider
        self.consented = allow_remote_model
        self.person = person
        self.notify = notify or (lambda: None)
        self.engine: SessionEngine | None = None
        self._work: _Work | None = None
        self._ask_thread: threading.Thread | None = None
        self._ask_generation = 0
        self._lock = threading.RLock()
        self._pause_requested = False
        self._stop_requested = False
        self._error = ""
        self._notice = ""
        self._question = ""
        self._answer = ""
        self._answer_question = ""
        self._last: AgentSnapshot | None = None

    # ------------------------------------------------------------ provider

    def connect(self, provider: AgentProvider | None) -> None:
        """Use a provider from now on (``None`` turns AI off; drafts stay)."""
        if self.busy:
            raise RuntimeError("wait for the agent to stop before changing provider")
        self.provider = provider
        self._error = ""
        if provider is not None and self.engine is not None:
            self.engine.provider = provider
        self.notify()

    def consent(self, granted: bool) -> None:
        """Record the person's consent to send repository context remotely."""
        self.consented = granted
        if self.engine is not None and granted:
            self.engine.state.policy.allow_remote_model = True
        self.notify()

    def set_person(self, name: str) -> None:
        self.person = name.strip() or None
        self.notify()

    def actor(self) -> Actor:
        """The person acting now; agent work never starts without one."""
        actor = resolve_actor(self.person)
        if actor.kind is not ActorKind.HUMAN:
            raise PermissionError(
                "enter your name first: approvals, pauses and resumes are recorded "
                "with the person who made them"
            )
        return actor

    def _capability_problem(self) -> str:
        provider = self.provider
        if provider is None:
            return "No AI provider is configured; everything works manually."
        try:
            capabilities = provider.capabilities
        except Exception as error:  # a broken adapter must not blank the UI
            return f"The provider cannot describe itself: {error}"
        if not capabilities.tool_calling:
            return (
                f"{capabilities.name} cannot call nf-splice's structured tools, so "
                "Ask, Assist and autonomy are unavailable with it."
            )
        return ""

    def _provider_view(self) -> ProviderView | None:
        provider = self.provider
        if provider is None:
            return None
        try:
            capabilities = provider.capabilities
        except Exception:
            return None
        model = getattr(provider, "model", None) or "provider default"
        return ProviderView(
            capabilities.name,
            str(model),
            capabilities.inference,
            capabilities.billing,
            capabilities.remote,
            capabilities.tool_calling,
            capabilities.reasoning_control,
            capabilities.continuation,
            capabilities.cancellation,
        )

    def tools_supported(self) -> bool:
        """False only when a connected provider cannot call nf-splice tools."""
        return self.provider is None or not self._capability_problem()

    @property
    def consent_needed(self) -> bool:
        view = self._provider_view()
        return bool(view and view.remote and not self.consented)

    def available(self) -> bool:
        return not self._capability_problem() and not self.consent_needed

    # ------------------------------------------------------------ sessions

    def attach_latest(self) -> SessionEngine | None:
        """Re-open the most recent session that is not finished (on start).

        A cancelled or completed session is never re-opened; an interrupted
        one is shown as paused, and continues only when a person resumes it.
        """
        if not (self.repository / SESSIONS_DIR).is_dir():
            # No session was ever started here; opening a folder (an original
            # pipeline, say) must not create .splice-local/ in it.
            return None
        try:
            sessions = SessionStore(self.repository).sessions()
        except Exception:
            return None
        live = [item for item in sessions if item.status not in _FINISHED]
        if not live:
            return None
        latest = max(live, key=lambda item: item.updated_at)
        try:
            self.engine = SessionEngine.open(self.repository, latest.id, self.provider)
        except Exception as error:
            self._notice = bounded(f"could not reopen session {latest.id}: {error}")
            return None
        if self.engine.state.status is SessionStatus.RUNNING:
            self._notice = (
                f"Session {latest.id} was interrupted while running; it is paused "
                "until you resume it."
            )
        self.notify()
        return self.engine

    def _new_engine(
        self, mode: InteractionMode, grants: list[Permission], budget: int
    ) -> SessionEngine:
        provider = self.provider
        assert provider is not None
        policy = ExecutionPolicy(
            grants=sorted(set(grants), key=lambda item: item.value),
            budgets=Budgets(max_tool_calls=budget),
            allow_remote_model=self.consented,
        )
        return SessionEngine.create(
            self.repository,
            mode=mode,
            provider=provider,
            objective="Integrate this Nextflow pipeline with SPLICE.",
            policy=policy,
            actor=self.actor(),
        )

    def _assisted_engine(self) -> SessionEngine:
        engine = self.engine
        if engine is None or engine.state.status is SessionStatus.CANCELLED:
            engine = self._new_engine(InteractionMode.ASSISTED, list(BASE_GRANTS), 1500)
            self.engine = engine
        elif engine.state.mode is not InteractionMode.ASSISTED:
            engine.switch_mode(InteractionMode.ASSISTED, self.actor())
        if self.provider is not None:
            engine.provider = self.provider
        return engine

    # ------------------------------------------------------------ background

    @property
    def busy(self) -> bool:
        work = self._work
        return work is not None and work.thread.is_alive()

    @property
    def asking(self) -> bool:
        thread = self._ask_thread
        return thread is not None and thread.is_alive()

    def writes_locked(self) -> bool:
        """Whether the agent may be writing drafts now (manual edits wait)."""
        work = self._work
        if work is None or not work.thread.is_alive():
            return False
        return work.task in {"autonomous", "approve", "resume"}

    def _run(
        self,
        task: str,
        label: str,
        coroutine: Callable[[], Coroutine[Any, Any, Any]],
        after: Callable[[], None] | None = None,
    ) -> None:
        if self.busy:
            raise RuntimeError("the agent is already working; wait or pause it first")
        self._error = ""

        def work() -> None:
            try:
                asyncio.run(coroutine())
            except Exception as error:
                self._error = bounded(str(error) or type(error).__name__, 400)
            finally:
                try:
                    if after is not None:
                        after()
                    self._settle()
                except Exception as error:
                    self._error = bounded(str(error), 400)
                self.notify()

        thread = threading.Thread(target=work, name=f"nf-splice-{task}", daemon=True)
        self._work = _Work(task, label, thread)
        thread.start()
        self.notify()

    def _settle(self) -> None:
        """Apply a requested pause or stop once the work has returned."""
        engine = self.engine
        if engine is None:
            return
        actor = resolve_actor(self.person)
        status = engine.state.status
        if self._stop_requested:
            self._stop_requested = False
            self._pause_requested = False
            if status is not SessionStatus.CANCELLED and actor.kind is ActorKind.HUMAN:
                engine.cancel(actor)
            return
        if self._pause_requested:
            self._pause_requested = False
            if status not in {
                SessionStatus.PAUSED,
                SessionStatus.COMPLETED,
                SessionStatus.CANCELLED,
            }:
                if actor.kind is ActorKind.HUMAN:
                    engine.pause(actor)

    def wait(self, timeout: float | None = None) -> bool:
        """Wait for background work (tests and shutdown); True when idle."""
        work = self._work
        if work is not None:
            work.thread.join(timeout)
        thread = self._ask_thread
        if thread is not None:
            thread.join(timeout)
        return not self.busy and not self.asking

    # ------------------------------------------------------------ Ask

    def ask(self, question: str, context: dict[str, Any]) -> None:
        """Answer one question with read-only tools; nothing can change."""
        if not self.available():
            raise RuntimeError(self._capability_problem() or "remote consent needed")
        provider = self.provider
        assert provider is not None
        self._ask_generation += 1
        generation = self._ask_generation
        self._question = question
        self._answer = ""
        self._answer_question = question

        def work() -> None:
            try:
                answer = asyncio.run(
                    ask_for_help(
                        self.repository,
                        provider,
                        question,
                        context=context,
                        allow_remote_model=self.consented,
                    )
                )
                text = answer.text
            except Exception as error:
                text = f"The question could not be answered: {bounded(error, 400)}"
            if generation == self._ask_generation:
                self._answer = text
            self.notify()

        self._ask_thread = threading.Thread(
            target=work, name="nf-splice-ask", daemon=True
        )
        self._ask_thread.start()
        self.notify()

    def cancel_answer(self) -> None:
        """Ignore the running answer (the read-only call finishes unused)."""
        self._ask_generation += 1
        self._answer = "Answer cancelled."
        self.notify()

    # ------------------------------------------------------------ Assist

    def assist(self, stage: str, guidance: str = "") -> None:
        """Ask for one stage's proposal; nothing is applied without approval."""
        if not self.available():
            raise RuntimeError(self._capability_problem() or "remote consent needed")
        engine = self._assisted_engine()
        actor = self.actor()
        engine.reset_cancel()
        self._run(
            "assist",
            f"Investigating {spec(Stage(stage)).title}",
            lambda: engine.assist(Stage(stage), actor, guidance),
        )

    def approve(self) -> None:
        engine = self._require_engine()
        actor = self.actor()
        self._run(
            "approve", "Applying the approved changes", lambda: engine.approve(actor)
        )

    def revise(self, text: str) -> None:
        if not text.strip():
            raise ValueError("say what should change in the proposal")
        engine = self._require_engine()
        actor = self.actor()
        self._run("assist", "Revising the proposal", lambda: engine.object(text, actor))

    def reject(self, reason: str = "") -> None:
        engine = self._require_engine()
        engine.reject(self.actor(), reason)
        self.notify()

    def reply(self, text: str) -> None:
        if not text.strip():
            raise ValueError("type your answer first")
        engine = self._require_engine()
        actor = self.actor()
        self._run(
            "assist", "Planning with your answer", lambda: engine.reply(text, actor)
        )

    def _require_engine(self) -> SessionEngine:
        if self.engine is None:
            raise RuntimeError("no session is open")
        if self.provider is not None:
            self.engine.provider = self.provider
        return self.engine

    # ------------------------------------------------------------ autonomy

    def start_autonomous(
        self, grants: list[Permission], max_tool_calls: int = 1500
    ) -> None:
        """Start scoped autonomy (or switch the open session to it)."""
        if not self.available():
            raise RuntimeError(self._capability_problem() or "remote consent needed")
        actor = self.actor()
        scope = sorted(set(BASE_GRANTS) | set(grants), key=lambda item: item.value)
        engine = self.engine
        if engine is None or engine.state.status is SessionStatus.CANCELLED:
            engine = self._new_engine(InteractionMode.AUTONOMOUS, scope, max_tool_calls)
            self.engine = engine
        else:
            policy = engine.state.policy.model_copy(deep=True)
            policy.grants = scope
            policy.budgets = policy.budgets.model_copy(
                update={"max_tool_calls": max_tool_calls}
            )
            policy.allow_remote_model = self.consented
            engine.switch_mode(InteractionMode.AUTONOMOUS, actor, policy=policy)
        if self.provider is not None:
            engine.provider = self.provider
        engine.reset_cancel()
        self._run("autonomous", "Working autonomously", engine.advance)

    def request_pause(self) -> None:
        """Ask for a stop at the next safe point; not a pause until it stops."""
        engine = self.engine
        if engine is None:
            return
        if self.busy:
            self._pause_requested = True
            engine.request_cancel()
        elif engine.state.status not in {
            SessionStatus.PAUSED,
            SessionStatus.COMPLETED,
            SessionStatus.CANCELLED,
        }:
            engine.pause(self.actor())
        self.notify()

    def stop(self) -> None:
        """Cancel the session for good once it reaches a safe point."""
        engine = self.engine
        if engine is None:
            return
        actor = self.actor()
        if self.busy:
            self._stop_requested = True
            engine.request_cancel()
        elif engine.state.status is not SessionStatus.CANCELLED:
            engine.cancel(actor)
        self.notify()

    def resume(self, note: str = "") -> None:
        """Continue the same session from the current drafts."""
        engine = self._require_engine()
        actor = self.actor()
        engine.reset_cancel()
        engine.resume(actor, note)
        if engine.state.mode is InteractionMode.AUTONOMOUS:
            self._run("resume", "Resuming autonomously", engine.advance)
        else:
            self.notify()

    def shutdown(self, timeout: float = 30.0) -> bool:
        """Request a safe pause and wait; True when nothing is left running."""
        if self.busy and self.engine is not None:
            self._pause_requested = True
            self.engine.request_cancel()
        return self.wait(timeout)

    # ------------------------------------------------------------ projection

    def snapshot(self) -> AgentSnapshot:
        try:
            snapshot = self._snapshot()
        except Exception:  # a state being written in the worker: show the last
            if self._last is not None:
                return self._last
            raise
        self._last = snapshot
        return snapshot

    def _state(self) -> AgentState:
        if self._capability_problem() and self.provider is None:
            return AgentState.OFF
        engine = self.engine
        busy = self.busy
        if busy and (self._pause_requested or self._stop_requested):
            return AgentState.PAUSE_REQUESTED
        if busy:
            work = self._work
            assert work is not None
            return (
                AgentState.RUNNING
                if work.task in {"autonomous", "resume"}
                else AgentState.THINKING
            )
        if self._error and engine is None:
            return AgentState.FAILED
        if engine is None:
            return AgentState.THINKING if self.asking else AgentState.READY
        status = engine.state.status
        if engine.state.interruption:
            return AgentState.FAILED
        if status is SessionStatus.CANCELLED:
            return AgentState.STOPPED
        if status is SessionStatus.COMPLETED:
            return AgentState.COMPLETED
        if status is SessionStatus.AWAITING_APPROVAL and engine.state.pending:
            return AgentState.PROPOSAL
        if status is SessionStatus.AWAITING_INPUT:
            return AgentState.AWAITING_YOU
        if status is SessionStatus.BLOCKED:
            return (
                AgentState.AWAITING_YOU
                if engine.open_interventions()
                else AgentState.BLOCKED
            )
        if status in {SessionStatus.PAUSED, SessionStatus.RUNNING}:
            return AgentState.PAUSED
        if self._error:
            return AgentState.FAILED
        return AgentState.THINKING if self.asking else AgentState.READY

    def _snapshot(self) -> AgentSnapshot:
        engine = self.engine
        state = self._state()
        proposal = None
        interventions: tuple[Intervention, ...] = ()
        stages: tuple[tuple[str, str], ...] = ()
        activity: tuple[str, ...] = ()
        grants: tuple[str, ...] = ()
        stage = focus = mode = session_id = None
        stage_title = ""
        tool_calls = max_calls = 0
        if engine is not None:
            record = engine.state
            session_id = record.id
            mode = record.mode.value
            stage = record.current_stage.value if record.current_stage else None
            stage_title = (
                spec(record.current_stage).title if record.current_stage else ""
            )
            focus = record.focus.value if record.focus else None
            grants = tuple(item.value for item in record.policy.grants)
            tool_calls = record.usage.tool_calls
            max_calls = record.policy.budgets.max_tool_calls
            stages = tuple(
                (spec(item).title, value.status.value)
                for item, value in list(record.stages.items())
            )
            activity = tuple(
                bounded(f"{entry.role}: {entry.text}", 220)
                for entry in list(record.conversation)[-8:]
                if entry.kind not in {"proposal"}
            )
            pending = record.pending
            if pending is not None:
                proposal = ProposalView(
                    pending.id,
                    pending.stage.value,
                    spec(pending.stage).title,
                    bounded(pending.summary, 600),
                    tuple(bounded(item, 200) for item in pending.evidence[:12]),
                    tuple(bounded(item, 200) for item in pending.uncertainties[:8]),
                    tuple(bounded(item, 200) for item in pending.preview_issues[:8]),
                    bounded(pending.validation_gate, 200),
                    pending.diff,
                    _changed_files(pending.diff),
                    len(pending.operations),
                )
            interventions = tuple(
                Intervention(
                    item.stage.value,
                    spec(item.stage).title,
                    bounded(item.decision, 300),
                    bounded(item.reason or "; ".join(item.issues[:3]), 300),
                    _evidence(item.attempted_checks),
                    bounded(item.suggested_resolution, 300),
                    item.pointer,
                    item.checkpoint,
                    item.artefact,
                    target_for(stage=item.stage.value, pointer=item.pointer or None),
                    tuple(bounded(value, 200) for value in item.uncertainties[:6]),
                    tuple(
                        [f"finding: {value}" for value in item.issues]
                        + [f"agent check: {value}" for value in item.attempted_checks]
                        + [f"operation: {value}" for value in item.diagnostics]
                    ),
                )
                for item in engine.open_interventions()
            )
            if record.status is SessionStatus.AWAITING_INPUT and not interventions:
                question = next(
                    (
                        entry
                        for entry in reversed(record.conversation)
                        if entry.kind == "question"
                    ),
                    None,
                )
                if question is not None and question.stage is not None:
                    interventions = (
                        Intervention(
                            question.stage.value,
                            spec(question.stage).title,
                            bounded(question.text, 400),
                            "",
                            (),
                            "Answer the question, or edit the draft and resume.",
                            "",
                            "",
                            "",
                            target_for(stage=question.stage.value),
                        ),
                    )
        work = self._work
        return AgentSnapshot(
            state=state,
            provider=self._provider_view(),
            consent_needed=self.consent_needed,
            unavailable=self._capability_problem(),
            session_id=session_id,
            mode=mode,
            stage=stage,
            stage_title=stage_title,
            focus=focus,
            grants=grants,
            tool_calls=tool_calls,
            max_tool_calls=max_calls,
            stages=stages,
            activity=activity,
            proposal=proposal,
            interventions=interventions,
            question=self._question,
            answer=self._answer,
            answer_question=self._answer_question,
            asking=self.asking,
            busy=self.busy,
            task=work.label if work is not None and work.thread.is_alive() else "",
            error=self._error,
            notice=self._notice,
            person=self.person,
        )


def stage_status_glyph(status: str) -> str:
    return {
        StageStatus.COMPLETED.value: "✓",
        StageStatus.BLOCKED.value: "!",
        StageStatus.NEEDS_APPROVAL.value: "?",
        StageStatus.EXECUTING.value: "…",
        StageStatus.REPAIRING.value: "…",
        StageStatus.VALIDATION_FAILED.value: "!",
        StageStatus.SKIPPED.value: "-",
    }.get(status, "○")
