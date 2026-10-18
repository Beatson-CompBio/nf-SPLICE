"""Immutable view models the workspace renders, built off the event loop.

:func:`build_model` reads the six drafts and the native configs, validates
each layer through the shared services, and returns a frozen
:class:`WorkspaceModel` of bounded, ready-to-display rows. It runs in a
worker; screens render from the model and never scan the repository, parse
large files or validate inside event handlers (ADR-0067).

:class:`ModelCache` keys layer validation on the bytes of every draft and
config, so selecting rows or switching pages costs nothing and an edit
re-validates once. The slower checks (lifecycle, route coverage, the
promotion plan) are separate views built on demand by their pages and
cached on the same key plus the published files.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nf_splice.interfaces.tui.navigation import (
    PAGES,
    StepState,
    Target,
    field_label,
    target_for,
)
from nf_splice.layers.base import LAYERS, load_review_state, read_layer, strip_marker
from nf_splice.layout import DRAFTS_DIR, PRIVATE_DIR, PUBLISHED_DIR

#: Longest message or value shown in place; longer text opens in a viewer.
MAX_TEXT = 240
#: Issues shown per screen before "View all".
MAX_ISSUES = 5


def bounded(text: Any, limit: int = MAX_TEXT) -> str:
    """One line of at most ``limit`` characters (an ellipsis marks a cut)."""
    value = " ".join(str(text).split())
    return value if len(value) <= limit else value[: limit - 1] + "…"


@dataclass(frozen=True, slots=True)
class Issue:
    """One validation finding, shaped for people and linked to its field."""

    layer: str
    pointer: str
    code: str
    message: str
    severity: str
    label: str
    entity: str
    target: Target

    @property
    def error(self) -> bool:
        return self.severity == "error"


@dataclass(frozen=True, slots=True)
class LayerView:
    """One draft as the workspace sees it."""

    name: str
    path: str
    exists: bool
    malformed: str | None
    sha256: str | None
    data: Mapping[str, Any]
    issues: tuple[Issue, ...]

    @property
    def errors(self) -> tuple[Issue, ...]:
        return tuple(item for item in self.issues if item.error)

    @property
    def warnings(self) -> tuple[Issue, ...]:
        return tuple(item for item in self.issues if not item.error)

    @property
    def ready(self) -> bool:
        return self.exists and self.malformed is None and not self.errors


@dataclass(frozen=True, slots=True)
class SourceFile:
    """A recognised structured source and whether it is present."""

    label: str
    path: str
    found: bool
    purpose: str


@dataclass(frozen=True, slots=True)
class ImportedValue:
    """An identity value imported from an exact key, with its provenance."""

    field: str
    value: str
    source: str
    location: str


@dataclass(frozen=True, slots=True)
class ParameterRow:
    name: str
    group: str
    group_title: str
    type: str
    required: bool
    default: str
    editable_by: tuple[str, ...]
    visibility: str
    description: str
    pointer: str


@dataclass(frozen=True, slots=True)
class SubmissionBlocker:
    """A required parameter with no default that nobody may supply."""

    name: str
    reason: str
    output_directory: bool


@dataclass(frozen=True, slots=True)
class OutputRow:
    index: int
    key: str
    title: str
    category: str
    formats: tuple[str, ...]
    scopes: tuple[str, ...]
    entity_types: tuple[str, ...]
    patterns: tuple[str, ...]
    complete: bool
    problems: tuple[str, ...]
    data: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class ComponentRow:
    index: int
    id: str
    tool: str
    version: str
    container: str
    sources: tuple[str, ...]
    unresolved: tuple[str, ...]
    type: str
    path: str


@dataclass(frozen=True, slots=True)
class ProfileRow:
    index: int
    id: str
    name: str
    description: str
    type: str
    executor: str
    container_engine: str
    config: str
    default: bool
    starter: bool
    problems: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WorkspaceModel:
    """Everything the authoring pages show; immutable once built."""

    repository: Path
    key: str
    layers: Mapping[str, LayerView]
    sources: tuple[SourceFile, ...]
    configs: Mapping[str, str]
    integration: Mapping[str, Any] | None
    imported: tuple[ImportedValue, ...]
    conflicts: Mapping[str, tuple[str, ...]]
    parameters: tuple[ParameterRow, ...]
    groups: tuple[tuple[str, str], ...]
    submission_blockers: tuple[SubmissionBlocker, ...]
    outputs: tuple[OutputRow, ...]
    components: tuple[ComponentRow, ...]
    containers: tuple[Mapping[str, Any], ...]
    profiles: tuple[ProfileRow, ...]
    published: bool
    read_only: bool
    error: str | None = None

    # ------------------------------------------------------------ queries

    @property
    def has_drafts(self) -> bool:
        return any(item.exists for item in self.layers.values())

    @property
    def all_drafts(self) -> bool:
        return all(item.exists for item in self.layers.values())

    @property
    def drafts_valid(self) -> bool:
        return all(item.ready for item in self.layers.values())

    def layer(self, name: str) -> LayerView:
        return self.layers[name]

    def pipeline(self) -> Mapping[str, Any]:
        value = self.layers["bundle"].data.get("pipeline")
        return value if isinstance(value, Mapping) else {}

    def identity_issues(self) -> tuple[Issue, ...]:
        return tuple(
            item
            for item in self.layers["bundle"].issues
            if item.target.page == "identity"
        )

    def assay_issues(self) -> tuple[Issue, ...]:
        return tuple(
            item
            for item in self.layers["bundle"].issues
            if item.target.page == "assays"
        )

    def page_issues(self, page_id: str) -> tuple[Issue, ...]:
        found: list[Issue] = []
        for layer in self.layers.values():
            found.extend(item for item in layer.issues if item.target.page == page_id)
        return tuple(found)

    def publication_blockers(self) -> tuple[Issue, ...]:
        """Errors in any draft, deduplicated by layer, pointer and code."""
        seen: set[tuple[str, str, str]] = set()
        found = []
        for layer in self.layers.values():
            for item in layer.errors:
                key = (item.layer, item.pointer, item.code)
                if key not in seen:
                    seen.add(key)
                    found.append(item)
        return tuple(found)

    def step_state(self, page_id: str) -> StepState:
        """A page's state from the current files and validation only."""
        if page_id == "welcome":
            return StepState.READY if self.has_drafts else StepState.NOT_STARTED
        if page_id == "overview":
            return StepState.READY if self.all_drafts else StepState.NOT_STARTED
        if not self.has_drafts:
            return StepState.NOT_STARTED
        if page_id in {"identity", "assays"}:
            bundle = self.layers["bundle"]
            if not bundle.exists:
                return StepState.NOT_STARTED
            if bundle.malformed:
                return StepState.BLOCKED
            issues = self.identity_issues() if page_id == "identity" else ()
            if page_id == "assays":
                issues = self.assay_issues()
                if not self.pipeline().get("assay_capabilities"):
                    return StepState.NOT_STARTED
            return (
                StepState.NEEDS_REVIEW
                if any(item.error for item in issues)
                else StepState.READY
            )
        layer_for = {
            "parameters": "inputs",
            "outputs": "outputs",
            "software": "components",
            "execution": "execution-profiles",
            "provenance": "provenance",
        }
        if page_id in layer_for:
            view = self.layers[layer_for[page_id]]
            if not view.exists:
                return StepState.NOT_STARTED
            if view.malformed:
                return StepState.BLOCKED
            if page_id == "outputs" and not self.outputs:
                return StepState.NOT_STARTED
            if page_id == "parameters" and self.submission_blockers:
                return StepState.NEEDS_REVIEW
            if page_id == "execution" and any(item.starter for item in self.profiles):
                return StepState.NEEDS_REVIEW
            return StepState.NEEDS_REVIEW if view.errors else StepState.READY
        if page_id == "review":
            return StepState.READY if self.drafts_valid else StepState.NEEDS_REVIEW
        if page_id == "publish":
            if self.published:
                return StepState.PUBLISHED
            return StepState.BLOCKED if not self.drafts_valid else StepState.NOT_STARTED
        return StepState.NOT_STARTED

    def step_states(self) -> dict[str, StepState]:
        return {item.id: self.step_state(item.id) for item in PAGES}


# ------------------------------------------------------------ building

#: Recognised structured sources (exact keys are read from these only).
SOURCES = (
    ("nextflow.config", "nextflow.config", "pipeline metadata block"),
    ("nextflow_schema.json", "nextflow_schema.json", "parameter definitions"),
    ("modules.json", "modules.json", "module identifiers and versions"),
    ("CITATION.cff", "CITATION.cff", "citation metadata"),
    ("RO-Crate", "ro-crate-metadata.json", "structured provenance"),
    ("Published bundle", f"{PUBLISHED_DIR}/bundle.json", "an earlier publication"),
)


def _issues(layer: str, validation: Any) -> tuple[Issue, ...]:
    found = []
    data = None
    for item in validation.issues:
        pointer = str(item.pointer or "")
        target = target_for(layer, pointer)
        entity = ""
        if target.entry:
            entity = target.entry
        elif target.index is not None:
            entity = f"#{target.index + 1}"
        found.append(
            Issue(
                layer,
                pointer,
                str(item.code),
                bounded(item.message),
                item.severity.value,
                field_label(pointer) if pointer else layer,
                entity,
                target,
            )
        )
    del data
    return tuple(found)


def _hash_bytes(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def model_key(repository: Path) -> str:
    """A cheap fingerprint of every draft, config and published file."""
    digest = hashlib.sha256()
    drafts = repository / DRAFTS_DIR
    candidates = sorted(drafts.rglob("*")) if drafts.is_dir() else []
    published = repository / PUBLISHED_DIR
    if published.is_dir():
        candidates += sorted(published.glob("*.json"))
        candidates += sorted(published.glob("*.yaml"))
    for path in candidates:
        if path.is_file():
            stat = path.stat()
            digest.update(f"{path}:{stat.st_size}:{stat.st_mtime_ns}\n".encode())
    for _label, relative, _purpose in SOURCES[:5]:
        path = repository / relative
        if path.is_file():
            stat = path.stat()
            digest.update(f"{relative}:{stat.st_size}:{stat.st_mtime_ns}\n".encode())
    return digest.hexdigest()


def _summary(value: Any) -> str:
    if value is None:
        return "none"
    if isinstance(value, str):
        return bounded(value, 40) if value else '""'
    return bounded(json.dumps(value), 40)


def _parameters(
    data: Mapping[str, Any], configs: Mapping[str, str], default_config: str | None
) -> tuple[
    tuple[ParameterRow, ...], tuple[tuple[str, str], ...], tuple[SubmissionBlocker, ...]
]:
    from nf_splice.layers.inputs import iter_parameters
    from nf_splice.services.readiness import _config_assigns

    required: set[str] = set(data.get("required") or [])
    groups: list[tuple[str, str]] = []
    definitions = data.get("$defs")
    if isinstance(definitions, Mapping):
        for name, definition in definitions.items():
            if isinstance(definition, Mapping):
                required.update(definition.get("required") or [])
                groups.append((str(name), bounded(definition.get("title") or name, 60)))
    titles = dict(groups)
    rows = []
    blockers = []
    config_text = configs.get(default_config or "", "")
    for item in iter_parameters(data):
        schema = item.schema
        access = tuple(item.editable_by or ())
        ui = (
            schema.get("x-splice-ui")
            if isinstance(schema.get("x-splice-ui"), Mapping)
            else {}
        )
        visibility = str(
            (ui or {}).get("visibility")
            or ("hidden" if schema.get("hidden") else "standard")
        )
        kind = schema.get("type")
        is_required = item.name in required
        rows.append(
            ParameterRow(
                item.name,
                item.group or "",
                titles.get(item.group or "", "Other parameters"),
                bounded(kind if isinstance(kind, str) else json.dumps(kind), 20),
                is_required,
                _summary(schema.get("default")) if "default" in schema else "none",
                access,
                visibility,
                bounded(schema.get("description") or "", 160),
                item.pointer,
            )
        )
        if (
            is_required
            and schema.get("default") in (None, "")
            and not access
            and not (config_text and _config_assigns(config_text, item.name))
        ):
            output_directory = item.name in {"outdir", "output_dir", "publish_dir"} or (
                schema.get("format") == "directory-path" and "out" in item.name.lower()
            )
            blockers.append(
                SubmissionBlocker(
                    item.name,
                    "required, has no default, and neither a user, the platform "
                    "nor an agent may supply it",
                    output_directory,
                )
            )
    return tuple(rows), tuple(groups), tuple(blockers)


def _output_rows(
    data: Mapping[str, Any], issues: Sequence[Issue]
) -> tuple[OutputRow, ...]:
    rows = []
    for index, item in enumerate(data.get("outputs") or []):
        if not isinstance(item, Mapping):
            continue
        problems = tuple(
            bounded(f"{issue.label}: {issue.message}", 160)
            for issue in issues
            if issue.error and issue.target.index == index
        )
        rows.append(
            OutputRow(
                index,
                str(item.get("key") or ""),
                bounded(item.get("title") or "", 60),
                bounded(item.get("category") or "", 40),
                tuple(str(value) for value in item.get("formats") or []),
                tuple(str(value) for value in item.get("scopes") or []),
                tuple(str(value) for value in item.get("entity_types") or []),
                tuple(str(value) for value in item.get("path_patterns") or []),
                not problems,
                problems,
                dict(item),
            )
        )
    return tuple(rows)


def _component_rows(data: Mapping[str, Any]) -> tuple[ComponentRow, ...]:
    containers = {
        str(item.get("id")): item
        for item in data.get("containers") or []
        if isinstance(item, Mapping)
    }
    rows = []
    for index, item in enumerate(data.get("components") or []):
        if not isinstance(item, Mapping):
            continue
        tool = item.get("tool") if isinstance(item.get("tool"), Mapping) else {}
        container = str(item.get("container_id") or "")
        sources = containers.get(container, {}).get("source_images") or {}
        rows.append(
            ComponentRow(
                index,
                str(item.get("id") or ""),
                bounded((tool or {}).get("name") or "", 40),
                bounded((tool or {}).get("version") or "", 30),
                container,
                tuple(
                    bounded(f"{runtime}: {reference}", 120)
                    for runtime, reference in sorted(dict(sources).items())
                ),
                tuple(bounded(value, 160) for value in item.get("unresolved") or []),
                str(item.get("type") or ""),
                str(item.get("path") or ""),
            )
        )
    return tuple(rows)


def _profile_rows(
    data: Mapping[str, Any], issues: Sequence[Issue]
) -> tuple[ProfileRow, ...]:
    rows = []
    default = data.get("default_profile")
    for index, item in enumerate(data.get("profiles") or []):
        if not isinstance(item, Mapping):
            continue
        config = item.get("config") if isinstance(item.get("config"), Mapping) else {}
        reference = (
            (config or {}).get("draft")
            or (config or {}).get("adopt")
            or (config or {}).get("source")
            or ""
        )
        problems = tuple(
            bounded(f"{issue.label}: {issue.message}", 160)
            for issue in issues
            if issue.error and issue.target.index == index
        )
        rows.append(
            ProfileRow(
                index,
                str(item.get("id") or ""),
                bounded(item.get("name") or "", 50),
                bounded(item.get("description") or "", 120),
                str(item.get("type") or ""),
                str(item.get("executor") or ""),
                str(item.get("container_engine") or ""),
                str(reference),
                item.get("id") == default,
                item.get("type") in (None, ""),
                problems,
            )
        )
    return tuple(rows)


def _imported(
    root: Path,
) -> tuple[tuple[ImportedValue, ...], dict[str, tuple[str, ...]]]:
    state = load_review_state(root, "bundle")
    values = []
    for item in state.document.get("evidence") or []:
        if not isinstance(item, Mapping):
            continue
        value = item.get("value")
        values.append(
            ImportedValue(
                str(item.get("field") or ""),
                bounded(value if isinstance(value, str) else json.dumps(value), 120),
                str(item.get("source") or ""),
                str(item.get("location") or ""),
            )
        )
    conflicts = {
        str(pointer): tuple(
            bounded(
                f"{choice.get('value')} ({choice.get('source')})"
                if isinstance(choice, Mapping)
                else choice,
                120,
            )
            for choice in choices or []
        )[:4]
        for pointer, choices in (state.conflicts or {}).items()
    }
    return tuple(values), conflicts


def _configs(root: Path) -> dict[str, str]:
    directory = root / DRAFTS_DIR / "configs"
    found = {}
    if directory.is_dir():
        for path in sorted(directory.glob("*.draft.config")):
            try:
                found[path.name] = path.read_text(encoding="utf-8")[:200_000]
            except (OSError, UnicodeError):
                continue
    return found


class ModelCache:
    """Validated layers keyed by the bytes of every draft and config."""

    def __init__(self) -> None:
        self._key: str | None = None
        self._layers: dict[str, LayerView] = {}

    def invalidate(self) -> None:
        self._key = None

    def layers(self, root: Path) -> tuple[str, dict[str, LayerView]]:
        from nf_splice.services.lifecycle import validate_layer

        digest = hashlib.sha256()
        for spec in LAYERS:
            digest.update(_hash_bytes(root / spec.draft).encode())
        for name, text in sorted(_configs(root).items()):
            digest.update(name.encode() + hashlib.sha256(text.encode()).digest())
        bundle_identity = root / PUBLISHED_DIR / "bundle.json"
        digest.update(_hash_bytes(bundle_identity).encode())
        key = digest.hexdigest()
        if key == self._key:
            return key, self._layers
        layers = {}
        for spec in LAYERS:
            state = read_layer(root, spec.name)
            exists = state.file.exists
            malformed = None
            data: Mapping[str, Any] = {}
            if exists and (
                state.draft is None or not isinstance(state.draft.data, dict)
            ):
                malformed = bounded(state.error or "the YAML cannot be read", 300)
            elif state.draft is not None and isinstance(state.draft.data, dict):
                data = strip_marker(state.draft.data)
            issues: tuple[Issue, ...] = ()
            if exists:
                try:
                    issues = _issues(spec.name, validate_layer(root, spec.name))
                except Exception as error:  # a validator bug must not blank the UI
                    issues = (
                        Issue(
                            spec.name,
                            "",
                            "validation_failed",
                            bounded(f"validation could not run: {error}"),
                            "error",
                            spec.name,
                            "",
                            target_for(spec.name, ""),
                        ),
                    )
            layers[spec.name] = LayerView(
                spec.name,
                spec.draft,
                exists,
                malformed,
                state.file.sha256,
                data,
                issues,
            )
        self._key, self._layers = key, layers
        return key, layers


def build_model(
    repository: str | Path, cache: ModelCache | None = None
) -> WorkspaceModel:
    """Read and validate the drafts once (call from a worker)."""
    from nf_splice.services.source import read_record

    root = Path(repository).resolve()
    cache = cache or ModelCache()
    key, layers = cache.layers(root)
    configs = _configs(root)
    try:
        integration = read_record(root)
    except (OSError, ValueError):
        integration = None
    imported, conflicts = _imported(root)
    inputs = layers["inputs"].data
    execution = layers["execution-profiles"].data
    default_config = None
    for item in execution.get("profiles") or []:
        if isinstance(item, Mapping) and item.get("id") == execution.get(
            "default_profile"
        ):
            config = (
                item.get("config") if isinstance(item.get("config"), Mapping) else {}
            )
            reference = str((config or {}).get("draft") or "")
            default_config = Path(reference).name if reference else None
    parameters, groups, blockers = _parameters(inputs, configs, default_config)
    components = layers["components"].data
    return WorkspaceModel(
        repository=root,
        key=key,
        layers=layers,
        sources=tuple(
            SourceFile(label, relative, (root / relative).is_file(), purpose)
            for label, relative, purpose in SOURCES
        ),
        configs=configs,
        integration=integration,
        imported=imported,
        conflicts=conflicts,
        parameters=parameters,
        groups=groups,
        submission_blockers=blockers,
        outputs=_output_rows(layers["outputs"].data, layers["outputs"].issues),
        components=_component_rows(components),
        containers=tuple(
            item
            for item in components.get("containers") or []
            if isinstance(item, Mapping)
        ),
        profiles=_profile_rows(execution, layers["execution-profiles"].issues),
        published=(root / PUBLISHED_DIR / "bundle.json").is_file(),
        read_only=not os.access(root, os.W_OK),
    )


def empty_model(repository: str | Path, error: str | None = None) -> WorkspaceModel:
    """The model before the first build finishes (nothing is claimed)."""
    root = Path(repository).resolve()
    return WorkspaceModel(
        repository=root,
        key="",
        layers={
            spec.name: LayerView(spec.name, spec.draft, False, None, None, {}, ())
            for spec in LAYERS
        },
        sources=(),
        configs={},
        integration=None,
        imported=(),
        conflicts={},
        parameters=(),
        groups=(),
        submission_blockers=(),
        outputs=(),
        components=(),
        containers=(),
        profiles=(),
        published=(root / PUBLISHED_DIR / "bundle.json").is_file(),
        read_only=not os.access(root, os.W_OK),
        error=error,
    )


# ------------------------------------------------------------ slower views


@dataclass(frozen=True, slots=True)
class ReadinessView:
    """Lifecycle facts and the output coverage, kept apart (ADR-0062)."""

    key: str
    headline: str
    state: str
    published: bool
    structurally_valid: bool
    classified: bool
    ingestion_ready: bool
    dimensions: Mapping[str, Mapping[str, Any]]
    coverage: Mapping[str, Any]
    reasons: tuple[str, ...] = field(default_factory=tuple)


def build_readiness(
    repository: str | Path, drafts_valid: bool, key: str
) -> ReadinessView:
    """Lifecycle and draft route coverage (call from a worker)."""
    from nf_splice.layers.outputs import route_coverage
    from nf_splice.services.readiness import lifecycle

    root = Path(repository).resolve()
    state = lifecycle(root, drafts_valid=drafts_valid)
    coverage = route_coverage(root)
    return ReadinessView(
        key,
        state.headline,
        state.state,
        state.published,
        state.structurally_valid,
        state.scientifically_classified,
        state.ingestion_ready,
        state.readiness.to_json()["dimensions"],
        coverage.to_json(),
        tuple(bounded(item, 300) for item in state.reasons()[:40]),
    )


@dataclass(frozen=True, slots=True)
class PlanView:
    """The validated promotion plan: exact files and their changes."""

    key: str
    ready: bool
    changes: tuple[tuple[str, str], ...]
    diffs: Mapping[str, str]
    blockers: tuple[str, ...]
    replaces_existing: bool


def build_plan(repository: str | Path, key: str) -> PlanView:
    from nf_splice.services.lifecycle import plan_promotion

    root = Path(repository).resolve()
    try:
        plan = plan_promotion(root)
    except ValueError as error:
        return PlanView(key, False, (), {}, (bounded(error, 300),), False)
    changes = tuple((item.kind, item.path) for item in plan.changes)
    return PlanView(
        key,
        plan.ready,
        changes,
        {item.path: (item.diff or "")[:200_000] for item in plan.changes},
        tuple(
            bounded(f"{item.layer}{item.pointer}: {item.message}", 300)
            for item in plan.blockers
        ),
        any(kind not in {"create", "unchanged"} for kind, _path in changes),
    )


_SAFE_NAME = re.compile(r"[^A-Za-z0-9_.-]+")


def private_path(repository: Path, *parts: str) -> Path:
    """A path in the repository's private workspace."""
    return (
        repository / PRIVATE_DIR / Path(*(_SAFE_NAME.sub("-", part) for part in parts))
    )
