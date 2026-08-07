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
from nf_splice.domain.serialization import (
    InvalidAuthoringDocument,
    UnsupportedSchemaVersion,
    load_authoring_document,
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


def _require_execution_profiles(path: Path) -> str | None:
    error = _require_mapping_keys(path, ("schema_version", "profiles"))
    if error is not None:
        return error
    try:
        content: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as parse_error:
        return f"invalid JSON: {parse_error}"
    profiles = content.get("profiles")
    if not isinstance(profiles, list) or not profiles:
        return "profiles must be a non-empty array"
    identifiers: list[str] = []
    for index, profile in enumerate(profiles):
        if not isinstance(profile, dict):
            return f"profiles[{index}] must be an object"
        missing = [
            key
            for key in (
                "id",
                "name",
                "description",
                "engine",
                "executor",
                "container_engine",
                "config",
            )
            if not isinstance(profile.get(key), str) or not profile[key]
        ]
        if missing:
            return f"profiles[{index}] has invalid fields: {', '.join(missing)}"
        identifiers.append(profile["id"])
        config = profile["config"]
        config_path = path.parent / config
        if (
            not config.startswith("configs/")
            or not config.endswith(".config")
            or ".." in Path(config).parts
            or config_path.is_symlink()
            or not config_path.is_file()
        ):
            return f"profiles[{index}] references invalid config {config!r}"
    if len(identifiers) != len(set(identifiers)):
        return "execution profile ids must be unique"
    return None


def validate_authoring_state(path: Path) -> tuple[str, str | None]:
    """Return compatibility and detail for a canonical authoring document."""
    try:
        load_authoring_document(path.read_text(encoding="utf-8"))
    except UnsupportedSchemaVersion as error:
        return "incompatible", str(error)
    except (OSError, UnicodeError, InvalidAuthoringDocument) as error:
        return "malformed", str(error)
    return "recognized", None


def validate_lock_state(path: Path) -> tuple[str, str | None]:
    """Validate the reserved JSON provenance envelope without inventing its body."""
    try:
        content: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return "malformed", f"invalid JSON: {error}"
    if not isinstance(content, dict):
        return "malformed", "lock state must be a JSON object"
    version = content.get("schema_version")
    if version != "1.0":
        return "incompatible", (
            f"unsupported lock schema version {version!r}; expected '1.0'"
        )
    return "recognized", None


def _require_authoring_state(path: Path) -> str | None:
    _classification, detail = validate_authoring_state(path)
    return detail


def _require_lock_state(path: Path) -> str | None:
    _classification, detail = validate_lock_state(path)
    return detail


_FIXED_ARTIFACTS: dict[str, tuple[LayerNames, Validator]] = {
    "nf-splice.yaml": (("authoring",), _require_authoring_state),
    "nf-splice.lock.json": (("bundle",), _require_lock_state),
    "bundle.json": (("bundle",), _require_bundle),
    "components.json": (
        ("components",),
        lambda path: _require_mapping_keys(
            path, ("schema_version", "pipeline", "containers", "components")
        ),
    ),
    "execution-profiles.json": (
        ("execution_profiles",),
        _require_execution_profiles,
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
    if item.path in {"nf-splice.yaml", "nf-splice.lock.json"}:
        return None
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
