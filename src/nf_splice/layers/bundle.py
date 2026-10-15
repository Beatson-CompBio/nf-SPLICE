"""Identity layer: the authoritative ``.splice-local/drafts/bundle.draft.yaml``.

The draft holds the reviewed pipeline identity and descriptive metadata that
every detached contract reuses. Values found in ``nextflow.config``, Git,
``CITATION.cff``, ``README.md`` or the RO-Crate are *evidence*: they are
seeded into a new draft, recorded as unconfirmed and block promotion until a
person confirms or edits them. Conflicting evidence is never chosen.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from nf_splice.domain.identity import (
    PIPELINE_FIELD_ORDER,
    REQUIRED_PIPELINE_FIELDS,
    Maintainer,
    PipelineIdError,
    PipelineMetadata,
    derive_pipeline_id,
    is_placeholder,
)
from nf_splice.drafts import ABSENT, resolve
from nf_splice.inspectors.identity import IdentityValue, inspect_pipeline_identity
from nf_splice.layers.base import (
    ChangeContext,
    DraftIssue,
    EditResult,
    LayerError,
    ReviewState,
    Severity,
    edit_draft,
    layer_spec,
    load_review_state,
    ops_for,
    read_layer,
    seed_draft,
    strip_marker,
)

LAYER = "bundle"
_LIST_FIELDS = {"authors", "funders", "keywords"}


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _empty_pipeline() -> dict[str, Any]:
    return {
        key: [] if key in _LIST_FIELDS else ("nextflow" if key == "engine" else None)
        for key in PIPELINE_FIELD_ORDER
    }


@dataclass(frozen=True, slots=True)
class SeedResult:
    """Outcome of seeding the identity draft from repository evidence."""

    created: bool
    seeded: tuple[str, ...]
    conflicts: tuple[str, ...]


def _grouped(values: tuple[IdentityValue, ...]) -> dict[str, list[IdentityValue]]:
    grouped: dict[str, list[IdentityValue]] = defaultdict(list)
    for item in values:
        grouped[item.field].append(item)
    return grouped


def seed_bundle_draft(
    repository_root: str | Path,
    *,
    explicit: Mapping[str, Any] | None = None,
) -> SeedResult:
    """Create ``bundle.draft.yaml`` from evidence if it does not already exist.

    Explicitly supplied values are developer-authored and never marked as
    detected. Unanimous evidence is seeded but unconfirmed; conflicting
    evidence leaves the field null and is recorded for review.
    """
    root = Path(repository_root).resolve()
    supplied = dict(explicit or {})
    unknown = sorted(set(supplied) - set(PIPELINE_FIELD_ORDER))
    if unknown:
        raise LayerError(f"unknown identity field(s): {', '.join(unknown)}")
    inspection = inspect_pipeline_identity(root)
    pipeline = _empty_pipeline()
    seeded: list[str] = []
    conflicts: dict[str, list[dict[str, Any]]] = {}
    evidence: list[dict[str, Any]] = []
    for field_name, items in sorted(_grouped(inspection.values).items()):
        for item in items:
            evidence.append(
                {
                    "field": field_name,
                    "value": item.value,
                    "source": item.evidence.provenance.source,
                    "location": item.evidence.provenance.location,
                }
            )
        if field_name in supplied or field_name not in pipeline:
            continue
        distinct = {_canonical(item.value): item.value for item in items}
        if len(distinct) == 1:
            pipeline[field_name] = next(iter(distinct.values()))
            seeded.append(f"/pipeline/{field_name}")
        else:
            conflicts[f"/pipeline/{field_name}"] = [
                {
                    "value": item.value,
                    "source": item.evidence.provenance.source,
                    "location": item.evidence.provenance.location,
                }
                for item in items
            ]
    pipeline.update(supplied)
    if pipeline.get("id") is None and isinstance(pipeline.get("name"), str):
        try:
            pipeline["id"] = derive_pipeline_id(pipeline["name"])
        except PipelineIdError:
            pipeline["id"] = None
        if "name" not in supplied and pipeline["id"] is not None:
            seeded.append("/pipeline/id")
    data = {
        "pipeline": pipeline,
        "maintainers": [],
        "maintainers_publication_approved": False,
    }

    def review(state: ReviewState) -> None:
        state.conflicts.update(conflicts)
        state.document["evidence"] = evidence

    created = seed_draft(root, LAYER, data, seeded_pointers=seeded, review=review)
    return SeedResult(created, tuple(sorted(seeded)), tuple(sorted(conflicts)))


@dataclass(frozen=True, slots=True)
class BundleValidation:
    """Identity draft readiness derived from the current draft bytes."""

    metadata: PipelineMetadata | None
    maintainers: tuple[Maintainer, ...]
    issues: tuple[DraftIssue, ...]

    @property
    def ready(self) -> bool:
        return self.metadata is not None and not any(
            item.severity is Severity.ERROR for item in self.issues
        )


def _issue(
    pointer: str, code: str, message: str, severity: Severity = Severity.ERROR
) -> DraftIssue:
    return DraftIssue(LAYER, layer_spec(LAYER).draft, pointer, severity, code, message)


def _pointer(location: tuple[Any, ...], prefix: str) -> str:
    return prefix + "".join(f"/{item}" for item in location)


def _text_values(value: Any, pointer: str) -> list[tuple[str, str]]:
    if isinstance(value, str):
        return [(pointer, value)]
    if isinstance(value, list):
        return [
            found
            for index, item in enumerate(value)
            for found in _text_values(item, f"{pointer}/{index}")
        ]
    if isinstance(value, dict):
        return [
            found
            for key, item in value.items()
            for found in _text_values(item, f"{pointer}/{key}")
        ]
    return []


def validate_bundle_draft(repository_root: str | Path) -> BundleValidation:
    """Validate the identity draft and derive its readiness (read-only)."""
    root = Path(repository_root).resolve()
    state = read_layer(root, LAYER)
    path = layer_spec(LAYER).draft
    if not state.file.exists:
        return BundleValidation(
            None, (), (_issue("", "missing_draft", f"{path} does not exist"),)
        )
    if state.draft is None:
        return BundleValidation(
            None, (), (_issue("", "syntax", f"{path}: {state.error}"),)
        )
    data = strip_marker(state.draft.data) if isinstance(state.draft.data, dict) else {}
    issues: list[DraftIssue] = [
        _issue("", "yaml_warning", warning, Severity.WARNING)
        for warning in state.draft.warnings
    ]
    pipeline = data.get("pipeline")
    if not isinstance(pipeline, dict):
        return BundleValidation(
            None,
            (),
            (*issues, _issue("/pipeline", "missing_required", "pipeline is required")),
        )
    unknown = sorted(set(pipeline) - set(PIPELINE_FIELD_ORDER))
    for name in unknown:
        issues.append(
            _issue(f"/pipeline/{name}", "unknown_field", f"unknown field {name!r}")
        )
    for name in REQUIRED_PIPELINE_FIELDS:
        if pipeline.get(name) in (None, ""):
            issues.append(
                _issue(
                    f"/pipeline/{name}",
                    "missing_required",
                    f"pipeline.{name} is required for an ingestion-ready bundle",
                )
            )
    for pointer, text in _text_values(pipeline, "/pipeline"):
        if is_placeholder(text):
            issues.append(
                _issue(
                    pointer, "placeholder", f"placeholder value {text!r} is not allowed"
                )
            )
    review = load_review_state(root, LAYER)
    for pointer in review.pending(state.draft.data):
        issues.append(
            _issue(
                pointer,
                "unconfirmed_detected_value",
                "detected value requires explicit confirmation or editing "
                f"(nf-splice draft confirm bundle {pointer})",
            )
        )
    for pointer, candidates in sorted(review.conflicts.items()):
        if resolve(state.draft.data, pointer) in (ABSENT, None, []):
            options = "; ".join(
                f"{_canonical(item['value'])} from {item['location']}"
                for item in candidates
            )
            issues.append(
                _issue(
                    pointer,
                    "conflicting_evidence",
                    f"conflicting detected values: {options}",
                )
            )
    if not pipeline.get("description"):
        issues.append(
            _issue(
                "/pipeline/description",
                "recommended",
                "a concise description is recommended for platform display",
                Severity.WARNING,
            )
        )
    evidence = review.document.get("evidence") or []
    remotes = {
        item["value"]
        for item in evidence
        if isinstance(item, dict)
        and item.get("source") == "git_remote"
        and item.get("field") == "repository_url"
    }
    repository_url = pipeline.get("repository_url")
    if (
        remotes
        and isinstance(repository_url, str)
        and repository_url.rstrip("/")
        not in {str(item).rstrip("/") for item in remotes}
    ):
        issues.append(
            _issue(
                "/pipeline/repository_url",
                "repository_mismatch",
                f"repository_url differs from the Git remote {sorted(remotes)}",
                Severity.WARNING,
            )
        )
    release_url, version = pipeline.get("release_url"), pipeline.get("version")
    if (
        isinstance(release_url, str)
        and isinstance(version, str)
        and (version not in release_url)
    ):
        issues.append(
            _issue(
                "/pipeline/release_url",
                "stale_release_url",
                f"release_url does not reference pipeline version {version!r}",
                Severity.WARNING,
            )
        )
    engine_versions = {
        str(item["value"])
        for item in evidence
        if isinstance(item, dict)
        and item.get("field") == "engine_version_min"
        and item.get("source") == "nextflow.config"
    }
    declared = pipeline.get("engine_version_min")
    if (
        engine_versions
        and declared is not None
        and str(declared) not in engine_versions
    ):
        issues.append(
            _issue(
                "/pipeline/engine_version_min",
                "contradictory_engine_version",
                "engine_version_min contradicts nextflow.config "
                f"nextflowVersion {sorted(engine_versions)}",
            )
        )
    maintainers: tuple[Maintainer, ...] = ()
    raw_maintainers = data.get("maintainers") or []
    try:
        maintainers = tuple(Maintainer.model_validate(item) for item in raw_maintainers)
    except ValidationError as error:
        for detail in error.errors():
            issues.append(
                _issue(
                    _pointer(tuple(detail["loc"]), "/maintainers"),
                    "invalid_value",
                    detail["msg"],
                )
            )
    if maintainers and data.get("maintainers_publication_approved") is not True:
        issues.append(
            _issue(
                "/maintainers_publication_approved",
                "publication_consent",
                "maintainer contacts are published in bundle.json; set "
                "maintainers_publication_approved: true to approve publication",
            )
        )
    metadata = None
    present = {key: value for key, value in pipeline.items() if value not in (None, [])}
    try:
        metadata = PipelineMetadata.model_validate(
            {
                key: value
                for key, value in present.items()
                if key in PIPELINE_FIELD_ORDER
            }
        )
    except ValidationError as error:
        for detail in error.errors():
            location = tuple(detail["loc"])
            if (
                detail["type"] == "missing"
                and location
                and location[0] in (REQUIRED_PIPELINE_FIELDS)
            ):
                continue
            issues.append(
                _issue(_pointer(location, "/pipeline"), "invalid_value", detail["msg"])
            )
    return BundleValidation(metadata, maintainers, tuple(issues))


def require_identity(repository_root: str | Path) -> PipelineMetadata:
    """Return reviewed identity or raise with every blocking issue."""
    validation = validate_bundle_draft(repository_root)
    if not validation.ready or validation.metadata is None:
        blocking = "; ".join(
            f"{item.pointer or '/'}: {item.message}"
            for item in validation.issues
            if item.severity is Severity.ERROR
        )
        raise LayerError(f"pipeline identity is not ready: {blocking}")
    return validation.metadata


def set_identity_fields(
    repository_root: str | Path,
    changes: Mapping[str, Any],
    context: ChangeContext,
    *,
    write: bool = True,
) -> EditResult:
    """Apply reviewed identity values as a targeted patch of the draft."""
    root = Path(repository_root).resolve()
    unknown = sorted(
        set(changes)
        - {*PIPELINE_FIELD_ORDER, "maintainers", "maintainers_publication_approved"}
    )
    if unknown:
        raise LayerError(f"unknown identity field(s): {', '.join(unknown)}")
    state = read_layer(root, LAYER)
    if state.draft is None:
        raise LayerError(f"{layer_spec(LAYER).draft} is missing or malformed")
    pointers = {
        (f"/{key}" if key.startswith("maintainers") else f"/pipeline/{key}"): value
        for key, value in changes.items()
    }
    return edit_draft(
        root,
        LAYER,
        ops_for(state.draft.data, pointers),
        context,
        action="set_identity",
        write=write,
    )
