"""Plan and atomically materialise the reviewed output-contract layer."""

from __future__ import annotations

import difflib
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from nf_splice.domain import PathClassification
from nf_splice.inspectors import inspect_splice_tree
from nf_splice.renderers import RenderedOutputContracts, render_output_contracts
from nf_splice.services.authoring import load_repository_document


class OutputContractBuildError(ValueError):
    """Raised when output contracts cannot be written without unsafe replacement."""


class ChangeKind(str, Enum):
    """File-level effect of rendering one output-contract artefact."""

    CREATE = "create"
    UPDATE = "update"
    UNCHANGED = "unchanged"


@dataclass(frozen=True, slots=True)
class OutputContractChange:
    """One visible file-level output-contract change."""

    path: Path
    kind: ChangeKind
    diff: str


@dataclass(frozen=True, slots=True)
class OutputContractBuildResult:
    """Planned changes and whether they were materialised."""

    changes: tuple[OutputContractChange, ...]
    wrote: bool


def _diff(path: Path, current: str, proposed: str) -> str:
    relative = f"splice/{path.name}"
    before = relative if current else "/dev/null"
    return "".join(
        difflib.unified_diff(
            current.splitlines(keepends=True),
            proposed.splitlines(keepends=True),
            fromfile=before,
            tofile=relative,
        )
    )


def _rendered_files(
    root: Path, rendered: RenderedOutputContracts
) -> tuple[tuple[Path, str], ...]:
    splice = root / "splice"
    return (
        (splice / "outputs.yaml", rendered.catalogue),
        (splice / "outputs.schema.json", rendered.schema),
    )


def plan_output_contracts(
    repository_root: str | Path,
) -> OutputContractBuildResult:
    """Return deterministic file diffs without changing the repository."""
    root = Path(repository_root).resolve()
    splice = root / "splice"
    if splice.exists() and (splice.is_symlink() or not splice.is_dir()):
        raise OutputContractBuildError(
            "repository-root splice path must be a regular directory"
        )
    rendered = render_output_contracts(load_repository_document(root))
    changes = []
    for path, proposed in _rendered_files(root, rendered):
        if path.exists() and (path.is_symlink() or not path.is_file()):
            raise OutputContractBuildError(
                f"generated output-contract path is not a regular file: {path}"
            )
        current = path.read_text(encoding="utf-8") if path.is_file() else ""
        if current == proposed:
            kind = ChangeKind.UNCHANGED
            difference = ""
        else:
            kind = ChangeKind.UPDATE if path.exists() else ChangeKind.CREATE
            difference = _diff(path, current, proposed)
        changes.append(OutputContractChange(path=path, kind=kind, diff=difference))
    return OutputContractBuildResult(changes=tuple(changes), wrote=False)


def _unsafe_existing_targets(root: Path) -> dict[str, PathClassification]:
    inspection = inspect_splice_tree(root)
    return {
        item.path: item.classification
        for item in inspection.paths
        if item.path in {"outputs.yaml", "outputs.schema.json"}
    }


def _write_atomic(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.nf-splice.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def build_output_contracts(
    repository_root: str | Path,
    *,
    replace_existing: bool = False,
) -> OutputContractBuildResult:
    """Write reviewed output contracts with exact-path collision protection."""
    root = Path(repository_root).resolve()
    plan = plan_output_contracts(root)
    changed = tuple(
        item for item in plan.changes if item.kind is not ChangeKind.UNCHANGED
    )
    classifications = _unsafe_existing_targets(root)
    for item in changed:
        relative = item.path.name
        classification = classifications.get(relative)
        if classification is PathClassification.MALFORMED:
            raise OutputContractBuildError(
                f"refusing to replace malformed recognized artefact: {item.path}"
            )
        if classification is PathClassification.UNKNOWN:
            raise OutputContractBuildError(
                f"refusing to replace unknown content: {item.path}"
            )
        if classification is PathClassification.RECOGNIZED and not replace_existing:
            raise OutputContractBuildError(
                "review the displayed output-contract diff, then pass "
                "--replace-existing to replace recognized differing files"
            )

    if not changed:
        return plan
    splice = root / "splice"
    splice.mkdir(exist_ok=True)
    rendered = render_output_contracts(load_repository_document(root))
    proposed = dict(_rendered_files(root, rendered))
    for item in changed:
        _write_atomic(item.path, proposed[item.path])
    return OutputContractBuildResult(changes=plan.changes, wrote=True)
