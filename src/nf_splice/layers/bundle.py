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

from nf_splice.catalogue import CatalogueError, ResolvedCapability, default_catalogue
from nf_splice.domain.audit import ActorKind, ChangeOrigin
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
    update_review_state,
)

LAYER = "bundle"
_LIST_FIELDS = {"authors", "funders", "keywords", "assay_capabilities"}
CAPABILITIES = "assay_capabilities"
#: Why a capability is declared. ``asserted`` is a person's scientific
#: statement without repository evidence; the others cite where it is shown.
EVIDENCE = ("asserted", "confirmed", "documented", "detected")
#: Sidecar key for recommendations a reviewer rejected, with reasons.
REJECTIONS = "assay_rejections"
#: The obsolete free-text field replaced by ``assay_capabilities``.
LEGACY_MODALITY = "modality"


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
    if LEGACY_MODALITY in pipeline:
        legacy = pipeline.get(LEGACY_MODALITY)
        if legacy in (None, ""):
            issues.append(
                _issue(
                    f"/pipeline/{LEGACY_MODALITY}",
                    "obsolete_field",
                    "modality was replaced by assay_capabilities; remove it",
                    Severity.WARNING,
                )
            )
        else:
            issues.append(
                _issue(
                    f"/pipeline/{LEGACY_MODALITY}",
                    "legacy_modality",
                    f"free-text modality {legacy!r} is not converted to an assay; "
                    "declare each supported assay with "
                    "`nf-splice configure bundle --add-assay CODE`, "
                    "then remove modality",
                )
            )
    capabilities, capability_issues = _draft_capabilities(pipeline.get(CAPABILITIES))
    issues.extend(capability_issues)
    if not capabilities and not any(
        item.pointer.startswith(f"/pipeline/{CAPABILITIES}")
        for item in capability_issues
    ):
        issues.append(
            _issue(
                f"/pipeline/{CAPABILITIES}",
                "missing_assay_classification",
                "no assay capability is declared; a pipeline is not ready for SPLICE "
                f"ingestion without one. Assay discovery: {_recommendation(root)}. "
                "Review with `nf-splice catalogue recommend`, then declare with "
                "`nf-splice configure identity --add-assay CODE`",
            )
        )
    unknown = sorted(set(pipeline) - set(PIPELINE_FIELD_ORDER) - {LEGACY_MODALITY})
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
    # Seeded values the author has not edited are the author's draft like any
    # other: their review status is provenance, never a validation error.
    review = load_review_state(root, LAYER)
    for pointer, candidates in sorted(review.conflicts.items()):
        if resolve(state.draft.data, pointer) in (ABSENT, None, []):
            options = "; ".join(
                f"{_canonical(item['value'])} from {item['location']}"
                for item in candidates
            )
            required = pointer.removeprefix("/pipeline/") in REQUIRED_PIPELINE_FIELDS
            issues.append(
                _issue(
                    pointer,
                    "conflicting_evidence",
                    f"the repository disagrees about this value: {options}; "
                    "write the correct one into the draft",
                    Severity.ERROR if required else Severity.WARNING,
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
    present.pop(CAPABILITIES, None)
    if capabilities:
        present[CAPABILITIES] = [item.to_json() for item in capabilities]
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


def unreviewed_detected_values(repository_root: str | Path) -> tuple[str, ...]:
    """Pointers still holding a seeded value nobody has edited or confirmed.

    Advisory provenance only: a seeded value left in the draft is the
    author's value like any other and never blocks validation.
    """
    root = Path(repository_root).resolve()
    state = read_layer(root, LAYER)
    if state.draft is None:
        return ()
    return tuple(load_review_state(root, LAYER).pending(state.draft.data))


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
    if CAPABILITIES in changes or LEGACY_MODALITY in changes:
        raise LayerError(
            "assay capabilities are changed only with add_assay_capability and "
            "remove_assay_capability, which resolve them against the SPLICE vocabulary"
        )
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


# ------------------------------------------------------------ assay capabilities


def _draft_capabilities(
    raw: Any,
) -> tuple[tuple[ResolvedCapability, ...], list[DraftIssue]]:
    """Resolve the reviewed draft entries; every problem becomes an issue."""
    issues: list[DraftIssue] = []
    if raw in (None, []):
        return (), issues
    pointer = f"/pipeline/{CAPABILITIES}"
    if not isinstance(raw, list):
        return (), [_issue(pointer, "invalid_value", "must be a list of capabilities")]
    catalogue = default_catalogue()
    resolved: list[ResolvedCapability] = []
    seen: dict[str, int] = {}
    for index, entry in enumerate(raw):
        where = f"{pointer}/{index}"
        if not isinstance(entry, dict):
            issues.append(_issue(where, "invalid_value", "must be a mapping"))
            continue
        try:
            item = catalogue.resolve_reference(entry)
        except CatalogueError as error:
            issues.append(_issue(where, error.code, str(error)))
            continue
        if item.key in seen:
            issues.append(
                _issue(
                    where,
                    "duplicate",
                    f"{item.key} is already declared at entry {seen[item.key] + 1}",
                )
            )
            continue
        seen[item.key] = index
        evidence = entry.get("evidence")
        if evidence not in EVIDENCE:
            issues.append(
                _issue(
                    f"{where}/evidence",
                    "missing_required",
                    f"evidence must be one of {', '.join(EVIDENCE)}",
                )
            )
        if not str(entry.get("rationale") or "").strip():
            issues.append(
                _issue(
                    f"{where}/rationale",
                    "missing_required",
                    "say why the pipeline supports this assay",
                )
            )
        sources = entry.get("sources") or []
        if evidence in ("documented", "detected", "confirmed") and not sources:
            issues.append(
                _issue(
                    f"{where}/sources",
                    "missing_required",
                    f"{evidence} evidence cites where it is shown (path:line, or "
                    "the conversation for a person's confirmation)",
                )
            )
        if item.registration is None and catalogue.registrations_for(
            item.assay.entity_id
        ):
            codes = ", ".join(
                registration.code
                for registration in catalogue.registrations_for(item.assay.entity_id)
            )
            issues.append(
                _issue(
                    where,
                    "registered_alternative",
                    f"{item.assay.label!r} is registered as {codes}; prefer the "
                    "registered code",
                    Severity.WARNING,
                )
            )
        resolved.append(item)
    return tuple(resolved), issues


def declared_capabilities(repository_root: str | Path) -> list[dict[str, Any]]:
    """The reviewed draft entries, as stored (read-only)."""
    state = read_layer(Path(repository_root).resolve(), LAYER)
    if state.draft is None or not isinstance(state.draft.data, dict):
        return []
    pipeline = state.draft.data.get("pipeline") or {}
    entries = pipeline.get(CAPABILITIES) or []
    return [dict(item) for item in entries if isinstance(item, dict)]


def _write_capabilities(
    root: Path,
    entries: list[dict[str, Any]],
    context: ChangeContext,
    action: str,
    write: bool,
) -> EditResult:
    state = read_layer(root, LAYER)
    if state.draft is None:
        raise LayerError(f"{layer_spec(LAYER).draft} is missing or malformed")
    return edit_draft(
        root,
        LAYER,
        ops_for(state.draft.data, {f"/pipeline/{CAPABILITIES}": entries}),
        context,
        action=action,
        write=write,
    )


def add_assay_capability(
    repository_root: str | Path,
    reference: str | Mapping[str, Any],
    context: ChangeContext,
    *,
    evidence: str,
    rationale: str,
    sources: tuple[str, ...] = (),
    write: bool = True,
) -> EditResult:
    """Declare that the workflow can process one assay.

    ``reference`` is a registered code (``polya_rnaseq``), ``entity:<id>`` for
    an unregistered vocabulary assay, or a mapping checked field by field.
    Only a person may assert a capability without citing evidence.
    """
    root = Path(repository_root).resolve()
    if evidence not in EVIDENCE:
        raise LayerError(f"evidence must be one of {', '.join(EVIDENCE)}")
    if not rationale.strip():
        raise LayerError("give the reason the pipeline supports this assay")
    if evidence == "asserted" and context.actor.kind is not ActorKind.HUMAN:
        raise LayerError(
            "only a person may assert an assay capability without evidence; "
            "cite documented or detected evidence, or ask the person"
        )
    if evidence == "confirmed" and not (
        context.actor.kind is ActorKind.HUMAN
        or context.origin is ChangeOrigin.AGENT_ASSISTED
    ):
        raise LayerError(
            "confirmed evidence records a person's answer and is applied only "
            "after the person approves it (AI-assisted mode); an autonomous run "
            "records a blocker instead"
        )
    if evidence != "asserted" and not sources:
        raise LayerError(f"{evidence} evidence cites where it is shown (path:line)")
    catalogue = default_catalogue()
    try:
        item = catalogue.resolve_reference(reference)
    except CatalogueError as error:
        raise LayerError(f"{error.code}: {error}") from error
    entries = declared_capabilities(root)
    for existing in entries:
        try:
            if catalogue.resolve_reference(existing).key == item.key:
                raise LayerError(f"{item.key} is already declared")
        except CatalogueError:
            continue
    entry: dict[str, Any] = (
        {"registered_code": item.registration.code}
        if item.registration is not None
        else {"entity_id": item.assay.entity_id}
    )
    entry["evidence"] = evidence
    entry["rationale"] = rationale.strip()
    if sources:
        entry["sources"] = list(sources)
    result = _write_capabilities(
        root, [*entries, entry], context, "add_assay_capability", write
    )
    if write:
        _forget_rejection(root, item.key)
    return result


def remove_assay_capability(
    repository_root: str | Path,
    reference: str,
    context: ChangeContext,
    *,
    write: bool = True,
) -> EditResult:
    """Remove a declared capability by code or ``entity:<id>``."""
    root = Path(repository_root).resolve()
    catalogue = default_catalogue()
    entries = declared_capabilities(root)
    kept = []
    for entry in entries:
        key = entry.get("registered_code") or f"entity:{entry.get('entity_id')}"
        try:
            key = catalogue.resolve_reference(entry).key
        except CatalogueError:
            pass
        if key != reference.strip():
            kept.append(entry)
    if len(kept) == len(entries):
        raise LayerError(f"{reference} is not declared")
    return _write_capabilities(root, kept, context, "remove_assay_capability", write)


def _recommendation(root: Path) -> str:
    from nf_splice.services.assay_discovery import assess_assays

    try:
        return assess_assays(root, rejected=rejected_assays(root)).summary()
    except (CatalogueError, OSError):  # never let discovery hide the issue itself
        return "could not run assay discovery"


def rejected_assays(repository_root: str | Path) -> tuple[str, ...]:
    """Recommendations a reviewer rejected (kept in the review sidecar)."""
    state = load_review_state(Path(repository_root).resolve(), LAYER)
    return tuple(
        str(item.get("reference"))
        for item in state.document.get(REJECTIONS) or []
        if isinstance(item, dict)
    )


def reject_assay_candidate(
    repository_root: str | Path,
    reference: str,
    context: ChangeContext,
    *,
    reason: str,
) -> None:
    """Record that a recommended assay does not apply, and why."""
    from nf_splice.domain.audit import ActorKind as _Kind

    root = Path(repository_root).resolve()
    if not reason.strip():
        raise LayerError("give the reason the assay does not apply")
    try:
        key = default_catalogue().resolve_reference(reference).key
    except CatalogueError as error:
        raise LayerError(f"{error.code}: {error}") from error
    for entry in declared_capabilities(root):
        try:
            if default_catalogue().resolve_reference(entry).key == key:
                raise LayerError(f"{key} is declared; remove it before rejecting it")
        except CatalogueError:
            continue

    def mutate(state: ReviewState) -> None:
        kept = [
            item
            for item in state.document.get(REJECTIONS) or []
            if isinstance(item, dict) and item.get("reference") != key
        ]
        kept.append(
            {
                "reference": key,
                "reason": reason.strip(),
                "actor": context.actor.label,
                "actor_kind": context.actor.kind.value
                if isinstance(context.actor.kind, _Kind)
                else str(context.actor.kind),
                "origin": context.origin.value,
            }
        )
        state.document[REJECTIONS] = sorted(kept, key=lambda item: item["reference"])

    update_review_state(root, LAYER, mutate)


def _forget_rejection(root: Path, key: str) -> None:
    def mutate(state: ReviewState) -> None:
        rows = state.document.get(REJECTIONS) or []
        state.document[REJECTIONS] = [
            item
            for item in rows
            if isinstance(item, dict) and item.get("reference") != key
        ]

    if key in rejected_assays(root):
        update_review_state(root, LAYER, mutate)
