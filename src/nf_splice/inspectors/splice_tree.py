"""Read-only inspection of an existing repository-root ``splice/`` tree."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from nf_splice.domain.inspection import (
    EntryType,
    InspectedPath,
    PathClassification,
    SpliceTreeInspection,
    TreeState,
    UnsafeCollision,
)

LayerNames = tuple[str, ...]
Validator = Callable[[Path], str | None]


def _require_mapping_keys(path: Path, keys: tuple[str, ...]) -> str | None:
    try:
        content: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return f"invalid JSON: {error}"
    if not isinstance(content, dict):
        return "expected a JSON object"
    missing = [key for key in keys if key not in content]
    if missing:
        return f"missing required keys: {', '.join(missing)}"
    return None


def _require_bundle(path: Path) -> str | None:
    error = _require_mapping_keys(
        path, ("bundle_format", "schema_version", "pipeline", "files")
    )
    if error is not None:
        return error
    try:
        content: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as parse_error:
        return f"invalid JSON: {parse_error}"
    if content.get("bundle_format") != "splice-pipeline-bundle":
        return "bundle_format must be 'splice-pipeline-bundle'"
    return None


def _require_outputs_yaml(path: Path) -> str | None:
    try:
        content: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        return f"invalid YAML: {error}"
    if not isinstance(content, dict):
        return "expected a YAML mapping"
    missing = [
        key for key in ("schema_version", "pipeline", "outputs") if key not in content
    ]
    if missing:
        return f"missing required keys: {', '.join(missing)}"
    if not isinstance(content["outputs"], list):
        return "outputs must be a list"
    return None


def _require_nonempty_text(path: Path) -> str | None:
    try:
        if path.read_text(encoding="utf-8").strip():
            return None
    except (OSError, UnicodeError) as error:
        return f"cannot read text: {error}"
    return "file is empty"


_FIXED_ARTIFACTS: dict[str, tuple[LayerNames, Validator]] = {
    "bundle.json": (("bundle",), _require_bundle),
    "components.json": (
        ("components",),
        lambda path: _require_mapping_keys(
            path, ("schema_version", "pipeline", "containers", "components")
        ),
    ),
    "execution-profiles.json": (
        ("execution_profiles",),
        lambda path: _require_mapping_keys(path, ("schema_version", "profiles")),
    ),
    "inputs.schema.json": (
        ("inputs",),
        lambda path: _require_mapping_keys(path, ("$schema", "type")),
    ),
    "outputs.schema.json": (
        ("outputs",),
        lambda path: _require_mapping_keys(path, ("$schema", "type", "properties")),
    ),
    "outputs.yaml": (("outputs",), _require_outputs_yaml),
    "README.md": (("documentation",), _require_nonempty_text),
    "ro-crate-metadata.json": (
        ("provenance",),
        lambda path: _require_mapping_keys(path, ("@context", "@graph")),
    ),
}


def _entry_type(path: Path) -> EntryType:
    if path.is_symlink():
        return EntryType.SYMLINK
    if path.is_dir():
        return EntryType.DIRECTORY
    return EntryType.FILE


def _walk_without_following_links(root: Path) -> list[Path]:
    entries: list[Path] = []
    for current, directory_names, file_names in os.walk(root, followlinks=False):
        current_path = Path(current)
        directory_names.sort()
        file_names.sort()
        for name in directory_names:
            entries.append(current_path / name)
        for name in file_names:
            entries.append(current_path / name)
    return sorted(entries, key=lambda path: path.relative_to(root).as_posix())


def _classify(path: Path, relative: str) -> InspectedPath:
    entry_type = _entry_type(path)

    if relative == "configs" and entry_type is EntryType.DIRECTORY:
        return InspectedPath(
            path=relative,
            entry_type=entry_type,
            classification=PathClassification.RECOGNIZED,
            affected_layers=("execution_profiles",),
        )

    if relative.startswith("configs/"):
        layers: LayerNames = ("execution_profiles",)
        if entry_type is EntryType.FILE and relative.endswith(".config"):
            error = _require_nonempty_text(path)
            classification = (
                PathClassification.MALFORMED
                if error is not None
                else PathClassification.RECOGNIZED
            )
            return InspectedPath(
                path=relative,
                entry_type=entry_type,
                classification=classification,
                affected_layers=layers,
                detail=error,
            )
        return InspectedPath(
            path=relative,
            entry_type=entry_type,
            classification=PathClassification.UNKNOWN,
            affected_layers=layers,
            detail="unknown content inside the execution-profile config boundary",
        )

    spec = _FIXED_ARTIFACTS.get(relative)
    if spec is None:
        return InspectedPath(
            path=relative,
            entry_type=entry_type,
            classification=PathClassification.UNKNOWN,
            detail="path is not part of the recognized integration bundle",
        )

    layers, validator = spec
    if entry_type is not EntryType.FILE:
        return InspectedPath(
            path=relative,
            entry_type=entry_type,
            classification=PathClassification.MALFORMED,
            affected_layers=layers,
            detail="recognized artifact path must be a regular file",
        )

    error = validator(path)
    return InspectedPath(
        path=relative,
        entry_type=entry_type,
        classification=(
            PathClassification.MALFORMED
            if error is not None
            else PathClassification.RECOGNIZED
        ),
        affected_layers=layers,
        detail=error,
    )


def _tree_state(paths: list[InspectedPath]) -> TreeState:
    classifications = {item.classification for item in paths}
    if classifications == {PathClassification.RECOGNIZED}:
        return TreeState.RECOGNIZED
    if classifications == {PathClassification.MALFORMED}:
        return TreeState.MALFORMED
    if classifications == {PathClassification.UNKNOWN}:
        return TreeState.UNKNOWN
    return TreeState.MIXED


def _collision(item: InspectedPath) -> UnsafeCollision | None:
    if not item.affected_layers or item.entry_type is EntryType.DIRECTORY:
        return None
    if item.classification is PathClassification.UNKNOWN:
        reason = "unknown content makes this generated directory boundary unsafe"
    elif item.classification is PathClassification.MALFORMED:
        reason = "malformed recognized artifact must be reconciled before replacement"
    else:
        reason = "existing recognized artifact requires review before replacement"
    return UnsafeCollision(
        path=f"splice/{item.path}",
        affected_layers=item.affected_layers,
        reason=reason,
    )


def inspect_splice_tree(repository_root: Path) -> SpliceTreeInspection:
    """Inventory and classify ``splice/`` without modifying any path."""
    splice_root = repository_root / "splice"
    if not splice_root.exists() and not splice_root.is_symlink():
        return SpliceTreeInspection(state=TreeState.ABSENT)
    if splice_root.is_symlink() or not splice_root.is_dir():
        path = InspectedPath(
            path=".",
            entry_type=_entry_type(splice_root),
            classification=PathClassification.MALFORMED,
            affected_layers=("bundle",),
            detail="repository-root splice path must be a directory",
        )
        return SpliceTreeInspection(
            state=TreeState.MALFORMED,
            paths=(path,),
            collisions=(
                UnsafeCollision(
                    path="splice",
                    affected_layers=("bundle",),
                    reason="integration root is not a regular directory",
                ),
            ),
        )

    entries = _walk_without_following_links(splice_root)
    if not entries:
        return SpliceTreeInspection(state=TreeState.EMPTY)

    inspected = [
        _classify(path, path.relative_to(splice_root).as_posix()) for path in entries
    ]
    collisions = tuple(
        collision for item in inspected if (collision := _collision(item)) is not None
    )
    return SpliceTreeInspection(
        state=_tree_state(inspected),
        paths=tuple(inspected),
        collisions=collisions,
    )
