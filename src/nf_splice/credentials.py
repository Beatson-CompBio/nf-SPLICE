"""Per-user provider credentials and preferences, kept outside every project.

Credentials (API keys, OAuth tokens) are stored in the user's configuration
folder, never in a pipeline repository or ``.splice-local/``:
``$NF_SPLICE_CONFIG_DIR``, else ``$XDG_CONFIG_HOME/nf-splice``, else
``~/.config/nf-splice``. The folder is created owner-only (``0700``) and each
file is written atomically as owner-only (``0600``). Values are never printed
or logged; diagnostics show only whether a credential exists and a
non-secret account label.
"""

from __future__ import annotations

import json
import os
import secrets
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any


def config_directory(environment: Mapping[str, str] | None = None) -> Path:
    env = os.environ if environment is None else environment
    if env.get("NF_SPLICE_CONFIG_DIR"):
        return Path(env["NF_SPLICE_CONFIG_DIR"]).expanduser()
    base = env.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base).expanduser() / "nf-splice"


def _secure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path, 0o700)
    return path


def write_secret(relative: str, document: Mapping[str, Any]) -> Path:
    """Atomically write an owner-only JSON file below the config folder."""
    path = config_directory() / relative
    _secure_directory(path.parent)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(document), indent=2))
    os.replace(temporary, path)
    os.chmod(path, 0o600)
    return path


def read_secret(relative: str) -> dict[str, Any] | None:
    path = config_directory() / relative
    if not path.is_file():
        return None
    loaded = json.loads(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else None


def delete_secret(relative: str) -> bool:
    path = config_directory() / relative
    if path.is_file():
        path.unlink()
        return True
    return False


def list_secrets(relative_directory: str) -> list[str]:
    directory = config_directory() / relative_directory
    if not directory.is_dir():
        return []
    return sorted(item.name for item in directory.glob("*.json"))


@contextmanager
def exclusive(relative: str) -> Iterator[None]:
    """A simple cross-process lock (for example to serialise token refresh)."""
    path = config_directory() / f"{relative}.lock"
    _secure_directory(path.parent)
    try:
        import fcntl
    except ImportError:  # pragma: no cover - platforms without fcntl
        yield
        return
    with open(path, "w", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def preferences() -> dict[str, Any]:
    """Application-wide, non-secret preferences (selected provider and model)."""
    return read_secret("preferences.json") or {}


def save_preferences(document: Mapping[str, Any]) -> None:
    write_secret("preferences.json", document)


def api_key(provider: str, variable: str) -> tuple[str | None, str]:
    """An API key from the environment, else the store; and where it came from."""
    value = os.environ.get(variable)
    if value:
        return value, f"environment variable {variable}"
    stored = read_secret(f"keys/{provider}.json")
    if stored and stored.get("api_key"):
        return str(stored["api_key"]), "nf-splice credential store"
    return None, "none"


def store_api_key(provider: str, value: str, label: str | None = None) -> Path:
    return write_secret(
        f"keys/{provider}.json", {"api_key": value.strip(), "label": label or ""}
    )
