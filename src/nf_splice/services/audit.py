"""Actor resolution, public-safe review events and the private audit store.

Public artefacts (drafts, sidecars, final files, the lock) only ever receive
a :class:`ReviewEvent` with a public actor label. Contact details such as a
Git e-mail address are kept, if at all, in a user-local, permission-restricted
audit store outside the repository. The store is optional and failure-safe.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import subprocess
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nf_splice import __version__
from nf_splice.domain.audit import (
    UNATTRIBUTED,
    Actor,
    ActorKind,
    ApprovalStatus,
    ChangeOrigin,
    ReviewEvent,
)

Clock = Callable[[], datetime.datetime]
_SECRET_PATTERNS = (
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"(?i)\b(password|passwd|secret|token|api[_-]?key)\s*[=:]\s*\S+"),
)
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_SUPPRESSED: ContextVar[bool] = ContextVar("nf_splice_private_audit_suppressed")


@contextmanager
def suppress_private_audit() -> Iterator[None]:
    """Do not record private audit events (sandbox previews change nothing real)."""
    token = _SUPPRESSED.set(True)
    try:
        yield
    finally:
        _SUPPRESSED.reset(token)


@dataclass(frozen=True, slots=True)
class GitIdentity:
    """An unconfirmed suggestion read from local Git configuration."""

    name: str | None
    email: str | None


@dataclass(frozen=True, slots=True)
class AuditWriteResult:
    """Outcome of recording one event in the private store."""

    event: ReviewEvent
    stored: bool
    warning: str | None = None


def redact(text: str) -> str:
    """Remove secrets and e-mail addresses from free text."""
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[redacted-secret]", text)
    return _EMAIL.sub("[redacted-email]", text)


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def timestamp(clock: Clock = _utc_now) -> str:
    """Return the RFC 3339 UTC second-precision event timestamp."""
    return clock().astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def suggest_git_identity(repository_root: str | Path) -> GitIdentity | None:
    """Read ``user.name``/``user.email`` as a suggestion; never fails."""

    def value(key: str) -> str | None:
        try:
            result = subprocess.run(
                ("git", "-C", str(repository_root), "config", "--get", key),
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        found = result.stdout.strip()
        return found if result.returncode == 0 and found else None

    name, email = value("user.name"), value("user.email")
    if name is None and email is None:
        return None
    return GitIdentity(name=name, email=email)


def resolve_actor(
    explicit: str | None = None,
    *,
    environment: Mapping[str, str] | None = None,
) -> Actor:
    """Choose the public actor label without requiring Git configuration.

    Precedence: explicit ``--actor`` value, ``NF_SPLICE_ACTOR``, a CI
    identity (recorded as automation), otherwise ``unattributed``. Git
    identity is only ever a suggestion and is never used implicitly.
    """
    env = os.environ if environment is None else environment
    if explicit and explicit.strip():
        return Actor(label=explicit.strip(), kind=ActorKind.HUMAN)
    configured = env.get("NF_SPLICE_ACTOR", "").strip()
    if configured:
        return Actor(label=configured, kind=ActorKind.HUMAN)
    if env.get("GITHUB_ACTIONS") == "true" and env.get("GITHUB_ACTOR"):
        return Actor(label=f"ci:{env['GITHUB_ACTOR']}", kind=ActorKind.AUTOMATION)
    if env.get("CI", "").lower() in {"1", "true"}:
        return Actor(label="ci:automation", kind=ActorKind.AUTOMATION)
    return UNATTRIBUTED


def audit_directory(environment: Mapping[str, str] | None = None) -> Path:
    """Return the user-local private audit directory (outside the repository)."""
    env = os.environ if environment is None else environment
    if env.get("NF_SPLICE_AUDIT_DIR"):
        return Path(env["NF_SPLICE_AUDIT_DIR"]).expanduser()
    state = env.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(state).expanduser() / "nf-splice" / "audit"


def _store_path(repository_root: Path, directory: Path) -> Path:
    key = hashlib.sha256(str(repository_root.resolve()).encode("utf-8")).hexdigest()
    return directory / f"{key[:24]}.jsonl"


def make_event(
    *,
    layer: str,
    action: str,
    origin: ChangeOrigin,
    approval: ApprovalStatus,
    actor: Actor,
    approved_by: Actor | None = None,
    pointers: tuple[str, ...] = (),
    before_sha256: str | None = None,
    after_sha256: str | None = None,
    source_revision: str | None = None,
    clock: Clock = _utc_now,
) -> ReviewEvent:
    """Create a public-safe review event with a captured timestamp."""
    at = timestamp(clock)
    digest = hashlib.sha256(
        json.dumps(
            [
                layer,
                action,
                at,
                list(pointers),
                before_sha256,
                after_sha256,
                actor.label,
            ],
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:16]
    return ReviewEvent(
        id=f"event:{digest}",
        at=at,
        layer=layer,
        action=action,
        pointers=pointers,
        origin=origin,
        approval=approval,
        actor=actor,
        approved_by=approved_by,
        tool="nf-splice",
        tool_version=__version__,
        before_sha256=before_sha256,
        after_sha256=after_sha256,
        source_revision=source_revision,
    )


def record_private(
    repository_root: str | Path,
    event: ReviewEvent,
    *,
    contact: GitIdentity | None = None,
    environment: Mapping[str, str] | None = None,
) -> AuditWriteResult:
    """Append the event (plus optional private contact) to the local store.

    The store is created with owner-only permissions. Any failure leaves the
    authoring operation intact and is reported as a warning.
    """
    root = Path(repository_root).resolve()
    if _SUPPRESSED.get(False):
        return AuditWriteResult(event, False, "preview: private audit not recorded")
    directory = audit_directory(environment)
    try:
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(directory, 0o700)
        resolved = directory.resolve()
        workspace = (root / ".nf-splice-local").resolve()
        if resolved.is_relative_to(root) and not resolved.is_relative_to(workspace):
            raise OSError("private audit store must not live inside the repository")
        path = _store_path(root, directory)
        record: dict[str, Any] = {
            "repository": str(root),
            "event": event.model_dump(mode="json"),
        }
        if contact is not None:
            record["private_contact"] = {"name": contact.name, "email": contact.email}
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
        os.chmod(path, 0o600)
    except OSError as error:
        return AuditWriteResult(event, False, f"private audit not recorded: {error}")
    return AuditWriteResult(event, True)


def read_private(
    repository_root: str | Path,
    *,
    redacted: bool = True,
    environment: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Return the private audit records for a repository, redacted by default."""
    path = _store_path(Path(repository_root).resolve(), audit_directory(environment))
    if not path.is_file():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if redacted:
            record.pop("private_contact", None)
            record["repository"] = "[redacted-path]"
            record = json.loads(redact(json.dumps(record)))
        records.append(record)
    return records
