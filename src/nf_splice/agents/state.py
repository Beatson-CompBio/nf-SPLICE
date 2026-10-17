"""Durable session state, checkpoints and the repository mutation lock.

Drafts live in ``.splice-local/drafts/`` and published files in ``splice/``.
A session stores how the work is being driven (mode, stages, proposals,
approvals, conversation, evidence, budgets) in
``.splice-local/sessions/<id>/``: ``session.json``, the redacted
``events.jsonl`` and ``checkpoints/``. ``.splice-local/`` is ignored by the
working copy's ``.gitignore`` and is never published or archived.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import secrets
import shutil
import socket
from collections.abc import Iterator
from contextlib import contextmanager
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from nf_splice import __version__
from nf_splice.agents.permissions import ExecutionPolicy
from nf_splice.agents.stages import ORDER, Stage, StageStatus
from nf_splice.layout import (
    DRAFTS_DIR,
    PRIVATE_DIR,
    PUBLISHED_DIR,
    REVIEWS_DIR,
    SESSIONS_DIR,
    prepare_private_workspace,
)
from nf_splice.services.audit import redact

FORMAT = "1"
WORKSPACE = PRIVATE_DIR
#: What a checkpoint captures: published files, private drafts and reviews.
CHECKPOINT_AREAS = (PUBLISHED_DIR, DRAFTS_DIR, REVIEWS_DIR)
_SPLICE_TRANSIENT = {
    ".nf-splice-staging",
    ".nf-splice-backup",
    ".nf-splice-publish.json",
}
_SOURCE_SUFFIXES = {".nf", ".config"}
_SOURCE_NAMES = {
    "nextflow_schema.json",
    "modules.json",
    "meta.yml",
    "meta.yaml",
    "ro-crate-metadata.json",
    "CITATION.cff",
    ".nf-core.yml",
}
_SKIP_DIRECTORIES = {
    ".git",
    WORKSPACE,
    ".nf-splice-local",
    "work",
    ".nextflow",
    "node_modules",
    "__pycache__",
    ".venv",
}


class InteractionMode(str, Enum):
    """Who drives the work. Switching never changes the meaning of saved state."""

    MANUAL = "manual"
    ASSISTED = "assisted"
    AUTONOMOUS = "autonomous"


class SessionStatus(str, Enum):
    """Overall session state."""

    ACTIVE = "active"
    AWAITING_APPROVAL = "awaiting_approval"
    AWAITING_INPUT = "awaiting_input"
    RUNNING = "running"
    PAUSED = "paused"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class EvidenceStatus(str, Enum):
    """How an assertion is supported."""

    OBSERVED = "observed"
    STATICALLY_INFERRED = "statically_inferred"
    TOOL_VERIFIED = "tool_verified"
    HUMAN_CONFIRMED = "human_confirmed"
    UNRESOLVED = "unresolved"


def now() -> str:
    """UTC timestamp, second precision."""
    return (
        datetime.datetime.now(datetime.timezone.utc)
        .replace(microsecond=0)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    )


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReviewRecord(_Model):
    """An AI review of one layer, with the facts that show it happened.

    ``inspected`` is recorded by nf-splice from the tool calls the model
    actually made (files and line ranges read, searches, analyses), never
    from what the model says it looked at. ``kind`` is ``scientific`` for
    identity, inputs, outputs and provenance and ``operational`` for
    components and execution profiles.
    """

    kind: str
    outcome: str
    summary: str = ""
    checked: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    inspected: list[str] = Field(default_factory=list)
    draft_sha256: str | None = None
    sources_fingerprint: str = ""
    provider: str = ""
    model: str | None = None
    reasoning_effort: str | None = None
    at: str = ""


class StageRecord(_Model):
    status: StageStatus = StageStatus.PENDING
    attempts: int = 0
    issues: list[str] = Field(default_factory=list)
    summary: str = ""
    notes: list[str] = Field(default_factory=list)
    started_at: str | None = None
    completed_at: str | None = None
    #: Every source read and analysis the model made for this stage.
    investigation: list[str] = Field(default_factory=list)
    review: ReviewRecord | None = None


class PlannedOperation(_Model):
    tool: str
    arguments: dict[str, Any]
    description: str = ""


class Proposal(_Model):
    id: str
    stage: Stage
    revision: int = 1
    summary: str
    operations: list[PlannedOperation]
    evidence: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    validation_gate: str = ""
    diff: str = ""
    preview_issues: list[str] = Field(default_factory=list)
    drafts_fingerprint: str
    sources_fingerprint: str
    created_at: str
    status: str = "pending"


class ApprovalRecord(_Model):
    proposal_id: str
    stage: Stage
    decision: str
    actor: str
    actor_kind: str
    at: str
    operations_sha256: str
    drafts_fingerprint: str
    note: str = ""


class ConversationEntry(_Model):
    at: str
    role: str
    kind: str
    text: str
    stage: Stage | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class EvidenceItem(_Model):
    id: str
    claim: str
    status: EvidenceStatus
    sources: list[str] = Field(default_factory=list)
    stage: Stage | None = None
    at: str


class Blocker(_Model):
    stage: Stage
    decision: str
    artefact: str
    attempted_checks: list[str] = Field(default_factory=list)
    suggested_resolution: str = ""
    issues: list[str] = Field(default_factory=list)
    at: str
    resolved: bool = False


class Checkpoint(_Model):
    id: str
    stage: Stage | None
    at: str
    reason: str
    drafts_fingerprint: str


class Transaction(_Model):
    id: str
    stage: Stage
    checkpoint: str
    started_at: str
    operations: list[str]


class Usage(_Model):
    tool_calls: int = 0
    provider_turns: int = 0
    cost_usd: float = 0.0
    cost_reported: bool = False
    by_provider: dict[str, dict[str, Any]] = Field(default_factory=dict)


class ProviderRecord(_Model):
    name: str
    remote: bool
    conversation_ref: str | None = None
    script: str | None = None
    model: str | None = None
    account: str | None = None
    billing: str = "unknown"
    inference: str = "remote"
    reasoning_control: str = "none"
    #: The effort requested and, after a turn, what the provider applied.
    reasoning_requested: str | None = None
    reasoning_applied: str | None = None
    reasoning_notice: str | None = None


class SessionState(_Model):
    """Everything needed to resume a session, in any mode."""

    format: str = FORMAT
    tool_version: str = __version__
    id: str
    created_at: str
    updated_at: str
    repository_key: str
    mode: InteractionMode
    status: SessionStatus = SessionStatus.ACTIVE
    objective: str
    provider: ProviderRecord
    policy: ExecutionPolicy
    stages: dict[Stage, StageRecord] = Field(
        default_factory=lambda: {stage: StageRecord() for stage in ORDER}
    )
    current_stage: Stage | None = Stage.DISCOVER
    pending: Proposal | None = None
    proposals: list[Proposal] = Field(default_factory=list)
    approvals: list[ApprovalRecord] = Field(default_factory=list)
    conversation: list[ConversationEntry] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    blockers: list[Blocker] = Field(default_factory=list)
    checkpoints: list[Checkpoint] = Field(default_factory=list)
    transaction: Transaction | None = None
    usage: Usage = Field(default_factory=Usage)
    drafts_fingerprint: str = ""
    sources_fingerprint: str = ""
    report: dict[str, Any] | None = None
    assessment: dict[str, Any] | None = None
    export: dict[str, Any] | None = None
    commit: dict[str, Any] | None = None
    mode_history: list[dict[str, str]] = Field(default_factory=list)
    events_logged: int = 0
    interruption: dict[str, Any] | None = None
    provider_history: list[dict[str, Any]] = Field(default_factory=list)

    def say(
        self,
        role: str,
        kind: str,
        text: str,
        *,
        stage: Stage | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        self.conversation.append(
            ConversationEntry(
                at=now(),
                role=role,
                kind=kind,
                text=redact(text)[:20000],
                stage=stage,
                data=json.loads(redact(json.dumps(data or {}, default=str))),
            )
        )

    def add_evidence(
        self,
        claim: str,
        status: EvidenceStatus,
        sources: list[str] | None = None,
        stage: Stage | None = None,
    ) -> EvidenceItem:
        item = EvidenceItem(
            id=f"evidence-{len(self.evidence) + 1}",
            claim=redact(claim)[:2000],
            status=status,
            sources=[redact(item)[:500] for item in sources or []][:20],
            stage=stage,
            at=now(),
        )
        self.evidence.append(item)
        return item


# ------------------------------------------------------------ fingerprints


def _digest_files(paths: Iterator[tuple[str, Path]]) -> str:
    digest = hashlib.sha256()
    for relative, path in sorted(paths):
        try:
            content = path.read_bytes()
        except OSError:
            continue
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(hashlib.sha256(content).digest())
    return digest.hexdigest()


def drafts_fingerprint(root: Path, *, include_reviews: bool = True) -> str:
    """Hash of ``splice/`` and the private drafts and reviews.

    Without ``include_reviews`` the review sidecars are left out, so recording
    the same decision again does not count as a change.
    """
    areas = [PUBLISHED_DIR, DRAFTS_DIR] + ([REVIEWS_DIR] if include_reviews else [])

    def files() -> Iterator[tuple[str, Path]]:
        for area in areas:
            base = root / area
            if not base.is_dir():
                continue
            for current, directories, names in os.walk(base, followlinks=False):
                directories[:] = [
                    item for item in directories if item not in _SPLICE_TRANSIENT
                ]
                for name in names:
                    if name in _SPLICE_TRANSIENT or name.endswith(".nf-splice.tmp"):
                        continue
                    path = Path(current) / name
                    yield path.relative_to(root).as_posix(), path

    return _digest_files(files())


def sources_fingerprint(root: Path) -> str:
    """Hash of the pipeline sources nf-splice reads as evidence."""

    def files() -> Iterator[tuple[str, Path]]:
        for current, directories, names in os.walk(root, followlinks=False):
            directories[:] = [
                item
                for item in directories
                if item not in _SKIP_DIRECTORIES
                and not (item == "splice" and Path(current) == root)
            ]
            for name in names:
                path = Path(current) / name
                if path.suffix in _SOURCE_SUFFIXES or name in _SOURCE_NAMES:
                    yield path.relative_to(root).as_posix(), path

    return _digest_files(files())


# ------------------------------------------------------------ store


class SessionError(RuntimeError):
    """A session cannot be loaded, saved or changed as requested."""


def repository_key(root: Path) -> str:
    return hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:24]


def agent_directory(root: Path) -> Path:
    """``.splice-local/sessions``, prepared (ignored, untracked) before use."""
    try:
        prepare_private_workspace(root)
    except ValueError as error:
        raise SessionError(str(error)) from error
    directory = root / SESSIONS_DIR
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    return directory


def _write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
    temporary.write_text(content, encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


class SessionStore:
    """Atomic, versioned persistence of sessions for one repository."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.directory = agent_directory(self.root)

    def session_directory(self, session_id: str) -> Path:
        if not session_id.startswith("session-") or "/" in session_id:
            raise SessionError(f"invalid session id {session_id!r}")
        return self.directory / session_id

    def new_id(self) -> str:
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
        return f"session-{stamp}-{secrets.token_hex(3)}"

    def save(self, state: SessionState) -> None:
        state.updated_at = now()
        directory = self.session_directory(state.id)
        _write_atomic(directory / "session.json", state.model_dump_json(indent=2))

    def latest_review(self, stage: Stage, *, exclude: str = "") -> ReviewRecord | None:
        """The newest completed review of a stage in another saved session."""
        found: list[ReviewRecord] = []
        for item in self.sessions():
            if item.id == exclude:
                continue
            try:
                state = self.load(item.id)
            except SessionError:
                continue
            review = state.stages[stage].review
            if review is not None and review.outcome in {"changed", "no_change"}:
                found.append(review)
        return max(found, key=lambda item: item.at) if found else None

    def load(self, session_id: str | None = None) -> SessionState:
        if session_id is None:
            listed = self.sessions()
            if not listed:
                raise SessionError("no session exists for this repository")
            session_id = listed[0].id
        path = self.session_directory(session_id) / "session.json"
        if not path.is_file():
            raise SessionError(f"session {session_id} does not exist")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise SessionError(
                f"session {session_id} is unreadable: {error}"
            ) from error
        if data.get("format") != FORMAT:
            raise SessionError(
                f"session {session_id} has format {data.get('format')!r}; this "
                f"nf-splice reads format {FORMAT}"
            )
        try:
            state = SessionState.model_validate(data)
        except ValidationError as error:
            raise SessionError(f"session {session_id} is invalid: {error}") from error
        if state.repository_key != repository_key(self.root):
            raise SessionError(f"session {session_id} belongs to another repository")
        return state

    def sessions(self) -> list[SessionState]:
        found = []
        sessions = self.directory
        if not sessions.is_dir():
            return []
        for path in sessions.glob("session-*/session.json"):
            try:
                found.append(SessionState.model_validate_json(path.read_text("utf-8")))
            except (OSError, ValueError, ValidationError):
                continue
        return sorted(found, key=lambda item: (item.updated_at, item.id), reverse=True)

    def log_tool(self, session_id: str, record: dict[str, Any]) -> None:
        path = self.session_directory(session_id) / "events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
            handle.write(redact(json.dumps(record, default=str, sort_keys=True)) + "\n")

    def events(self, session_id: str) -> list[dict[str, Any]]:
        """Every logged event: tool calls and conversation, redacted."""
        path = self.session_directory(session_id) / "events.jsonl"
        if not path.is_file():
            return []
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def tool_log(self, session_id: str) -> list[dict[str, Any]]:
        """Only the tool-call events."""
        return [
            item
            for item in self.events(session_id)
            if item.get("event") != "conversation"
        ]

    # -------------------------------------------------------- checkpoints

    def checkpoint(
        self, state: SessionState, stage: Stage | None, reason: str
    ) -> Checkpoint:
        """Copy ``splice/`` and the private drafts and reviews for restoring."""
        identifier = f"checkpoint-{len(state.checkpoints) + 1}"
        target = self.session_directory(state.id) / "checkpoints" / identifier
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True, mode=0o700)
        for area in CHECKPOINT_AREAS:
            source = self.root / area
            if source.is_dir() and not source.is_symlink():
                shutil.copytree(
                    source,
                    target / area,
                    symlinks=True,
                    ignore=shutil.ignore_patterns(*_SPLICE_TRANSIENT),
                )
        record = Checkpoint(
            id=identifier,
            stage=stage,
            at=now(),
            reason=reason,
            drafts_fingerprint=drafts_fingerprint(self.root),
        )
        state.checkpoints.append(record)
        return record

    def restore(self, state: SessionState, checkpoint_id: str) -> None:
        """Make ``splice/`` and the private drafts exactly match a checkpoint."""
        if not any(item.id == checkpoint_id for item in state.checkpoints):
            raise SessionError(f"unknown checkpoint {checkpoint_id!r}")
        source = self.session_directory(state.id) / "checkpoints" / checkpoint_id
        for area in CHECKPOINT_AREAS:
            current = self.root / area
            if current.is_dir() and not current.is_symlink():
                for child in current.iterdir():
                    if child.name in _SPLICE_TRANSIENT:
                        continue
                    if child.is_dir() and not child.is_symlink():
                        shutil.rmtree(child)
                    else:
                        child.unlink()
            if (source / area).is_dir():
                shutil.copytree(
                    source / area, current, symlinks=True, dirs_exist_ok=True
                )

    # -------------------------------------------------------- lock

    @contextmanager
    def mutation_lock(self, session_id: str) -> Iterator[None]:
        """One session at a time may change this repository's drafts."""
        path = self.directory / "lock.json"
        record = {
            "session": session_id,
            "pid": os.getpid(),
            "host": socket.gethostname(),
            "at": now(),
        }
        for _attempt in range(2):
            try:
                descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                holder = _read_lock(path)
                if holder is not None and _alive(holder):
                    raise SessionError(
                        f"session {holder.get('session')} is changing this "
                        f"repository's drafts (pid {holder.get('pid')}); wait for it "
                        "to finish or pause it"
                    ) from None
                path.unlink(missing_ok=True)
                continue
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(record))
            break
        else:
            raise SessionError("could not acquire the repository lock")
        try:
            yield
        finally:
            path.unlink(missing_ok=True)


def _read_lock(path: Path) -> dict[str, Any] | None:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return loaded if isinstance(loaded, dict) else None


def _alive(holder: dict[str, Any]) -> bool:
    if holder.get("host") != socket.gethostname():
        return True
    try:
        os.kill(int(holder.get("pid", 0)), 0)
    except (OSError, ValueError):
        return False
    return True
