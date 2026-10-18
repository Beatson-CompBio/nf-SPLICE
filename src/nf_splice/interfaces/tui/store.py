"""Where the workspace was left: the page and the drafts' fingerprint.

This is navigation only, never a decision: deleting it loses nothing, because
every state is derived again from the drafts. It lets the workspace reopen on
the same page and say when drafts were edited outside it.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from nf_splice import __version__
from nf_splice.layout import PRIVATE_DIR, SESSIONS_DIR, prepare_private_workspace


class NavigationState(BaseModel):
    """The page a person was on and what the drafts looked like then."""

    model_config = ConfigDict(extra="ignore")

    format: str = "2"
    tool_version: str = __version__
    repository_key: str
    current_page: str = "welcome"
    model_key: str = ""


def repository_key(repository: str | Path) -> str:
    """Stable hash of the resolved repository path."""
    text = str(Path(repository).resolve())
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def default_session_directory(
    repository: str | Path | None = None,
    environment: Mapping[str, str] | None = None,
) -> Path:
    """``NF_SPLICE_SESSION_DIR``, else ``.splice-local/sessions/workspace/``."""
    env = os.environ if environment is None else environment
    if env.get("NF_SPLICE_SESSION_DIR"):
        return Path(env["NF_SPLICE_SESSION_DIR"]).expanduser()
    root = Path(repository or ".").resolve()
    return root / SESSIONS_DIR / "workspace"


class NavigationStore:
    """Optional on-disk navigation state; a ``None`` directory disables it."""

    def __init__(self, directory: Path | None) -> None:
        self.directory = directory

    def _path(self, repository: Path) -> Path | None:
        if self.directory is None:
            return None
        return self.directory / f"{repository_key(repository)}.json"

    def load(self, repository: Path) -> NavigationState | None:
        path = self._path(repository)
        if path is None or not path.is_file():
            return None
        try:
            return NavigationState.model_validate(json.loads(path.read_text("utf-8")))
        except (OSError, ValueError, ValidationError):
            return None

    def save(self, repository: Path, state: NavigationState) -> None:
        path = self._path(repository)
        if path is None:
            return
        root = repository.resolve()
        parent = path.parent.resolve() if path.parent.exists() else path.parent
        if (root / "splice") in [parent, *parent.parents]:
            raise ValueError("navigation state must never be stored inside splice/")
        if (root / PRIVATE_DIR) in [parent, *parent.parents]:
            prepare_private_workspace(root)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(state.model_dump_json(indent=2), encoding="utf-8")
        os.replace(temporary, path)
