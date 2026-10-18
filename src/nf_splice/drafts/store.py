"""Safe, hash-checked reads and writes below ``splice/`` and ``.splice-local/``.

Writes are atomic per file, refuse symlinks and path escapes, never create a
file that already exists unless replacing it is explicitly requested, and use
a compare-and-swap on the file's SHA-256 so a concurrent external edit is
never overwritten silently.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from nf_splice.drafts.patch import JsonValue, PatchConflict, PatchConflictError, PatchOp
from nf_splice.drafts.yamlio import (
    DraftSyntaxError,
    YamlDraft,
    apply_ops_to_node,
    dump_yaml_node,
    load_yaml_draft,
)
from nf_splice.layout import DRAFTS_DIR as DRAFTS_DIR
from nf_splice.layout import PRIVATE_DIR, PUBLISHED_DIR, prepare_private_workspace
from nf_splice.layout import REVIEWS_DIR as REVIEWS_DIR

SPLICE_DIR = PUBLISHED_DIR
DRAFT_MARKER = "x-splice-draft"


class DraftStoreError(ValueError):
    """Raised when a draft path or write is unsafe."""


class DraftConflictError(DraftStoreError):
    """Raised when a file changed after it was read for an edit."""

    def __init__(
        self, relative: str, message: str, conflicts: Sequence[PatchConflict] = ()
    ) -> None:
        super().__init__(f"{relative}: {message}")
        self.relative = relative
        self.conflicts = tuple(conflicts)


@dataclass(frozen=True, slots=True)
class FileState:
    """Current bytes of one repository file, read without following links."""

    relative: str
    exists: bool
    payload: bytes | None
    sha256: str | None

    @property
    def text(self) -> str | None:
        return None if self.payload is None else self.payload.decode("utf-8")


@dataclass(frozen=True, slots=True)
class YamlFileState:
    """A YAML draft's bytes plus its parse result or preserved parse error."""

    file: FileState
    draft: YamlDraft | None
    error: DraftSyntaxError | None


@dataclass(frozen=True, slots=True)
class PatchOutcome:
    """Planned or applied result of a targeted draft edit."""

    relative: str
    before_sha256: str | None
    after_sha256: str
    before: str
    after: str
    diff: str
    data: JsonValue
    wrote: bool


def sha256(payload: bytes) -> str:
    """Return the lowercase hexadecimal SHA-256 of bytes."""
    return hashlib.sha256(payload).hexdigest()


def text_diff(relative: str, before: str, after: str) -> str:
    """Return a unified diff between two texts of one repository path."""
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=relative if before else "/dev/null",
            tofile=relative,
        )
    )


def safe_path(root: Path, relative: str) -> Path:
    """Resolve a path below ``splice/`` or ``.splice-local/`` without links."""
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts or not pure.parts:
        raise DraftStoreError(f"unsafe path {relative!r}")
    if pure.parts[0] not in {SPLICE_DIR, PRIVATE_DIR}:
        raise DraftStoreError(
            f"draft store path must be below splice/ or .splice-local/: {relative}"
        )
    current = root
    for part in pure.parts:
        current = current / part
        if current.is_symlink():
            raise DraftStoreError(
                f"refusing symbolic link at {current.relative_to(root)}"
            )
    return current


def read_file(root: Path, relative: str) -> FileState:
    """Read one file's bytes and hash, or report it absent."""
    path = safe_path(root, relative)
    if not path.exists():
        return FileState(relative, False, None, None)
    if not path.is_file():
        raise DraftStoreError(f"{relative} is not a regular file")
    payload = path.read_bytes()
    return FileState(relative, True, payload, sha256(payload))


def read_yaml(root: Path, relative: str) -> YamlFileState:
    """Read and parse one YAML draft, preserving a malformed file as-is."""
    state = read_file(root, relative)
    if state.payload is None:
        return YamlFileState(state, None, None)
    try:
        return YamlFileState(
            state, load_yaml_draft(state.payload.decode("utf-8")), None
        )
    except UnicodeDecodeError as error:
        return YamlFileState(state, None, DraftSyntaxError(f"not UTF-8: {error}"))
    except DraftSyntaxError as error:
        return YamlFileState(state, None, error)


def _ensure_directory(root: Path, relative_directory: str) -> None:
    if PurePosixPath(relative_directory).parts[:1] == (PRIVATE_DIR,):
        try:
            prepare_private_workspace(root)
        except ValueError as error:
            raise DraftStoreError(str(error)) from error
    current = root
    for part in PurePosixPath(relative_directory).parts:
        current = current / part
        if current.is_symlink():
            raise DraftStoreError(
                f"refusing symbolic link at {current.relative_to(root)}"
            )
        if current.exists() and not current.is_dir():
            raise DraftStoreError(f"{current.relative_to(root)} is not a directory")
        current.mkdir(exist_ok=True)


def _write_temporary(path: Path, payload: bytes) -> Path:
    temporary = path.with_name(f".{path.name}.nf-splice.tmp")
    temporary.unlink(missing_ok=True)
    with temporary.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    return temporary


def create_file(root: Path, relative: str, payload: bytes) -> bool:
    """Create a file only when absent; return whether it was created."""
    path = safe_path(root, relative)
    if path.exists():
        return False
    _ensure_directory(root, PurePosixPath(relative).parent.as_posix())
    temporary = _write_temporary(path, payload)
    try:
        try:
            os.link(temporary, path)
        except FileExistsError:
            return False
        except OSError:
            if path.exists():
                return False
            os.replace(temporary, path)
        return True
    finally:
        temporary.unlink(missing_ok=True)


def replace_file(
    root: Path, relative: str, payload: bytes, *, expected_sha256: str | None
) -> str:
    """Atomically replace a file whose current hash must equal ``expected``.

    ``expected_sha256=None`` means the file must not exist yet.
    """
    path = safe_path(root, relative)
    current = read_file(root, relative)
    if current.sha256 != expected_sha256:
        raise DraftConflictError(
            relative, "file changed on disk since it was read; re-read and retry"
        )
    _ensure_directory(root, PurePosixPath(relative).parent.as_posix())
    temporary = _write_temporary(path, payload)
    try:
        if read_file(root, relative).sha256 != expected_sha256:
            raise DraftConflictError(relative, "file changed on disk during the write")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return sha256(payload)


def patch_yaml(
    root: Path,
    relative: str,
    operations: Sequence[PatchOp],
    *,
    write: bool,
) -> PatchOutcome:
    """Plan or apply a three-way-merged targeted edit to an existing YAML draft."""
    state = read_yaml(root, relative)
    if not state.file.exists or state.file.text is None:
        raise DraftStoreError(f"{relative} does not exist")
    if state.error is not None or state.draft is None:
        raise DraftStoreError(
            f"{relative} cannot be edited until its syntax is fixed: {state.error}"
        )
    before = state.file.text
    try:
        node, data = apply_ops_to_node(state.draft.node, operations)
    except PatchConflictError as error:
        raise DraftConflictError(
            relative,
            f"edit overlaps a change made after it was planned: {error}",
            error.conflicts,
        ) from error
    after = dump_yaml_node(node)
    payload = after.encode("utf-8")
    wrote = False
    if write and after != before:
        replace_file(root, relative, payload, expected_sha256=state.file.sha256)
        wrote = True
    return PatchOutcome(
        relative=relative,
        before_sha256=state.file.sha256,
        after_sha256=sha256(payload),
        before=before,
        after=after,
        diff=text_diff(relative, before, after),
        data=data,
        wrote=wrote,
    )


def canonical_json(value: Any) -> bytes:
    """Deterministic, human-readable JSON bytes used for every emitted file."""
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def sidecar_path(layer: str) -> str:
    """Return the review-sidecar path for one layer."""
    return f"{REVIEWS_DIR}/{layer}.review.json"


def read_sidecar(root: Path, layer: str) -> tuple[dict[str, Any], str | None]:
    """Return a layer's review sidecar (empty when absent) and its hash."""
    state = read_file(root, sidecar_path(layer))
    if state.payload is None:
        return {}, None
    try:
        loaded: object = json.loads(state.payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DraftStoreError(f"{state.relative} is not valid JSON: {error}") from error
    if not isinstance(loaded, dict):
        raise DraftStoreError(f"{state.relative} must contain a JSON object")
    return loaded, state.sha256


def write_sidecar(
    root: Path, layer: str, document: dict[str, Any], *, expected_sha256: str | None
) -> str:
    """Replace a layer's review sidecar with compare-and-swap protection."""
    return replace_file(
        root,
        sidecar_path(layer),
        canonical_json(document),
        expected_sha256=expected_sha256,
    )
