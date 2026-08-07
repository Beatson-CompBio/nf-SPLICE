"""Plan and materialise deterministic input and component artefacts."""

from __future__ import annotations

import difflib
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from nf_splice.domain import PathClassification
from nf_splice.inspectors import inspect_splice_tree
from nf_splice.renderers import render_component_inventory, render_input_projection
from nf_splice.services.authoring import load_repository_document


class StaticLayerBuildError(ValueError):
    """Raised when a reviewed static layer cannot be rendered safely."""


class StaticChangeKind(str, Enum):
    """File-level result of rendering one reviewed static layer."""

    CREATE = "create"
    UPDATE = "update"
    UNCHANGED = "unchanged"


@dataclass(frozen=True, slots=True)
class StaticLayerChange:
    """One deterministic generated-file change."""

    path: Path
    kind: StaticChangeKind
    diff: str


@dataclass(frozen=True, slots=True)
class StaticLayerBuildResult:
    """Preview or application result for one static integration layer."""

    change: StaticLayerChange
    wrote: bool


def _render(repository_root: Path, target: str) -> tuple[Path, str]:
    document = load_repository_document(repository_root)
    if target == "inputs":
        return (
            repository_root / "splice" / "inputs.schema.json",
            render_input_projection(document).schema,
        )
    if target == "components":
        return (
            repository_root / "splice" / "components.json",
            render_component_inventory(document).inventory,
        )
    raise StaticLayerBuildError(f"unsupported static layer {target!r}")


def _diff(path: Path, current: str, proposed: str) -> str:
    relative = f"splice/{path.name}"
    return "".join(
        difflib.unified_diff(
            current.splitlines(keepends=True),
            proposed.splitlines(keepends=True),
            fromfile=relative if current else "/dev/null",
            tofile=relative,
        )
    )


def plan_static_layer(
    repository_root: str | Path, target: str
) -> StaticLayerBuildResult:
    """Return a deterministic file diff without mutating the repository."""
    root = Path(repository_root).resolve()
    splice = root / "splice"
    if splice.exists() and (splice.is_symlink() or not splice.is_dir()):
        raise StaticLayerBuildError(
            f"repository-root splice path must be a regular directory: {splice}"
        )
    path, proposed = _render(root, target)
    if path.exists() and (path.is_symlink() or not path.is_file()):
        raise StaticLayerBuildError(
            f"generated {target} path is not a regular file: {path}"
        )
    current = path.read_text(encoding="utf-8") if path.is_file() else ""
    kind = (
        StaticChangeKind.UNCHANGED
        if current == proposed
        else StaticChangeKind.UPDATE
        if path.exists()
        else StaticChangeKind.CREATE
    )
    return StaticLayerBuildResult(
        change=StaticLayerChange(
            path=path,
            kind=kind,
            diff=(
                ""
                if kind is StaticChangeKind.UNCHANGED
                else _diff(path, current, proposed)
            ),
        ),
        wrote=False,
    )


def _write_atomic(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.nf-splice.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def build_static_layer(
    repository_root: str | Path,
    target: str,
    *,
    replace_existing: bool = False,
) -> StaticLayerBuildResult:
    """Write one reviewed layer with exact-path collision protection."""
    root = Path(repository_root).resolve()
    plan = plan_static_layer(root, target)
    if plan.change.kind is StaticChangeKind.UNCHANGED:
        return plan
    relative = plan.change.path.name
    inspected = inspect_splice_tree(root)
    classification = next(
        (item.classification for item in inspected.paths if item.path == relative),
        None,
    )
    if classification is PathClassification.MALFORMED:
        raise StaticLayerBuildError(
            f"refusing to replace malformed recognized artefact: {plan.change.path}"
        )
    if classification is PathClassification.UNKNOWN:
        raise StaticLayerBuildError(
            f"refusing to replace unknown content: {plan.change.path}"
        )
    if classification is PathClassification.RECOGNIZED and not replace_existing:
        raise StaticLayerBuildError(
            f"review the displayed {target} diff, then pass --replace-existing"
        )
    path, proposed = _render(root, target)
    _write_atomic(path, proposed)
    return StaticLayerBuildResult(change=plan.change, wrote=True)
