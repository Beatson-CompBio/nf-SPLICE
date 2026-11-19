"""One session engine for AI-assisted and autonomous integration.

The engine is a typed state machine over the workflow stages. For each stage
it runs a bounded ``observe -> plan -> propose or execute -> validate ->
reflect`` loop:

- **Assisted**: the agent stages changes for one stage; they are previewed
  on a private copy and shown with their diff and validation outcome; only
  the user's approval applies them, after which the stage's deterministic
  gate decides whether the stage is complete. Objections start an
  investigation, never an automatic advance.
- **Autonomous**: within a scope and policy the user approved in advance,
  the agent applies routine decisions directly, the gate validates each
  stage, failed stages are retried only while they make progress, and
  anything that cannot be resolved with evidence becomes a recorded blocker.

Manual mode is the existing CLI and wizard; a session switched to manual is
simply paused while the person works. Every mode reads and writes the same
draft files, so a session can switch between modes at any time.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import threading
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from nf_splice.agents.operations import READ_OPERATIONS
from nf_splice.agents.permissions import ExecutionPolicy, Permission
from nf_splice.agents.prompts import (
    objection_instruction,
    proposal_text,
    stage_instruction,
    system_prompt,
)
from nf_splice.agents.protocol import (
    AgentProvider,
    EventKind,
    ProviderSession,
    ProviderUnavailable,
    TurnRequest,
    require_consent,
    require_tool_calling,
)
from nf_splice.agents.providers.base import (
    RETRYABLE,
    ProviderError,
    ProviderErrorKind,
)
from nf_splice.agents.report import build_report, report_text
from nf_splice.agents.review_scope import coverage
from nf_splice.agents.sandbox import Sandbox
from nf_splice.agents.stages import (
    FINISHING,
    LAYER_FOR_STAGE,
    ORDER,
    GateResult,
    Stage,
    StageStatus,
    gate,
    spec,
)
from nf_splice.agents.state import (
    ApprovalRecord,
    Blocker,
    EvidenceStatus,
    InteractionMode,
    PlannedOperation,
    Proposal,
    ProviderRecord,
    ReviewRecord,
    SessionError,
    SessionState,
    SessionStatus,
    SessionStore,
    Transaction,
    drafts_fingerprint,
    now,
    repository_key,
    sources_fingerprint,
)
from nf_splice.agents.toolbox import (
    SOURCE_INSPECTIONS,
    SessionToolbox,
    ToolMode,
    TurnOutcome,
)
from nf_splice.domain.audit import Actor, ActorKind, ChangeOrigin
from nf_splice.layers import ChangeContext
from nf_splice.layers.base import layer_spec, read_layer
from nf_splice.layout import STAGING_DIR, is_git_work_tree
from nf_splice.services import gitops
from nf_splice.services.coverage import assess
from nf_splice.services.export import (
    ExportError,
    ExportScope,
    default_archive_path,
    export_archive,
)
from nf_splice.services.lifecycle import validate_layer

_PLAN_CONTROLS = {
    "review_scope",
    "submit_stage_proposal",
    "complete_review",
    "record_blocker",
    "record_evidence",
}
_EXECUTE_CONTROLS = {
    "review_scope",
    "complete_review",
    "record_blocker",
    "record_evidence",
}
#: Layer stages whose review is scientific; the others are operational.
_SCIENTIFIC = frozenset({Stage.IDENTITY, Stage.INPUTS, Stage.OUTPUTS, Stage.PROVENANCE})
_PREVIEW_APPROVER = Actor(label="preview", kind=ActorKind.HUMAN)


class StaleProposal(SessionError):
    """Files changed after a proposal was made; it must be planned again."""


class ProviderInterrupted(SessionError):
    """The provider stopped a turn; the session is paused, not failed."""

    def __init__(self, error: ProviderError) -> None:
        super().__init__(str(error))
        self.error = error


def _digest(operations: list[PlannedOperation]) -> str:
    return hashlib.sha256(
        json.dumps([item.model_dump() for item in operations], sort_keys=True).encode()
    ).hexdigest()


def _ellipsise(text: str, limit: int = 400) -> str:
    """One line, at most limit characters, never cut mid-word.

    Session-history summaries are the only record a provider without
    continuation sees; an explicit ellipsis says a longer record exists,
    where a mid-word cut reads as a transcription error.
    """
    flat = " ".join(text.split())
    if len(flat) <= limit:
        return flat
    head = flat[:limit]
    stop = max(head.rfind(". "), head.rfind("! "), head.rfind("? "))
    if stop >= limit // 2:
        return head[: stop + 1]
    word = head.rfind(" ")
    if word > 0:
        head = head[:word]
    return head.rstrip(",;:") + "…"


class SessionEngine:
    """Drive one session; every public method saves state before returning."""

    def __init__(
        self,
        root: Path,
        store: SessionStore,
        state: SessionState,
        provider: AgentProvider | None = None,
    ) -> None:
        self.root = root.resolve()
        self.store = store
        self.state = state
        self.provider = provider
        self._session: ProviderSession | None = None
        self._locked = False
        self._cancel = threading.Event()

    # -------------------------------------------------------- lifecycle

    @classmethod
    def create(
        cls,
        repository: str | Path,
        *,
        mode: InteractionMode,
        provider: AgentProvider,
        objective: str,
        policy: ExecutionPolicy,
        actor: Actor,
        script: str | None = None,
    ) -> SessionEngine:
        """Start a session after checking capability, consent and approval."""
        if mode is InteractionMode.MANUAL:
            raise SessionError("manual work needs no session; use the CLI or wizard")
        require_tool_calling(provider)
        require_consent(provider, policy.allow_remote_model)
        if actor.kind is not ActorKind.HUMAN:
            raise SessionError(
                "a person must start a session and approve its scope; pass --user"
            )
        root = Path(repository).resolve()
        store = SessionStore(root)
        for example in policy.examples:
            if not Path(example).exists():
                raise SessionError(f"example output does not exist: {example}")
        policy.approved_by = actor.label
        policy.approved_at = now()
        stamp = now()
        capabilities = provider.capabilities
        state = SessionState(
            id=store.new_id(),
            created_at=stamp,
            updated_at=stamp,
            repository_key=repository_key(root),
            mode=mode,
            objective=objective,
            provider=ProviderRecord(
                name=capabilities.name,
                remote=capabilities.remote,
                script=script,
                model=policy.budgets.model or getattr(provider, "model", None),
                billing=capabilities.billing,
                inference=capabilities.inference,
                reasoning_control=capabilities.reasoning_control,
                reasoning_requested=policy.budgets.reasoning_effort,
            ),
            policy=policy,
        )
        state.mode_history.append(
            {"from": "", "to": mode.value, "at": stamp, "actor": actor.label}
        )
        state.say(
            "user",
            "start",
            f"{actor.label} started an {mode.value} session: {objective}",
            data={"grants": [item.value for item in policy.grants]},
        )
        engine = cls(root, store, state, provider)
        engine._save()
        return engine

    @classmethod
    def open(
        cls,
        repository: str | Path,
        session_id: str | None = None,
        provider: AgentProvider | None = None,
    ) -> SessionEngine:
        root = Path(repository).resolve()
        store = SessionStore(root)
        return cls(root, store, store.load(session_id), provider)

    def request_cancel(self) -> None:
        """Ask a running autonomous loop to stop at the next safe point."""
        self._cancel.set()

    @property
    def stop_requested(self) -> bool:
        """Whether a stop at the next safe point was requested."""
        return self._cancel.is_set()

    def reset_cancel(self) -> None:
        """Forget an earlier stop request before the session continues."""
        self._cancel.clear()

    # -------------------------------------------------------- helpers

    @property
    def session_directory(self) -> Path:
        return self.store.session_directory(self.state.id)

    def _staging(self) -> Path:
        return self.root / STAGING_DIR / self.state.id / "preview"

    def _examples(self) -> list[Path]:
        return [Path(item).resolve() for item in self.state.policy.examples]

    def _agent(self) -> Actor:
        return Actor(label=self.state.provider.name, kind=ActorKind.AGENT)

    def _change(self, approved_by: Actor | None) -> ChangeContext:
        if self.state.mode is InteractionMode.AUTONOMOUS:
            return ChangeContext(
                actor=self._agent(), origin=ChangeOrigin.AGENT_AUTONOMOUS
            )
        return ChangeContext(
            actor=self._agent(),
            origin=ChangeOrigin.AGENT_ASSISTED,
            approved_by=approved_by,
        )

    def _log(self, record: dict[str, Any]) -> None:
        record = record | {
            "session_mode": self.state.mode.value,
            "stage": self.state.current_stage.value
            if self.state.current_stage
            else None,
        }
        self.store.log_tool(self.state.id, record)

    def _save(self) -> None:
        self.state.drafts_fingerprint = drafts_fingerprint(self.root)
        self.state.sources_fingerprint = sources_fingerprint(self.root)
        for entry in self.state.conversation[self.state.events_logged :]:
            self.store.log_tool(
                self.state.id,
                {"event": "conversation", **entry.model_dump(mode="json")},
            )
        self.state.events_logged = len(self.state.conversation)
        self.store.save(self.state)

    def _require_provider(self) -> AgentProvider:
        if self.provider is None:
            raise SessionError("this step needs the session's AI provider")
        require_tool_calling(self.provider)
        require_consent(self.provider, self.state.policy.allow_remote_model)
        return self.provider

    def _fingerprints(self) -> tuple[str, str]:
        return drafts_fingerprint(self.root), sources_fingerprint(self.root)

    # -------------------------------------------------------- consistency

    def _prepare(self) -> None:
        self._recover_interrupted()
        drafts, sources = self._fingerprints()
        state = self.state
        if state.drafts_fingerprint and (
            drafts != state.drafts_fingerprint or sources != state.sources_fingerprint
        ):
            state.say(
                "system",
                "external_change",
                "Files changed outside this session since it last ran; completed "
                "stages were checked again.",
            )
            self._recheck_completed()
            if state.pending is not None and (
                state.pending.drafts_fingerprint != drafts
                or state.pending.sources_fingerprint != sources
            ):
                self._withdraw_pending("stale: files changed after it was made")

    def _recover_interrupted(self) -> None:
        transaction = self.state.transaction
        if transaction is None or self._locked:
            return
        with self.store.mutation_lock(self.state.id):
            self.store.restore(self.state, transaction.checkpoint)
        record = self.state.stages[transaction.stage]
        record.status = StageStatus.VALIDATION_FAILED
        record.notes.append(
            f"interrupted while applying changes; restored {transaction.checkpoint}"
        )
        self.state.transaction = None
        self.state.say(
            "system",
            "recovery",
            f"An interrupted action in {transaction.stage.value} was rolled back to "
            f"{transaction.checkpoint}.",
            stage=transaction.stage,
        )
        self._save()

    def _recheck_completed(self) -> None:
        for stage in ORDER:
            record = self.state.stages[stage]
            if record.status is not StageStatus.COMPLETED or stage in FINISHING:
                continue
            result = gate(stage, self.root)
            if not result.passed:
                record.status = StageStatus.PENDING
                record.issues = list(result.issues)
                record.notes.append("reopened: its validation no longer passes")
                for later in FINISHING:
                    self.state.stages[later].status = StageStatus.PENDING

    def _withdraw_pending(self, reason: str) -> None:
        pending = self.state.pending
        if pending is None:
            return
        pending.status = "withdrawn"
        self._store_proposal(pending)
        self.state.pending = None
        self.state.say(
            "system", "proposal_withdrawn", f"{pending.id} withdrawn: {reason}"
        )
        if self.state.status is SessionStatus.AWAITING_APPROVAL:
            self.state.status = SessionStatus.ACTIVE

    def _store_proposal(self, proposal: Proposal) -> None:
        self.state.proposals = [
            item for item in self.state.proposals if item.id != proposal.id
        ] + [proposal.model_copy()]

    # -------------------------------------------------------- stage bookkeeping

    def _next_stage(self) -> Stage | None:
        assisted = self.state.mode is InteractionMode.ASSISTED
        focus = self.state.focus
        if assisted and focus is not None:
            done = self.state.stages[focus].status in {
                StageStatus.COMPLETED,
                StageStatus.CANCELLED,
                StageStatus.SKIPPED,
            }
            return None if done else focus
        for stage in ORDER:
            record = self.state.stages[stage]
            if record.status in {
                StageStatus.COMPLETED,
                StageStatus.CANCELLED,
                StageStatus.SKIPPED,
            }:
                continue
            if record.status is StageStatus.BLOCKED and not assisted:
                continue
            usable = self._identity_usable(stage)
            blocked = [
                item
                for item in spec(stage).depends_on
                if self.state.stages[item].status is StageStatus.BLOCKED
                and not (item is Stage.IDENTITY and usable)
            ]
            if blocked:
                if not assisted:
                    record.status = StageStatus.BLOCKED
                    # Name the inherited reason, not just the stage: a stage
                    # blocked before it ran once should say what it waits for
                    # and why, so a cascade never looks unexplained.
                    for upstream in blocked:
                        decisions = "; ".join(
                            sorted(
                                {
                                    str(blocker.decision)
                                    for blocker in self.state.blockers
                                    if blocker.stage is upstream
                                    and not blocker.resolved
                                    and blocker.decision
                                }
                            )
                        )
                        note = f"waiting on {upstream.value}: " + (
                            decisions or "that stage is blocked"
                        )
                        if note not in record.notes:
                            record.notes.append(note)
                            self.state.say(
                                "system",
                                "blocked_by_dependency",
                                f"{spec(stage).title} is blocked before it "
                                f"starts: {note}.",
                                stage=stage,
                            )
                continue
            if any(
                self.state.stages[item].status
                not in {StageStatus.COMPLETED, StageStatus.SKIPPED}
                and not (item is Stage.IDENTITY and usable)
                for item in spec(stage).depends_on
            ):
                continue
            return stage
        return None

    def _identity_usable(self, stage: Stage) -> bool:
        """Whether a layer stage may proceed while identity waits for a person.

        An identity blocked only on its scientific classification (an assay
        a person must name) still gives the other layers everything they
        compile against, so their stages continue; validation, build and
        everything after them still wait for the identity stage itself.
        """
        if stage is Stage.IDENTITY or stage not in LAYER_FOR_STAGE:
            return False
        if self.state.stages[Stage.IDENTITY].status is not StageStatus.BLOCKED:
            return False
        from nf_splice.layers.bundle import validate_bundle_draft

        return validate_bundle_draft(self.root).usable

    def _complete(self, stage: Stage, result: GateResult, note: str = "") -> None:
        record = self.state.stages[stage]
        record.status = StageStatus.COMPLETED
        record.completed_at = now()
        record.issues = []
        record.summary = note or result.summary
        for blocker in self.state.blockers:
            if blocker.stage is stage:
                blocker.resolved = True
        if stage not in FINISHING:
            self.state.add_evidence(
                f"{spec(stage).title}: {result.summary or 'validation passed'}",
                EvidenceStatus.TOOL_VERIFIED,
                [f"gate:{stage.value}"],
                stage,
            )
        self.state.say(
            "system",
            "stage_complete",
            f"{spec(stage).title} complete. {note}".strip(),
            stage=stage,
        )

    def _block(
        self,
        stage: Stage,
        issues: tuple[str, ...] | list[str],
        reported: list[dict[str, Any]],
        attempted: list[str],
    ) -> None:
        record = self.state.stages[stage]
        record.status = StageStatus.BLOCKED
        record.issues = list(issues)
        layer = LAYER_FOR_STAGE.get(stage)
        artefact = f".splice-local/drafts ({layer})" if layer else spec(stage).title
        checkpoint = self.state.checkpoints[-1].id if self.state.checkpoints else ""
        if reported:
            for item in reported:
                self.state.blockers.append(
                    Blocker(
                        stage=stage,
                        decision=str(item.get("decision", "")),
                        artefact=str(item.get("artefact") or artefact),
                        attempted_checks=[
                            str(value) for value in item.get("attempted_checks") or []
                        ],
                        suggested_resolution=str(
                            item.get("suggested_resolution") or ""
                        ),
                        issues=list(issues),
                        reason=str(item.get("reason") or ""),
                        uncertainties=[
                            str(value) for value in item.get("uncertainties") or []
                        ],
                        diagnostics=list(attempted),
                        pointer=str(item.get("pointer") or ""),
                        checkpoint=checkpoint,
                        at=now(),
                    )
                )
        else:
            self.state.blockers.append(
                Blocker(
                    stage=stage,
                    decision=f"{spec(stage).title} still fails its validation",
                    artefact=artefact,
                    diagnostics=list(attempted),
                    suggested_resolution="Resume this session in assisted mode to "
                    "discuss it, or fix the listed issues and continue.",
                    issues=list(issues),
                    checkpoint=checkpoint,
                    at=now(),
                )
            )
        self.state.add_evidence(
            f"{spec(stage).title} blocked",
            EvidenceStatus.UNRESOLVED,
            list(issues)[:5],
            stage,
        )
        self.state.say(
            "agent" if reported else "system",
            "blocker",
            f"{spec(stage).title} is blocked: "
            + "; ".join(
                [str(item.get("decision")) for item in reported] or list(issues)[:3]
            ),
            stage=stage,
        )

    # -------------------------------------------------------- reviews

    def _source_inspections(self, stage: Stage | None) -> int:
        if stage is None:
            return 0
        return sum(
            1
            for item in self.state.stages[stage].investigation
            if item.split(" ", 1)[0].split("(", 1)[0] in SOURCE_INSPECTIONS
        )

    def _stage_changed(self, stage: Stage | None) -> bool:
        """Whether the stage's draft changed since the stage started."""
        if stage is None or stage not in LAYER_FOR_STAGE:
            return False
        baseline = self.state.stages[stage].baseline_sha256
        return baseline is not None and baseline != self._draft_sha(stage)

    def _start_stage(self, stage: Stage) -> None:
        record = self.state.stages[stage]
        record.started_at = record.started_at or now()
        if stage in LAYER_FOR_STAGE and record.baseline_sha256 is None:
            record.baseline_sha256 = self._draft_sha(stage)

    def _draft_sha(self, stage: Stage) -> str | None:
        layer = LAYER_FOR_STAGE.get(stage)
        if layer is None:
            return None
        sha = read_layer(self.root, layer).file.sha256
        if layer == "execution-profiles":
            # The profile's configuration lives in its native config files.
            from nf_splice.layers.execution import list_config_drafts

            configs = [
                read_layer(self.root, layer).file.sha256 or "",
                *(
                    (self.root / item).read_text(encoding="utf-8", errors="replace")
                    for item in list_config_drafts(self.root)
                ),
            ]
            sha = hashlib.sha256("\0".join(configs).encode()).hexdigest()
        return sha

    def _review_satisfied(self, stage: Stage) -> bool:
        """Whether this layer stage has a current AI review (never the gate)."""
        if stage not in LAYER_FOR_STAGE:
            return True
        review = self.state.stages[stage].review
        current = self._draft_sha(stage)
        if review is not None and review.outcome in {"changed", "no_change"}:
            if review.draft_sha256 == current:
                return True
        if self.state.policy.review == "reuse_unchanged":
            previous = self.store.latest_review(stage, exclude=self.state.id)
            if (
                previous is not None
                and previous.draft_sha256 == current
                and previous.sources_fingerprint == self._fingerprints()[1]
            ):
                self.state.stages[stage].review = previous.model_copy(
                    update={"outcome": previous.outcome}
                )
                self.state.say(
                    "system",
                    "review_reused",
                    f"{spec(stage).title}: reusing the review of {previous.at}; "
                    "the draft and sources are unchanged since.",
                    stage=stage,
                )
                return True
        return False

    def _record_review(
        self,
        stage: Stage,
        outcome: str,
        details: dict[str, Any] | None,
    ) -> None:
        details = details or {}
        record = self.state.stages[stage]
        report = coverage(
            self.root,
            stage.value,
            record.investigation,
            examples=bool(self._examples()),
        )
        assessment = details.get("draft_assessment") or {}
        record.review = ReviewRecord(
            kind="scientific" if stage in _SCIENTIFIC else "operational",
            outcome=outcome,
            basis="revised" if outcome == "changed" else "verified_unchanged",
            evidence=[str(item) for item in details.get("evidence") or []],
            draft_assessment={
                key: [str(item) for item in assessment.get(key) or []]
                for key in (
                    "omissions",
                    "incorrect_assumptions",
                    "unsupported_declarations",
                    "confirmed",
                )
            },
            coverage=[item.to_json() for item in report.classes],
            gaps=report.gap_lines(),
            summary=str(details.get("summary") or ""),
            checked=[str(item) for item in details.get("checked") or []],
            findings=[str(item) for item in details.get("findings") or []],
            uncertainties=[str(item) for item in details.get("uncertainties") or []],
            inspected=list(record.investigation),
            draft_sha256=self._draft_sha(stage),
            sources_fingerprint=self._fingerprints()[1],
            provider=self.state.provider.name,
            model=self.state.provider.model,
            reasoning_effort=self.state.provider.reasoning_applied,
            at=now(),
        )
        self.state.say(
            "agent",
            "review",
            f"{spec(stage).title} review ({record.review.kind}): "
            f"{record.review.summary or outcome}",
            stage=stage,
            data={"inspected": len(record.investigation)},
        )

    def _record_outcome(self, stage: Stage | None, outcome: TurnOutcome) -> None:
        if stage is not None:
            record = self.state.stages[stage]
            for entry in outcome.inspected:
                if entry not in record.investigation:
                    record.investigation.append(entry)
        for item in outcome.evidence:
            self.state.add_evidence(
                str(item.get("claim", "")),
                EvidenceStatus(str(item.get("status", "unresolved"))),
                [str(value) for value in item.get("sources") or []],
                stage,
            )
        for denial in outcome.denied:
            self.state.say("system", "denied", denial, stage=stage)

    # -------------------------------------------------------- provider turns

    def _history_context(self) -> str:
        """A bounded summary of the session for providers without continuation."""
        entries = [
            item
            for item in self.state.conversation
            if item.kind not in {"external_change", "stage_complete"}
        ][-12:]
        if not entries:
            return ""
        lines = [
            f"- [{item.role}/{item.kind}] {_ellipsise(item.text)}" for item in entries
        ]
        return (
            "\n\nEarlier in this session (nf-splice's record; the drafts and "
            "gates are the source of truth, not this summary):\n" + "\n".join(lines)
        )

    def _account_usage(self, data: Any) -> None:
        cost = data.get("cost_usd")
        record = self.state.usage.by_provider.setdefault(
            self.state.provider.name,
            {"turns": 0, "cost_usd": 0.0, "billing": self.state.provider.billing},
        )
        record["turns"] = int(record.get("turns", 0)) + 1
        if cost is not None:
            self.state.usage.cost_usd += float(cost)
            self.state.usage.cost_reported = True
            record["cost_usd"] = float(record.get("cost_usd", 0.0)) + float(cost)
        for key in ("input_tokens", "output_tokens"):
            if data.get(key) is not None:
                record[key] = int(record.get(key, 0)) + int(data[key])

    async def _turn(
        self,
        purpose: str,
        stage: Stage | None,
        instruction: str,
        toolbox: SessionToolbox,
    ) -> TurnOutcome:
        provider = self._require_provider()
        if self._session is None:
            self._session = provider.open(self.root)
        session = self._session
        budgets = self.state.policy.budgets
        spent = self.state.usage.cost_usd
        remaining = (
            None
            if budgets.max_budget_usd is None
            else max(budgets.max_budget_usd - spent, 0.0)
        )
        if remaining == 0.0:
            raise ProviderInterrupted(
                ProviderError(
                    ProviderErrorKind.BUDGET_EXHAUSTED,
                    "the session's spending budget is used up",
                    "Resume with a larger --max-budget-usd or continue manually.",
                )
            )
        if self.state.provider.conversation_ref is None:
            instruction += self._history_context()
        request = TurnRequest(
            purpose=purpose,
            instruction=instruction,
            system_prompt=system_prompt(purpose, stage),
            tools=toolbox,
            stage=stage.value if stage else None,
            max_turns=budgets.max_turns_per_step,
            timeout_seconds=budgets.turn_timeout_seconds,
            max_budget_usd=remaining,
            model=budgets.model or self.state.provider.model,
            conversation_ref=self.state.provider.conversation_ref,
            reasoning_effort=budgets.reasoning_effort,
        )
        messages: list[str] = []

        async def consume(events: AsyncIterator[Any]) -> None:
            async for event in events:
                if event.kind is EventKind.MESSAGE and event.text:
                    messages.append(event.text)
                elif event.kind is EventKind.ERROR:
                    toolbox.outcome.failures.append(event.text)
                elif event.kind is EventKind.USAGE:
                    self._account_usage(event.data)
                elif event.kind is EventKind.NOTICE and event.text:
                    toolbox.outcome.notices.append(event.text)
                if self._cancel.is_set():
                    await session.cancel()
                    break

        attempt = 0
        while True:
            # Persist before every provider request, so nothing is lost if the
            # process, the network or the provider stops here.
            self.state.usage.provider_turns += 1
            self.store.save(self.state)
            try:
                await asyncio.wait_for(
                    consume(session.turn(request)),
                    timeout=budgets.turn_timeout_seconds,
                )
                break
            except asyncio.TimeoutError:
                await session.cancel()
                toolbox.outcome.failures.append(
                    f"the provider turn exceeded {budgets.turn_timeout_seconds:.0f} s"
                )
                break
            except ProviderUnavailable:
                raise
            except ProviderError as error:
                untouched = not (
                    toolbox.outcome.staged
                    or toolbox.outcome.executed
                    or toolbox.outcome.denied
                    or messages
                )
                if (
                    error.kind in RETRYABLE
                    and attempt < 2
                    and untouched
                    and not self._cancel.is_set()
                ):
                    attempt += 1
                    delay = min(error.retry_after or 2.0 * 2**attempt, 60.0)
                    self.state.say(
                        "system",
                        "provider_retry",
                        f"{error} Retrying in {delay:.0f} s (attempt {attempt} of 2).",
                        stage=stage,
                    )
                    await asyncio.sleep(delay)
                    continue
                self.state.provider.conversation_ref = session.conversation_ref
                raise ProviderInterrupted(error) from error
            except Exception as error:
                # An unclassified provider failure ends the turn; the gate
                # still decides the stage.
                toolbox.outcome.failures.append(
                    f"provider error: {type(error).__name__}: {error}"
                )
                break
        self.state.provider.conversation_ref = session.conversation_ref
        provider_record = self.state.provider
        provider_record.reasoning_requested = budgets.reasoning_effort
        if toolbox.outcome.notices:
            provider_record.reasoning_notice = toolbox.outcome.notices[-1]
            for notice in toolbox.outcome.notices:
                if not any(
                    item.kind == "notice" and item.text == notice
                    for item in self.state.conversation
                ):
                    self.state.say("system", "notice", notice, stage=stage)
        supported = provider.capabilities.reasoning_efforts
        if budgets.reasoning_effort is None:
            provider_record.reasoning_applied = None
        elif not toolbox.outcome.notices and budgets.reasoning_effort in supported:
            provider_record.reasoning_applied = budgets.reasoning_effort
        elif toolbox.outcome.notices:
            text = toolbox.outcome.notices[-1]
            provider_record.reasoning_applied = next(
                (item for item in supported if f"'{item}' was used" in text), None
            )
        toolbox.outcome.messages = messages
        if messages:
            self.state.say("agent", "message", "\n\n".join(messages), stage=stage)
        for failure in toolbox.outcome.failures:
            self.state.say("system", "failure", failure, stage=stage)
        return toolbox.outcome

    def _pause_for_provider(self, interruption: ProviderInterrupted) -> SessionState:
        """Stop safely after a provider problem; the session resumes later."""
        error = interruption.error
        self.state.transaction = None
        for stage in ORDER:
            record = self.state.stages[stage]
            if record.status in {StageStatus.EXECUTING, StageStatus.REPAIRING}:
                record.status = StageStatus.PENDING
                record.attempts = max(record.attempts - 1, 0)
        self.state.interruption = error.to_json()
        self.state.status = SessionStatus.PAUSED
        self.state.say(
            "system",
            "provider_interrupted",
            f"The provider stopped the session: {error}. Your work is saved; resume "
            "with `nf-splice session resume` (optionally with another provider), "
            "or continue manually.",
            data=error.to_json(),
        )
        self._save()
        return self.state

    def switch_provider(
        self, provider: AgentProvider, actor: Actor, *, model: str | None = None
    ) -> SessionState:
        """Use another provider or model; nf-splice's record carries the context."""
        require_tool_calling(provider)
        require_consent(provider, self.state.policy.allow_remote_model)
        self._require_idle()
        capabilities = provider.capabilities
        previous = self.state.provider
        self.state.provider_history.append(
            {"provider": previous.name, "model": previous.model or "", "until": now()}
        )
        self.state.provider = ProviderRecord(
            name=capabilities.name,
            remote=capabilities.remote,
            model=model or getattr(provider, "model", None),
            billing=capabilities.billing,
            inference=capabilities.inference,
            script=previous.script if capabilities.name == previous.name else None,
        )
        self.provider = provider
        self._session = None
        self.state.say(
            "user",
            "provider",
            f"{actor.label} switched the provider from {previous.name} to "
            f"{capabilities.name}" + (f" ({model})" if model else "") + ".",
        )
        self._save()
        return self.state

    def _toolbox(
        self,
        mode: ToolMode,
        stage: Stage | None,
        operations: set[str],
        controls: set[str],
        *,
        approved_by: Actor | None = None,
        sandbox: Sandbox | None = None,
    ) -> SessionToolbox:
        change = self._change(approved_by)
        if mode is ToolMode.STAGE and self.state.mode is InteractionMode.ASSISTED:
            change = self._change(_PREVIEW_APPROVER)
        return SessionToolbox(
            root=self.root,
            policy=self.state.policy,
            mode=mode,
            operations=operations,
            controls=controls,
            change=change,
            usage=self.state.usage,
            stage_layer=LAYER_FOR_STAGE.get(stage) if stage else None,
            examples=self._examples(),
            session_directory=self.session_directory,
            sandbox=sandbox,
            log=self._log,
            prior_investigation=(
                self.state.stages[stage].investigation if stage is not None else ()
            ),
            stage=stage.value if stage in LAYER_FOR_STAGE else None,
            stage_changed=self._stage_changed(stage),
        )

    # -------------------------------------------------------- assisted planning

    def _proposal(
        self,
        stage: Stage,
        operations: list[PlannedOperation],
        sandbox: Sandbox,
        details: dict[str, Any],
        revision: int,
    ) -> Proposal:
        drafts, sources = self._fingerprints()
        layer = LAYER_FOR_STAGE.get(stage)
        proposal = Proposal(
            id=f"proposal-{len(self.state.proposals) + 1}",
            stage=stage,
            revision=revision,
            summary=str(details.get("summary") or f"Changes for {spec(stage).title}"),
            operations=operations,
            evidence=[str(item) for item in details.get("evidence") or []],
            uncertainties=[str(item) for item in details.get("uncertainties") or []],
            validation_gate=str(
                details.get("validation_gate")
                or f"{spec(stage).title} validation (nf-splice draft validate)"
            ),
            diff=sandbox.diff()[:60000],
            preview_issues=sandbox.issues([layer]) if layer else [],
            drafts_fingerprint=drafts,
            sources_fingerprint=sources,
            created_at=now(),
        )
        self.state.pending = proposal
        self._store_proposal(proposal)
        self.state.status = SessionStatus.AWAITING_APPROVAL
        self.state.stages[stage].status = StageStatus.NEEDS_APPROVAL
        self.state.say(
            "agent",
            "proposal",
            proposal_text(proposal),
            stage=stage,
            data={"proposal": proposal.id},
        )
        return proposal

    def _deterministic_proposal(
        self, stage: Stage, operations: list[PlannedOperation], summary: str
    ) -> Proposal:
        sandbox = Sandbox(self.root, self._staging(), self._examples())
        try:
            toolbox = self._toolbox(
                ToolMode.STAGE,
                stage,
                {item.tool for item in operations},
                set(),
                sandbox=sandbox,
            )
            for item in operations:
                result = toolbox.call(item.tool, item.arguments)
                if not result.get("success"):
                    raise SessionError(
                        f"{item.tool} cannot run: {'; '.join(result.get('issues', []))}"
                    )
            return self._proposal(
                stage, toolbox.outcome.staged, sandbox, {"summary": summary}, 1
            )
        finally:
            sandbox.close()

    async def _plan(
        self,
        stage: Stage,
        purpose: str,
        instruction: str,
        *,
        revision: int = 1,
    ) -> tuple[Proposal | None, TurnOutcome]:
        sandbox = Sandbox(self.root, self._staging(), self._examples())
        try:
            controls = set(_PLAN_CONTROLS)
            if purpose == "objection":
                controls.add("assess_objection")
            toolbox = self._toolbox(
                ToolMode.STAGE,
                stage,
                set(READ_OPERATIONS) | set(spec(stage).operations),
                controls,
                sandbox=sandbox,
            )
            outcome = await self._turn(purpose, stage, instruction, toolbox)
            self._record_outcome(stage, outcome)
            if not outcome.staged:
                return None, outcome
            details = dict(outcome.proposal or {})
            if not details.get("summary") and outcome.messages:
                details["summary"] = outcome.messages[-1][:2000]
            return (
                self._proposal(stage, outcome.staged, sandbox, details, revision),
                outcome,
            )
        finally:
            sandbox.close()

    def _await_input(self, stage: Stage, message: str) -> None:
        self.state.status = SessionStatus.AWAITING_INPUT
        self.state.say("agent", "question", message, stage=stage)

    async def _plan_stage(
        self, stage: Stage, issues: list[str] | None = None, guidance: str = ""
    ) -> bool:
        """Plan one stage; True when its review finished it with no change."""
        record = self.state.stages[stage]
        record.attempts += 1
        instruction = stage_instruction(
            self.root, self.state, stage, issues=issues, attempt=record.attempts
        )
        if guidance:
            instruction += "\n\nThe user's guidance:\n" + guidance
        proposal, outcome = await self._plan(stage, "plan", instruction)
        if proposal is not None:
            return False
        if outcome.review is not None and stage in LAYER_FOR_STAGE:
            result = gate(stage, self.root)
            if result.passed and not outcome.blockers:
                self._record_review(stage, "no_change", outcome.review)
                self._complete(stage, result, "reviewed; no change was needed")
                return True
            self._await_input(
                stage,
                f"I reviewed {spec(stage).title} but it still fails its validation: "
                + "; ".join(result.issues[:5])
                + ". Tell me how to proceed, or edit the draft and continue.",
            )
            return False
        if outcome.blockers:
            self._block(stage, record.issues, outcome.blockers, [])
        self._await_input(
            stage,
            "I could not propose a sound change for "
            f"{spec(stage).title}. "
            + (
                "; ".join(str(item.get("decision")) for item in outcome.blockers)
                or "Tell me how you would like to proceed, or edit the draft and "
                "continue."
            ),
        )
        return False

    # -------------------------------------------------------- execution

    async def _execute(
        self,
        stage: Stage,
        operations: list[PlannedOperation],
        approved_by: Actor | None,
    ) -> str | None:
        """Apply planned operations under a checkpoint; roll back on failure."""

        def run() -> str | None:
            checkpoint = self.store.checkpoint(
                self.state, stage, f"before applying {len(operations)} change(s)"
            )
            self.state.transaction = Transaction(
                id=f"transaction-{len(self.state.checkpoints)}",
                stage=stage,
                checkpoint=checkpoint.id,
                started_at=now(),
                operations=[item.tool for item in operations],
            )
            self.store.save(self.state)
            toolbox = self._toolbox(
                ToolMode.EXECUTE,
                stage,
                {item.tool for item in operations},
                set(),
                approved_by=approved_by,
            )
            failure = None
            try:
                for item in operations:
                    result = toolbox.call(item.tool, item.arguments)
                    if not result.get("success"):
                        failure = f"{item.tool}: " + "; ".join(
                            str(value) for value in result.get("issues", [])
                        )
                        break
                if failure is not None:
                    self.store.restore(self.state, checkpoint.id)
            except BaseException:
                self.store.restore(self.state, checkpoint.id)
                self.state.transaction = None
                self.store.save(self.state)
                raise
            self.state.transaction = None
            return failure

        if self._locked:
            return run()
        with self.store.mutation_lock(self.state.id):
            self._locked = True
            try:
                return run()
            finally:
                self._locked = False

    # -------------------------------------------------------- deterministic stages

    def _validate_stage(self) -> None:
        result = gate(Stage.VALIDATE, self.root)
        record = self.state.stages[Stage.VALIDATE]
        if result.passed:
            self._complete(Stage.VALIDATE, result)
            return
        record.attempts += 1
        failing = []
        for stage, layer in LAYER_FOR_STAGE.items():
            try:
                ready = validate_layer(self.root, layer).ready
            except ValueError:
                ready = False
            if not ready:
                failing.append(stage)
        reopenable = [
            item
            for item in failing
            if self.state.stages[item].status is StageStatus.COMPLETED
        ]
        if (
            reopenable
            and record.attempts <= self.state.policy.budgets.max_stage_attempts
        ):
            for item in reopenable:
                self.state.stages[item].status = StageStatus.PENDING
                self.state.stages[item].notes.append(
                    "reopened by cross-layer validation"
                )
            record.status = StageStatus.PENDING
            record.issues = list(result.issues)
            return
        self._block(Stage.VALIDATE, result.issues, [], ["cross-layer plan_promotion"])

    def _verify_stage(self) -> dict[str, Any]:
        directory = self.session_directory / "analysis-output"
        directory.mkdir(parents=True, exist_ok=True)
        result = assess(
            self.root,
            examples=self._examples(),
            permitted=[item.value for item in self.state.policy.grants],
            analysis_output_directory=directory,
        ).to_json()
        contract = result["contract_validity"]["status"]
        self.state.add_evidence(
            f"Contract validity: {contract}",
            EvidenceStatus.TOOL_VERIFIED
            if contract == "valid"
            else EvidenceStatus.UNRESOLVED,
            ["nf-splice validate"],
            Stage.VERIFY,
        )
        observed = result["observed_output_compatibility"]
        for example in observed["examples"]:
            reconciliation = example["reconciliation"]
            self.state.add_evidence(
                f"Example {reconciliation['example']}: "
                f"{sum(reconciliation['classified'].values())} classified, "
                f"{len(reconciliation['unclassified'])} unclassified, "
                f"{len(reconciliation['ambiguous'])} ambiguous; analysis_output.json "
                f"{example['analysis_output']['status']}",
                EvidenceStatus.OBSERVED,
                [reconciliation["example"]],
                Stage.VERIFY,
            )
        self.state.add_evidence(
            result["coverage_assessment"]["statement"],
            EvidenceStatus.STATICALLY_INFERRED,
            ["analyse_routes"],
            Stage.VERIFY,
        )
        for check in result["optional_checks"]:
            self.state.add_evidence(
                f"{check['name']}: {check['status']} ({check['reason']})",
                EvidenceStatus.TOOL_VERIFIED
                if check["status"] in {"passed", "passed_with_warnings", "failed"}
                else EvidenceStatus.UNRESOLVED,
                [check["tool"]],
                Stage.VERIFY,
            )
        self._complete(
            Stage.VERIFY,
            GateResult(True, (), f"contract {contract}; observed {observed['status']}"),
        )
        return result

    def _skip(self, stage: Stage, reason: str) -> None:
        record = self.state.stages[stage]
        record.status = StageStatus.SKIPPED
        record.summary = reason
        record.completed_at = now()
        self.state.say("system", "stage_skipped", f"{spec(stage).title}: {reason}")

    def _export_stage(self) -> None:
        """Write and verify the bundle archive (deterministic, private folder)."""
        if not self.state.policy.granted(Permission.EXPORT):
            self._skip(Stage.EXPORT, "exporting is not permitted in this session")
            return
        default = default_archive_path(self.root, ExportScope.BUNDLE)
        target = default.with_name(f"{default.stem}-{self.state.id}.zip")
        try:
            result = export_archive(
                self.root, ExportScope.BUNDLE, target, overwrite=True
            )
        except ExportError as error:
            self._block(Stage.EXPORT, [str(error)], [], ["export_archive"])
            return
        self.state.export = result.to_json()
        self.state.add_evidence(
            f"Archive {result.path} verified: " + "; ".join(result.checks),
            EvidenceStatus.TOOL_VERIFIED,
            [result.sha256],
            Stage.EXPORT,
        )
        self._complete(
            Stage.EXPORT,
            GateResult(True, (), f"verified archive, SHA-256 {result.sha256[:12]}"),
        )

    def _commit_stage(self, *, assisted: bool) -> bool:
        """Commit locally when permitted; returns True when awaiting approval."""
        if not self.state.policy.granted(Permission.GIT_COMMIT):
            self._skip(
                Stage.COMMIT,
                "not committed: the session does not have the git_commit permission; "
                "run `nf-splice git commit` when you are ready",
            )
            return False
        if not is_git_work_tree(self.root):
            self._skip(
                Stage.COMMIT, "not committed: the working copy is not a Git repository"
            )
            return False
        operations = [
            PlannedOperation(
                tool="git_commit",
                arguments={
                    "message": f"Publish the SPLICE workflow bundle ({self.state.id})"
                },
                description="commit the validated splice/ and .gitignore locally",
            )
        ]
        if assisted:
            drafts, sources = self._fingerprints()
            proposal = Proposal(
                id=f"proposal-{len(self.state.proposals) + 1}",
                stage=Stage.COMMIT,
                summary="Commit the validated bundle to the local branch "
                "(nothing is pushed).",
                operations=operations,
                validation_gate="splice/ and .gitignore have no uncommitted changes",
                diff=gitops.diff(self.root)[:60000],
                drafts_fingerprint=drafts,
                sources_fingerprint=sources,
                created_at=now(),
            )
            self.state.pending = proposal
            self._store_proposal(proposal)
            self.state.status = SessionStatus.AWAITING_APPROVAL
            self.state.stages[Stage.COMMIT].status = StageStatus.NEEDS_APPROVAL
            self.state.say(
                "agent", "proposal", proposal_text(proposal), stage=Stage.COMMIT
            )
            return True
        toolbox = self._toolbox(ToolMode.EXECUTE, Stage.COMMIT, {"git_commit"}, set())
        result = toolbox.call("git_commit", operations[0].arguments)
        if not result.get("success"):
            self._block(
                Stage.COMMIT, list(result.get("issues", [])), [], ["git_commit"]
            )
            return False
        self.state.commit = result
        self._complete(Stage.COMMIT, gate(Stage.COMMIT, self.root))
        return False

    def _finish(self) -> None:
        if (
            self.state.stages[Stage.VERIFY].status is not StageStatus.COMPLETED
            or self.state.assessment is None
        ):
            self.state.assessment = self._verify_stage()
        self.state.stages[Stage.REPORT].status = StageStatus.COMPLETED
        self.state.stages[Stage.REPORT].completed_at = now()
        report = build_report(self.root, self.store, self.state, self.state.assessment)
        self.state.report = report
        self.state.current_stage = None
        complete = report["completion"] == "complete"
        self.state.status = (
            SessionStatus.COMPLETED
            if complete
            else SessionStatus.BLOCKED
            if self.state.mode is InteractionMode.AUTONOMOUS
            else SessionStatus.AWAITING_INPUT
        )
        self.state.say(
            "agent",
            "report",
            report_text(report),
            data={"completion": report["completion"]},
        )

    # -------------------------------------------------------- assisted mode

    async def _advance(self) -> SessionState:
        """Move the session forward until it needs the user or finishes."""
        self._prepare()
        state = self.state
        if state.status in {SessionStatus.COMPLETED, SessionStatus.CANCELLED}:
            self._save()
            return state
        if state.mode is InteractionMode.MANUAL or state.status is SessionStatus.PAUSED:
            raise SessionError("the session is paused; resume it to continue")
        if state.mode is InteractionMode.AUTONOMOUS:
            return await self._run_autonomous()
        if state.pending is not None:
            state.status = SessionStatus.AWAITING_APPROVAL
            self._save()
            return state
        state.status = SessionStatus.ACTIVE
        while True:
            stage = self._next_stage()
            state.current_stage = stage
            if stage is None and state.focus is not None:
                state.say(
                    "system",
                    "focus_done",
                    f"{spec(state.focus).title} is complete; ask for help with "
                    "another section, or continue the whole integration.",
                )
                state.focus = None
                break
            if stage is None:
                self._finish()
                break
            record = state.stages[stage]
            self._start_stage(stage)
            if stage is Stage.VALIDATE:
                self._validate_stage()
                if state.stages[Stage.VALIDATE].status is StageStatus.BLOCKED:
                    self._await_input(
                        stage,
                        "Cross-layer validation still fails: "
                        + "; ".join(state.stages[stage].issues[:5]),
                    )
                    break
                continue
            if stage is Stage.VERIFY:
                state.assessment = self._verify_stage()
                continue
            if stage is Stage.EXPORT:
                self._export_stage()
                continue
            if stage is Stage.COMMIT:
                if self._commit_stage(assisted=True):
                    break
                continue
            if stage is Stage.REPORT:
                self._finish()
                break
            result = gate(stage, self.root)
            if result.passed and self._review_satisfied(stage):
                self._complete(
                    stage,
                    result,
                    "validated and reviewed"
                    if stage in LAYER_FOR_STAGE
                    else "already satisfied by the current files",
                )
                continue
            if stage is Stage.DISCOVER:
                self._deterministic_proposal(
                    stage,
                    [
                        PlannedOperation(
                            tool="initialise_drafts",
                            arguments={"accept_detected": False},
                            description="create the missing drafts from repository "
                            "evidence (existing drafts are kept)",
                        )
                    ],
                    "Create the missing drafts from the repository's evidence.",
                )
                break
            if stage is Stage.BUILD:
                if not state.policy.granted(Permission.BUILD):
                    self._await_input(
                        stage,
                        "Every layer is ready. Building needs the build permission; "
                        "grant it or run `nf-splice build all` yourself.",
                    )
                    break
                self._deterministic_proposal(
                    stage,
                    [
                        PlannedOperation(
                            tool="build_bundle",
                            arguments={},
                            description="publish the validated drafts into splice/",
                        )
                    ],
                    "Every layer validates. Publish the bundle into splice/.",
                )
                break
            record.issues = list(result.issues)
            if record.attempts >= state.policy.budgets.max_stage_attempts:
                self._await_input(
                    stage,
                    f"{spec(stage).title} still needs work after {record.attempts} "
                    "attempt(s): "
                    + ("; ".join(record.issues[:5]) or "its review is not complete")
                    + ". Tell me how to proceed, or edit the draft and continue.",
                )
                break
            if await self._plan_stage(stage):
                continue
            break
        self._save()
        return state

    async def _approve(self, actor: Actor) -> SessionState:
        """Apply the pending proposal exactly as shown, then validate it."""
        if actor.kind is not ActorKind.HUMAN:
            raise SessionError("approval needs a person's name (--user)")
        previous = self.state.pending
        self._prepare()
        proposal = self.state.pending
        if proposal is None:
            self._save()
            if previous is not None:
                raise StaleProposal(
                    f"{previous.id} is stale: files changed after it was proposed; "
                    "continue the session to plan again"
                )
            raise SessionError("nothing is waiting for approval")
        drafts, sources = self._fingerprints()
        if (
            drafts != proposal.drafts_fingerprint
            or sources != proposal.sources_fingerprint
        ):
            self._withdraw_pending("stale: files changed after it was made")
            self._save()
            raise StaleProposal(
                f"{proposal.id} is stale: files changed after it was proposed; "
                "continue the session to plan again"
            )
        self.state.approvals.append(
            ApprovalRecord(
                proposal_id=proposal.id,
                stage=proposal.stage,
                decision="approved",
                actor=actor.label,
                actor_kind=actor.kind.value,
                at=now(),
                operations_sha256=_digest(proposal.operations),
                drafts_fingerprint=proposal.drafts_fingerprint,
            )
        )
        self.state.say("user", "approval", f"{actor.label} approved {proposal.id}.")
        stage = proposal.stage
        self.state.current_stage = stage
        self.state.stages[stage].status = StageStatus.EXECUTING
        failure = await self._execute(stage, proposal.operations, actor)
        proposal.status = "applied" if failure is None else "failed"
        self._store_proposal(proposal)
        self.state.pending = None
        if failure is not None:
            self.state.stages[stage].status = StageStatus.VALIDATION_FAILED
            self.state.say(
                "system",
                "failure",
                f"Applying {proposal.id} failed and was rolled back: {failure}",
                stage=stage,
            )
            await self._plan_stage(stage, issues=[failure])
            self._save()
            return self.state
        self.state.add_evidence(
            f"{actor.label} approved: {proposal.summary}",
            EvidenceStatus.HUMAN_CONFIRMED,
            [proposal.id],
            stage,
        )
        result = gate(stage, self.root)
        if result.passed:
            if stage in LAYER_FOR_STAGE:
                self._record_review(
                    stage,
                    "changed",
                    {
                        "summary": proposal.summary,
                        "checked": proposal.evidence,
                        "evidence": proposal.evidence,
                        "uncertainties": proposal.uncertainties,
                    },
                )
            self._complete(stage, result)
            self._save()
            return await self._advance()
        record = self.state.stages[stage]
        record.status = StageStatus.VALIDATION_FAILED
        record.issues = list(result.issues)
        self.state.say(
            "system",
            "validation",
            f"{spec(stage).title} validation after the change: "
            + "; ".join(result.issues[:10]),
            stage=stage,
        )
        if record.attempts < self.state.policy.budgets.max_stage_attempts:
            record.status = StageStatus.REPAIRING
            await self._plan_stage(stage, issues=list(result.issues))
        else:
            self._await_input(
                stage,
                f"{spec(stage).title} still fails validation; tell me how to proceed.",
            )
        self._save()
        return self.state

    async def _object(self, text: str, actor: Actor) -> SessionState:
        """Investigate the user's objection; never treat it as approval."""
        self._prepare()
        proposal = self.state.pending
        if proposal is None:
            self._save()
            raise SessionError(
                "there is no proposal to object to; ask a question instead"
            )
        self.state.approvals.append(
            ApprovalRecord(
                proposal_id=proposal.id,
                stage=proposal.stage,
                decision="objected",
                actor=actor.label,
                actor_kind=actor.kind.value,
                at=now(),
                operations_sha256=_digest(proposal.operations),
                drafts_fingerprint=proposal.drafts_fingerprint,
                note=text[:4000],
            )
        )
        self.state.say("user", "objection", text, stage=proposal.stage)
        instruction = objection_instruction(self.root, self.state, proposal, text)
        revised, outcome = await self._plan(
            proposal.stage, "objection", instruction, revision=proposal.revision + 1
        )
        assessment = outcome.assessment
        if assessment:
            self.state.say(
                "agent",
                "assessment",
                f"Assessment: {assessment.get('assessment')}. "
                f"{assessment.get('explanation', '')}",
                stage=proposal.stage,
                data=assessment,
            )
            self.state.add_evidence(
                f"Objection assessed as {assessment.get('assessment')}: "
                f"{assessment.get('explanation', '')}",
                EvidenceStatus.STATICALLY_INFERRED,
                [str(item) for item in assessment.get("evidence") or []],
                proposal.stage,
            )
        else:
            self.state.say(
                "system",
                "assessment_missing",
                "The agent did not record an assessment of the objection.",
                stage=proposal.stage,
            )
        if revised is not None:
            proposal.status = "superseded"
            self._store_proposal(proposal)
        else:
            self.state.pending = proposal
            self.state.status = SessionStatus.AWAITING_APPROVAL
            self.state.stages[proposal.stage].status = StageStatus.NEEDS_APPROVAL
        self._save()
        return self.state

    async def _reply(self, text: str, actor: Actor) -> SessionState:
        """Answer the agent's question and let it plan the stage again."""
        self._prepare()
        if self.state.pending is not None:
            self._save()
            raise SessionError(
                "a proposal is waiting: approve it, object to it or ask about it"
            )
        if self.state.mode is not InteractionMode.ASSISTED:
            self._save()
            raise SessionError("replies are part of AI-assisted sessions")
        self.state.say("user", "reply", f"{actor.label}: {text}")
        stage = self._next_stage()
        if (
            stage is None
            or spec(stage).deterministic
            or stage
            in {
                Stage.DISCOVER,
                Stage.BUILD,
            }
        ):
            self.state.status = SessionStatus.ACTIVE
            self._save()
            return await self._advance()
        record = self.state.stages[stage]
        record.status = StageStatus.PENDING
        record.attempts = 0
        self.state.status = SessionStatus.ACTIVE
        self.state.current_stage = stage
        if await self._plan_stage(stage, guidance=text):
            self._save()
            return await self._advance()
        self._save()
        return self.state

    async def _ask(self, text: str, actor: Actor) -> str:
        """Answer a question within the session without changing anything."""
        self._prepare()
        self.state.say("user", "question", text, stage=self.state.current_stage)
        toolbox = self._toolbox(
            ToolMode.OBSERVE,
            self.state.current_stage,
            set(READ_OPERATIONS),
            {"record_evidence"},
        )
        context = ""
        if self.state.pending is not None:
            context = "\n\nThe current proposal is:\n" + proposal_text(
                self.state.pending
            )
        outcome = await self._turn(
            "question",
            self.state.current_stage,
            f"Objective: {self.state.objective}{context}\n\nThe user asks: {text}",
            toolbox,
        )
        self._record_outcome(self.state.current_stage, outcome)
        self._save()
        return "\n\n".join(outcome.messages) or "The agent gave no answer."

    # -------------------------------------------------------- autonomous mode

    async def _autonomous_layer(self, stage: Stage) -> None:
        record = self.state.stages[stage]
        checkpoint = self.store.checkpoint(self.state, stage, "before autonomous work")
        previous: tuple[str, tuple[str, ...]] | None = None
        result = gate(stage, self.root)
        outcome = TurnOutcome()
        attempted: list[str] = []
        reviewed: dict[str, Any] | None = None
        while record.attempts < self.state.policy.budgets.max_stage_attempts:
            if self._cancel.is_set():
                return
            record.attempts += 1
            record.status = (
                StageStatus.EXECUTING if record.attempts == 1 else StageStatus.REPAIRING
            )
            self.state.transaction = Transaction(
                id=f"transaction-{stage.value}-{record.attempts}",
                stage=stage,
                checkpoint=checkpoint.id,
                started_at=now(),
                operations=["agent turn"],
            )
            self.store.save(self.state)
            toolbox = self._toolbox(
                ToolMode.EXECUTE,
                stage,
                set(READ_OPERATIONS) | set(spec(stage).operations),
                set(_EXECUTE_CONTROLS),
            )
            instruction = stage_instruction(
                self.root,
                self.state,
                stage,
                issues=list(result.issues),
                attempt=record.attempts,
            )
            if result.passed and record.attempts > 1 and reviewed is None:
                instruction += (
                    "\n\nThe draft validates, but the review is not finished: "
                    "inspect the pipeline's sources for this stage, improve the "
                    "draft where the evidence says so, then call complete_review."
                )
            outcome = await self._turn("execute", stage, instruction, toolbox)
            self.state.transaction = None
            self._record_outcome(stage, outcome)
            attempted.extend(outcome.executed)
            reviewed = outcome.review or reviewed
            result = gate(stage, self.root)
            # A decision the agent says it cannot make keeps the stage open even
            # when validation passes: an optional field may be what is undecided.
            # Passing validation alone never completes a layer: it needs the
            # agent's review of the content against the sources.
            if result.passed and not outcome.blockers and reviewed is not None:
                self._record_review(
                    stage, "changed" if attempted else "no_change", reviewed
                )
                self._complete(stage, result)
                self.store.save(self.state)
                return
            if (
                result.passed
                and not outcome.blockers
                and reviewed is None
                and any(item.startswith("complete_review:") for item in outcome.denied)
            ):
                # A refused review is a procedural nudge, not a failed
                # authoring attempt: like a provider interruption (see
                # _pause_for_provider) it refunds the attempt. The
                # no-progress check below stays the runaway guard.
                record.attempts = max(record.attempts - 1, 0)
            record.issues = list(result.issues)
            signature = (
                drafts_fingerprint(self.root, include_reviews=False),
                tuple(sorted(result.issues)),
            )
            if outcome.blockers or outcome.budget_exhausted or signature == previous:
                if signature == previous:
                    record.notes.append(
                        "stopped retrying: no progress since the last attempt"
                    )
                break
            previous = signature
            self.store.save(self.state)
        blockers = list(outcome.blockers)
        if result.passed and not blockers and reviewed is None:
            blockers.append(
                {
                    "decision": f"The {spec(stage).title} draft validates, but its "
                    "review against the pipeline's sources was not completed",
                    "artefact": layer_spec(LAYER_FOR_STAGE[stage]).draft,
                    "suggested_resolution": "resume the session (or review the "
                    "draft yourself and continue manually)",
                }
            )
        if reviewed is not None:
            # Keep the review that was made: the stage stays blocked on the
            # recorded decision, and the report shows both.
            self._record_review(
                stage, "blocked: " + ("changed" if attempted else "no_change"), reviewed
            )
        self._block(
            stage,
            result.issues,
            blockers,
            [*attempted, f"validate_layer({LAYER_FOR_STAGE[stage]})"],
        )

    async def _run_autonomous(self) -> SessionState:
        state = self.state
        if not state.policy.approved_by:
            raise SessionError("autonomous mode needs a person to approve its scope")
        state.status = SessionStatus.RUNNING
        self._save()
        with self.store.mutation_lock(state.id):
            self._locked = True
            try:
                await self._autonomous_loop()
            finally:
                self._locked = False
        if self._cancel.is_set() and state.status is not SessionStatus.COMPLETED:
            state.status = SessionStatus.PAUSED
            state.say(
                "system", "paused", "Stopped at your request; resume to continue."
            )
        self._save()
        return state

    async def _autonomous_loop(self) -> None:
        state = self.state
        while not self._cancel.is_set():
            if state.usage.tool_calls >= state.policy.budgets.max_tool_calls:
                state.say(
                    "system",
                    "budget",
                    "The tool-call budget is used up; stopping safely.",
                )
                for remaining in ORDER:
                    record = state.stages[remaining]
                    if (
                        record.status
                        not in {
                            StageStatus.COMPLETED,
                            StageStatus.BLOCKED,
                        }
                        and remaining not in FINISHING
                    ):
                        self._block(
                            remaining,
                            record.issues,
                            [
                                {
                                    "decision": "not attempted: the session's "
                                    "budget ran out",
                                    "suggested_resolution": "resume with a larger "
                                    "budget",
                                }
                            ],
                            [],
                        )
                break
            stage = self._next_stage()
            state.current_stage = stage
            if stage is None:
                break
            record = state.stages[stage]
            self._start_stage(stage)
            if stage is Stage.VALIDATE:
                self._validate_stage()
            elif stage is Stage.VERIFY:
                state.assessment = self._verify_stage()
            elif stage is Stage.EXPORT:
                self._export_stage()
            elif stage is Stage.COMMIT:
                self._commit_stage(assisted=False)
            elif stage is Stage.REPORT:
                break
            elif (result := gate(stage, self.root)).passed and self._review_satisfied(
                stage
            ):
                self._complete(
                    stage,
                    result,
                    "validated and reviewed"
                    if stage in LAYER_FOR_STAGE
                    else "already satisfied by the current files",
                )
            elif stage is Stage.DISCOVER:
                failure = await self._execute(
                    stage,
                    [PlannedOperation(tool="initialise_drafts", arguments={})],
                    None,
                )
                after = gate(stage, self.root)
                if failure is None and after.passed:
                    self._complete(stage, after)
                else:
                    self._block(stage, after.issues, [], ["initialise_drafts"])
            elif stage is Stage.BUILD:
                if not state.policy.granted(Permission.BUILD):
                    self._block(
                        stage,
                        (),
                        [
                            {
                                "decision": "Publishing into splice/ needs the build "
                                "permission, which this policy does not grant",
                                "artefact": "splice/",
                                "suggested_resolution": "run `nf-splice build all` "
                                "or resume with the build permission",
                            }
                        ],
                        [],
                    )
                else:
                    record.attempts += 1
                    failure = await self._execute(
                        stage,
                        [PlannedOperation(tool="build_bundle", arguments={})],
                        None,
                    )
                    after = gate(stage, self.root)
                    if failure is None and after.passed:
                        self._complete(stage, after)
                    else:
                        self._block(
                            stage,
                            [failure] if failure else after.issues,
                            [],
                            ["build_bundle", "validate_bundle"],
                        )
            else:
                await self._autonomous_layer(stage)
            self.store.save(state)
        if not self._cancel.is_set():
            self._finish()

    # -------------------------------------------------------- public steps

    async def advance(self) -> SessionState:
        """Move the session forward until it needs the user or finishes."""
        try:
            return await self._advance()
        except ProviderInterrupted as interruption:
            return self._pause_for_provider(interruption)

    async def _assist(self, stage: Stage, guidance: str, actor: Actor) -> SessionState:
        state = self.state
        if actor.kind is not ActorKind.HUMAN:
            raise SessionError("asking for a proposal needs a person's name (--user)")
        if state.mode is not InteractionMode.ASSISTED:
            raise SessionError("proposals are made in AI-assisted mode")
        if state.status is SessionStatus.CANCELLED:
            raise SessionError("a cancelled session cannot be resumed")
        self._require_idle()
        self._prepare()
        pending = state.pending
        if pending is not None and pending.stage is stage and not guidance:
            state.status = SessionStatus.AWAITING_APPROVAL
            self._save()
            return state
        if pending is not None:
            self._withdraw_pending(
                f"superseded: {actor.label} asked about {stage.value}"
            )
        state.focus = stage
        state.current_stage = stage
        state.status = SessionStatus.ACTIVE
        record = state.stages[stage]
        if record.status is not StageStatus.PENDING:
            record.status = StageStatus.PENDING
            record.attempts = 0
        self._start_stage(stage)
        state.say(
            "user",
            "assist",
            f"{actor.label} asked for help with {spec(stage).title}"
            + (f": {guidance}" if guidance else "."),
            stage=stage,
        )
        if await self._plan_stage(stage, guidance=guidance):
            state.focus = None
            state.status = SessionStatus.ACTIVE
        self._save()
        return state

    async def assist(
        self, stage: Stage, actor: Actor, guidance: str = ""
    ) -> SessionState:
        """Investigate one stage on request and propose a revision of it.

        The session works on that stage alone: the proposal waits for the
        person's approval, and once the stage is complete the session is idle
        rather than moving on to other stages unasked.
        """
        try:
            return await self._assist(stage, guidance, actor)
        except ProviderInterrupted as interruption:
            return self._pause_for_provider(interruption)

    def reject(self, actor: Actor, reason: str = "") -> SessionState:
        """Withdraw the pending proposal without applying or revising it."""
        if actor.kind is not ActorKind.HUMAN:
            raise SessionError("rejecting a proposal needs a person's name (--user)")
        self._require_idle()
        pending = self.state.pending
        if pending is None:
            raise SessionError("nothing is waiting for approval")
        self.state.approvals.append(
            ApprovalRecord(
                proposal_id=pending.id,
                stage=pending.stage,
                decision="rejected",
                actor=actor.label,
                actor_kind=actor.kind.value,
                at=now(),
                operations_sha256=_digest(pending.operations),
                drafts_fingerprint=pending.drafts_fingerprint,
                note=reason,
            )
        )
        self._withdraw_pending(
            f"rejected by {actor.label}" + (f": {reason}" if reason else "")
        )
        self.state.stages[pending.stage].status = StageStatus.PENDING
        self.state.focus = None
        self.state.status = SessionStatus.ACTIVE
        self._save()
        return self.state

    async def approve(self, actor: Actor) -> SessionState:
        """Apply the pending proposal exactly as shown, then validate it."""
        try:
            return await self._approve(actor)
        except ProviderInterrupted as interruption:
            return self._pause_for_provider(interruption)

    async def object(self, text: str, actor: Actor) -> SessionState:
        """Investigate the user's objection; never treat it as approval."""
        try:
            return await self._object(text, actor)
        except ProviderInterrupted as interruption:
            return self._pause_for_provider(interruption)

    async def reply(self, text: str, actor: Actor) -> SessionState:
        """Answer the agent's question and let it plan the stage again."""
        try:
            return await self._reply(text, actor)
        except ProviderInterrupted as interruption:
            return self._pause_for_provider(interruption)

    async def ask(self, text: str, actor: Actor) -> str:
        """Answer a question within the session without changing anything."""
        try:
            return await self._ask(text, actor)
        except ProviderInterrupted as interruption:
            self._pause_for_provider(interruption)
            return f"The provider could not answer: {interruption.error}"

    # -------------------------------------------------------- control

    def _require_idle(self) -> None:
        if self.state.transaction is not None:
            raise SessionError(
                "an action is being applied; wait for it to finish before changing "
                "the session"
            )

    def pause(self, actor: Actor) -> SessionState:
        self._require_idle()
        self.state.status = SessionStatus.PAUSED
        self.state.say("user", "pause", f"{actor.label} paused the session.")
        self._save()
        return self.state

    def open_interventions(self) -> list[Blocker]:
        """Unresolved blockers: the decisions waiting for a person."""
        return [item for item in self.state.blockers if not item.resolved]

    def resume(self, actor: Actor, note: str = "") -> SessionState:
        """Continue the same session after a person resolved its blockers.

        The drafts are re-read: completed stages whose validation no longer
        passes reopen, a proposal made before the files changed is withdrawn,
        and every blocked stage is planned again from the current drafts. The
        caller then advances the session. A cancelled session never resumes.
        """
        if actor.kind is not ActorKind.HUMAN:
            raise SessionError("resuming a session needs a person's name (--user)")
        self._require_idle()
        state = self.state
        if state.status is SessionStatus.CANCELLED:
            raise SessionError("a cancelled session cannot be resumed")
        self._prepare()
        reopened = []
        for stage in ORDER:
            record = state.stages[stage]
            if record.status is StageStatus.BLOCKED:
                record.status = StageStatus.PENDING
                record.attempts = 0
                record.notes.append(f"reopened by {actor.label} on resume")
                reopened.append(stage)
        for blocker in state.blockers:
            if not blocker.resolved and blocker.stage in reopened:
                blocker.resolved = True
                blocker.resolution = note or (
                    f"{actor.label} resumed the session after reviewing the drafts"
                )
        for later in FINISHING:
            if state.stages[later].status in {
                StageStatus.COMPLETED,
                StageStatus.SKIPPED,
                StageStatus.BLOCKED,
            }:
                state.stages[later].status = StageStatus.PENDING
        state.report = None
        state.interruption = None
        state.status = SessionStatus.ACTIVE
        state.say(
            "user",
            "resume",
            f"{actor.label} resumed the session"
            + (f": {note}" if note else "")
            + (
                "; reopened " + ", ".join(stage.value for stage in reopened)
                if reopened
                else ""
            )
            + ".",
        )
        self._save()
        return state

    def cancel(self, actor: Actor) -> SessionState:
        self._require_idle()
        self._withdraw_pending("the session was cancelled")
        self.state.status = SessionStatus.CANCELLED
        self.state.say("user", "cancel", f"{actor.label} cancelled the session.")
        self.state.report = build_report(
            self.root,
            self.store,
            self.state,
            self.state.assessment,
        )
        self._save()
        return self.state

    def switch_mode(
        self,
        mode: InteractionMode,
        actor: Actor,
        *,
        policy: ExecutionPolicy | None = None,
    ) -> SessionState:
        """Change who drives the work; the draft files and history are kept."""
        self._require_idle()
        self._prepare()
        state = self.state
        if state.status is SessionStatus.CANCELLED:
            raise SessionError("a cancelled session cannot be resumed")
        if mode is not InteractionMode.MANUAL and actor.kind is not ActorKind.HUMAN:
            raise SessionError("switching to an AI mode needs a person's name (--user)")
        previous = state.mode
        if policy is not None:
            policy.approved_by = actor.label
            policy.approved_at = now()
            state.policy = policy
        elif mode is InteractionMode.AUTONOMOUS:
            state.policy.approved_by = actor.label
            state.policy.approved_at = now()
        if mode is InteractionMode.MANUAL:
            self._withdraw_pending("you switched to manual mode")
            state.status = SessionStatus.PAUSED
        else:
            if (
                previous is not InteractionMode.ASSISTED
                and mode is InteractionMode.ASSISTED
            ):
                for stage in ORDER:
                    record = state.stages[stage]
                    if record.status is StageStatus.BLOCKED:
                        record.status = StageStatus.PENDING
                        record.attempts = 0
            if mode is InteractionMode.AUTONOMOUS:
                self._withdraw_pending("autonomous mode decides without proposals")
                for stage in ORDER:
                    record = state.stages[stage]
                    if record.status in {
                        StageStatus.BLOCKED,
                        StageStatus.NEEDS_APPROVAL,
                        StageStatus.VALIDATION_FAILED,
                        StageStatus.REPAIRING,
                    }:
                        record.status = StageStatus.PENDING
                        record.attempts = 0
            for later in FINISHING:
                if state.stages[later].status in {
                    StageStatus.COMPLETED,
                    StageStatus.SKIPPED,
                    StageStatus.BLOCKED,
                }:
                    state.stages[later].status = StageStatus.PENDING
            state.status = SessionStatus.ACTIVE
        state.mode = mode
        state.mode_history.append(
            {
                "from": previous.value,
                "to": mode.value,
                "at": now(),
                "actor": actor.label,
            }
        )
        state.say(
            "user",
            "mode",
            f"{actor.label} switched the session from {previous.value} to "
            f"{mode.value}.",
        )
        self._save()
        return state

    def rollback(self, checkpoint_id: str, actor: Actor) -> SessionState:
        """Restore ``splice/`` to a checkpoint (a person's explicit decision)."""
        if actor.kind is not ActorKind.HUMAN:
            raise SessionError("rolling back needs a person's name (--user)")
        self._require_idle()
        with self.store.mutation_lock(self.state.id):
            self.store.restore(self.state, checkpoint_id)
        self._withdraw_pending(f"rolled back to {checkpoint_id}")
        self._recheck_completed()
        self.state.say("user", "rollback", f"{actor.label} restored {checkpoint_id}.")
        self._save()
        return self.state

    def report(self) -> dict[str, Any]:
        """The latest report, computing a provisional one when needed."""
        if self.state.report and "completion" in self.state.report:
            return self.state.report
        return build_report(self.root, self.store, self.state, self.state.assessment)
