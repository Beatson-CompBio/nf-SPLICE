"""Wizard snapshot (derived from services) and non-authoritative sessions.

Sessions persist only navigation, visited/deferred steps, unsaved form text
and file hashes for external-change detection. They are never decisions:
deleting a session loses no reviewed state, because readiness is always
re-derived from the draft files.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from nf_splice import __version__
from nf_splice.layers.base import LAYERS
from nf_splice.services.lifecycle import plan_promotion, validate_bundle
from nf_splice.services.migration import LEGACY_STATE
from nf_splice.services.workspace import WorkspaceStatus, workspace_status


@dataclass(frozen=True, slots=True)
class WizardSnapshot:
    """Everything the wizard displays, computed by shared services."""

    repository: Path
    status: WorkspaceStatus | None
    legacy_state: bool = False
    publish_ready: bool = False
    bundle_valid: bool = False
    publish_blockers: tuple[str, ...] = ()
    draft_hashes: Mapping[str, str | None] = field(default_factory=dict)
    read_only: bool = False

    def layer_state(self, layer: str) -> str:
        if self.status is None:
            return "missing"
        for item in self.status.artifacts:
            if item.layer == layer:
                return item.state.value
        return "missing"

    @property
    def has_drafts(self) -> bool:
        return any(self.layer_state(item.name) != "missing" for item in LAYERS)

    @property
    def malformed_drafts(self) -> tuple[str, ...]:
        return tuple(
            item.name for item in LAYERS if self.layer_state(item.name) == "malformed"
        )


def build_snapshot(repository: str | Path) -> WizardSnapshot:
    """Compute a snapshot from current files (safe to call in a worker)."""
    root = Path(repository).resolve()
    status = workspace_status(root)
    try:
        plan = plan_promotion(root)
        ready = plan.ready
        blockers = tuple(
            f"{item.layer}{item.pointer}: {item.message}" for item in plan.blockers
        )
    except ValueError as error:
        ready, blockers = False, (str(error),)
    valid = (
        validate_bundle(root).valid
        if (root / "splice" / "bundle.json").is_file()
        else False
    )
    hashes = {item.draft: item.draft_sha256 for item in status.artifacts}
    return WizardSnapshot(
        repository=root,
        status=status,
        legacy_state=(root / LEGACY_STATE).is_file(),
        publish_ready=ready,
        bundle_valid=valid,
        publish_blockers=blockers,
        draft_hashes=hashes,
        read_only=not os.access(root, os.W_OK),
    )


class WizardSession(BaseModel):
    """Navigation-only wizard progress for one repository."""

    model_config = ConfigDict(extra="forbid")

    format: str = "1"
    tool_version: str = __version__
    repository_key: str
    current_step: str = "welcome"
    visited: list[str] = Field(default_factory=list)
    deferred: list[str] = Field(default_factory=list)
    unsaved: dict[str, dict[str, str]] = Field(default_factory=dict)
    file_hashes: dict[str, str | None] = Field(default_factory=dict)


def repository_key(repository: str | Path) -> str:
    """Stable hash of the resolved repository path."""
    return hashlib.sha256(str(Path(repository).resolve()).encode("utf-8")).hexdigest()[
        :24
    ]


def default_session_directory(environment: Mapping[str, str] | None = None) -> Path:
    """``NF_SPLICE_SESSION_DIR`` or the user cache; never the published bundle."""
    env = os.environ if environment is None else environment
    if env.get("NF_SPLICE_SESSION_DIR"):
        return Path(env["NF_SPLICE_SESSION_DIR"]).expanduser()
    cache = env.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(cache).expanduser() / "nf-splice" / "sessions"


class SessionStore:
    """Optional on-disk session store; ``None`` directory disables it."""

    def __init__(self, directory: Path | None) -> None:
        self.directory = directory

    @property
    def enabled(self) -> bool:
        return self.directory is not None

    def _path(self, repository: Path) -> Path | None:
        if self.directory is None:
            return None
        return self.directory / f"{repository_key(repository)}.json"

    def load(self, repository: Path) -> WizardSession | None:
        path = self._path(repository)
        if path is None or not path.is_file():
            return None
        try:
            return WizardSession.model_validate(json.loads(path.read_text("utf-8")))
        except (OSError, ValueError, ValidationError):
            return None

    def save(self, repository: Path, session: WizardSession) -> None:
        path = self._path(repository)
        if path is None:
            return
        repository_root = repository.resolve()
        resolved = path.parent.resolve() if path.parent.exists() else path.parent
        if (repository_root / "splice") in [resolved, *resolved.parents]:
            raise ValueError("sessions must never be stored inside splice/")
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(session.model_dump_json(indent=2), encoding="utf-8")
        os.replace(temporary, path)

    def delete(self, repository: Path) -> None:
        path = self._path(repository)
        if path is not None:
            path.unlink(missing_ok=True)


def changed_files(session: WizardSession, snapshot: WizardSnapshot) -> tuple[str, ...]:
    """Drafts whose bytes changed since the session last saw them."""
    return tuple(
        sorted(
            path
            for path, digest in snapshot.draft_hashes.items()
            if path in session.file_hashes and session.file_hashes[path] != digest
        )
    )
