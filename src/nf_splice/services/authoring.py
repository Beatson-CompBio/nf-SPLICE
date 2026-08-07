"""Shared authoring operations for identity and output review."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]
from pydantic import ValidationError

from nf_splice.domain import (
    AuthoringDocument,
    Decision,
    DecisionStatus,
    LayerState,
    OutputCandidate,
    OutputContractSettings,
    PipelineIdentity,
    ReviewedOutput,
    UnresolvedDecision,
    dump_authoring_document,
    load_authoring_document,
)
from nf_splice.inspectors import (
    discover_output_candidates,
    inspect_pipeline_identity,
)

_IDENTITY_FIELDS = ("name", "version", "repository_url")
_PLACEHOLDERS = {
    "example",
    "example-pipeline",
    "n/a",
    "none",
    "placeholder",
    "todo",
    "tbd",
    "unknown",
    "0.0.0",
}


class AuthoringOperationError(ValueError):
    """Raised when a requested authoring operation is not safe or complete."""


class IdentityResolutionError(AuthoringOperationError):
    """Raised when pipeline identity cannot be reviewed without more input."""


class OutputReviewError(AuthoringOperationError):
    """Raised when an output review action is invalid or incomplete."""


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    """Persisted document and the unresolved candidates remaining after discovery."""

    document: AuthoringDocument
    unresolved: tuple[OutputCandidate, ...]


def _document_path(repository_root: str | Path) -> Path:
    return Path(repository_root).resolve() / "nf-splice.yaml"


def _write_document(path: Path, document: AuthoringDocument) -> None:
    content = dump_authoring_document(document)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _validate_identity_value(field: str, value: str) -> str:
    value = value.strip()
    if not value:
        raise IdentityResolutionError(f"pipeline {field} must not be empty")
    lowered = value.lower()
    if (
        lowered in _PLACEHOLDERS
        or "example.com" in lowered
        or "example.org" in lowered
        or "/example" in lowered
    ):
        raise IdentityResolutionError(
            f"pipeline {field} cannot use placeholder value {value!r}"
        )
    return value


def initialise_authoring_document(
    repository_root: str | Path,
    *,
    name: str | None = None,
    version: str | None = None,
    repository_url: str | None = None,
    release_url: str | None = None,
    accept_detected: bool = False,
) -> AuthoringDocument:
    """Create canonical state from explicit or explicitly accepted identity evidence."""
    path = _document_path(repository_root)
    if path.exists():
        raise AuthoringOperationError(f"authoring state already exists: {path}")
    inspection = inspect_pipeline_identity(path.parent)
    explicit = {
        "name": name,
        "version": version,
        "repository_url": repository_url,
        "release_url": release_url,
    }
    by_field: dict[str, list[Any]] = {}
    for item in inspection.values:
        by_field.setdefault(item.field, []).append(item)

    selected: dict[str, str | None] = {}
    decisions: list[Decision] = []
    for field in (*_IDENTITY_FIELDS, "release_url"):
        supplied = explicit[field]
        candidates = by_field.get(field, [])
        distinct = {item.value for item in candidates}
        if supplied is not None:
            value = _validate_identity_value(field, supplied)
        elif not candidates:
            if field in _IDENTITY_FIELDS:
                raise IdentityResolutionError(
                    f"pipeline {field} is required; provide --{field.replace('_', '-')}"
                )
            value = None
        elif not accept_detected:
            if field == "release_url":
                value = None
            else:
                options = ", ".join(sorted(distinct))
                raise IdentityResolutionError(
                    f"pipeline {field} has detected value(s) {options}; "
                    "provide an explicit value or use --accept-detected"
                )
        elif len(distinct) > 1:
            options = ", ".join(sorted(distinct))
            raise IdentityResolutionError(
                f"conflicting detected pipeline {field} values: {options}; "
                f"provide --{field.replace('_', '-')} explicitly"
            )
        else:
            value = _validate_identity_value(field, next(iter(distinct)))
        selected[field] = value
        if value is not None:
            decisions.append(
                Decision(
                    id=f"identity:{field}",
                    status=DecisionStatus.REVIEWED,
                    value=value,
                    evidence_ids=tuple(sorted(item.evidence.id for item in candidates)),
                )
            )

    evidence = tuple(
        sorted((item.evidence for item in inspection.values), key=lambda item: item.id)
    )
    identity_decisions = tuple(item.id for item in decisions)
    document = AuthoringDocument(
        pipeline=PipelineIdentity(**selected),
        evidence=evidence,
        decisions=tuple(decisions),
        layers=(
            LayerState(
                name="identity",
                configured=True,
                decision_ids=identity_decisions,
            ),
        ),
    )
    _write_document(path, document)
    return document


def load_repository_document(repository_root: str | Path) -> AuthoringDocument:
    """Load required canonical state for a mutating authoring operation."""
    path = _document_path(repository_root)
    if not path.is_file():
        raise AuthoringOperationError(
            f"authoring state does not exist: {path}; run nf-splice init first"
        )
    return load_authoring_document(path.read_text(encoding="utf-8"))


def _replace_layer(
    layers: Sequence[LayerState], replacement: LayerState
) -> tuple[LayerState, ...]:
    retained = [item for item in layers if item.name != replacement.name]
    retained.append(replacement)
    return tuple(sorted(retained, key=lambda item: item.name))


def _candidate_from_decision(decision: Decision) -> OutputCandidate | None:
    if decision.status not in {DecisionStatus.CANDIDATE, DecisionStatus.CONFLICT}:
        return None
    try:
        return OutputCandidate.model_validate(decision.value)
    except ValidationError:
        return None


def unresolved_output_candidates(
    document: AuthoringDocument,
) -> tuple[OutputCandidate, ...]:
    """Return machine-readable candidates that still require review."""
    layer = next((item for item in document.layers if item.name == "outputs"), None)
    if layer is None:
        return ()
    by_id = {item.id: item for item in document.decisions}
    candidates = (
        _candidate_from_decision(by_id[item_id]) for item_id in layer.decision_ids
    )
    return tuple(
        sorted(
            (item for item in candidates if item is not None), key=lambda item: item.id
        )
    )


def discover_outputs(
    repository_root: str | Path,
    *,
    example_output_tree: str | Path | None = None,
    publish_directory: str | Path | None = None,
    contract_version: str | None = None,
) -> DiscoveryResult:
    """Discover candidates idempotently while preserving all reviewed decisions."""
    root = Path(repository_root).resolve()
    document = load_repository_document(root)
    discovered = discover_output_candidates(
        root,
        example_output_tree=example_output_tree,
        publish_directory=publish_directory,
    )
    evidence_by_id = {item.id: item for item in document.evidence}
    decisions_by_id = {item.id: item for item in document.decisions}
    output_layer = next(
        (item for item in document.layers if item.name == "outputs"), None
    )
    output_ids = set(output_layer.decision_ids if output_layer else ())

    for item in discovered:
        for evidence in item.evidence:
            evidence_by_id[evidence.id] = evidence
        candidate = item.candidate
        evidence_ids = tuple(sorted(evidence.id for evidence in item.evidence))
        existing = decisions_by_id.get(candidate.id)
        if existing is None:
            decisions_by_id[candidate.id] = Decision(
                id=candidate.id,
                value=candidate.model_dump(mode="json"),
                evidence_ids=evidence_ids,
            )
        else:
            updates: dict[str, object] = {
                "evidence_ids": tuple(
                    sorted(set(existing.evidence_ids) | set(evidence_ids))
                )
            }
            if existing.status is DecisionStatus.CANDIDATE:
                updates["value"] = candidate.model_dump(mode="json")
            decisions_by_id[candidate.id] = Decision.model_validate(
                existing.model_copy(update=updates).model_dump()
            )
        output_ids.add(candidate.id)

    unresolved = []
    for decision_id in sorted(output_ids):
        decision = decisions_by_id[decision_id]
        if decision.status in {DecisionStatus.CANDIDATE, DecisionStatus.CONFLICT}:
            unresolved.append(
                UnresolvedDecision(
                    decision_id=decision_id,
                    reason="Output meaning requires explicit developer review",
                )
            )
    layer = LayerState(
        name="outputs",
        configured=True,
        decision_ids=tuple(sorted(output_ids)),
        unresolved=tuple(unresolved),
    )
    output_contract = document.output_contract
    if contract_version is not None:
        output_contract = OutputContractSettings(schema_version=contract_version)
    updated = AuthoringDocument(
        schema_version=document.schema_version,
        pipeline=document.pipeline,
        output_contract=output_contract,
        evidence=tuple(sorted(evidence_by_id.values(), key=lambda item: item.id)),
        decisions=tuple(sorted(decisions_by_id.values(), key=lambda item: item.id)),
        layers=_replace_layer(document.layers, layer),
    )
    _write_document(_document_path(root), updated)
    return DiscoveryResult(updated, unresolved_output_candidates(updated))


def _replace_decision(
    document: AuthoringDocument, replacement: Decision
) -> AuthoringDocument:
    decisions = {item.id: item for item in document.decisions}
    if replacement.id not in decisions:
        raise OutputReviewError(f"unknown output candidate {replacement.id!r}")
    decisions[replacement.id] = replacement
    output_layer = next(
        (item for item in document.layers if item.name == "outputs"), None
    )
    if output_layer is None or replacement.id not in output_layer.decision_ids:
        raise OutputReviewError(
            f"decision {replacement.id!r} is not an output candidate"
        )
    unresolved = tuple(
        item for item in output_layer.unresolved if item.decision_id != replacement.id
    )
    layer = output_layer.model_copy(update={"unresolved": unresolved})
    return AuthoringDocument(
        schema_version=document.schema_version,
        pipeline=document.pipeline,
        output_contract=document.output_contract,
        evidence=document.evidence,
        decisions=tuple(sorted(decisions.values(), key=lambda item: item.id)),
        layers=_replace_layer(document.layers, layer),
    )


def _ensure_unique_output_key(
    document: AuthoringDocument, output: ReviewedOutput, decision_id: str
) -> None:
    for decision in document.decisions:
        if decision.id == decision_id or decision.status is not DecisionStatus.REVIEWED:
            continue
        try:
            reviewed = ReviewedOutput.model_validate(decision.value)
        except ValidationError:
            continue
        if reviewed.key == output.key:
            raise OutputReviewError(
                f"reviewed output key {output.key!r} is already used by {decision.id!r}"
            )


def accept_output(
    repository_root: str | Path,
    candidate_id: str,
    output: ReviewedOutput | Mapping[str, Any],
) -> AuthoringDocument:
    """Accept a complete output definition through the shared transition rules."""
    document = load_repository_document(repository_root)
    reviewed = (
        output
        if isinstance(output, ReviewedOutput)
        else ReviewedOutput.model_validate(output)
    )
    _ensure_unique_output_key(document, reviewed, candidate_id)
    current = next(
        (item for item in document.decisions if item.id == candidate_id), None
    )
    if current is None:
        raise OutputReviewError(f"unknown output candidate {candidate_id!r}")
    replacement = Decision(
        id=current.id,
        status=DecisionStatus.REVIEWED,
        value=reviewed.model_dump(mode="json"),
        evidence_ids=current.evidence_ids,
    )
    updated = _replace_decision(document, replacement)
    _write_document(_document_path(repository_root), updated)
    return updated


def reject_output(
    repository_root: str | Path, candidate_id: str, reason: str
) -> AuthoringDocument:
    """Reject a candidate explicitly while retaining it across rediscovery."""
    document = load_repository_document(repository_root)
    current = next(
        (item for item in document.decisions if item.id == candidate_id), None
    )
    if current is None:
        raise OutputReviewError(f"unknown output candidate {candidate_id!r}")
    replacement = Decision(
        id=current.id,
        status=DecisionStatus.REJECTED,
        value=current.value,
        evidence_ids=current.evidence_ids,
        reason=reason,
    )
    updated = _replace_decision(document, replacement)
    _write_document(_document_path(repository_root), updated)
    return updated


def merge_outputs(
    repository_root: str | Path,
    candidate_ids: Sequence[str],
    output: ReviewedOutput | Mapping[str, Any],
) -> AuthoringDocument:
    """Merge multiple candidates into the first reviewed output decision."""
    if len(candidate_ids) < 2 or len(candidate_ids) != len(set(candidate_ids)):
        raise OutputReviewError("merge requires at least two unique candidate ids")
    document = accept_output(repository_root, candidate_ids[0], output)
    for candidate_id in candidate_ids[1:]:
        document = reject_output(
            repository_root,
            candidate_id,
            f"Merged into {candidate_ids[0]}",
        )
    return document


def split_output(
    repository_root: str | Path,
    candidate_id: str,
    outputs: Sequence[ReviewedOutput | Mapping[str, Any]],
) -> AuthoringDocument:
    """Replace one broad candidate with two or more reviewed output decisions."""
    if len(outputs) < 2:
        raise OutputReviewError("split requires at least two reviewed outputs")
    document = load_repository_document(repository_root)
    source = next(
        (item for item in document.decisions if item.id == candidate_id), None
    )
    if source is None:
        raise OutputReviewError(f"unknown output candidate {candidate_id!r}")
    reviewed_outputs = tuple(
        item
        if isinstance(item, ReviewedOutput)
        else ReviewedOutput.model_validate(item)
        for item in outputs
    )
    if len({item.key for item in reviewed_outputs}) != len(reviewed_outputs):
        raise OutputReviewError("split output keys must be unique")
    document = reject_output(
        repository_root, candidate_id, "Split into narrower reviewed outputs"
    )
    decisions = {item.id: item for item in document.decisions}
    layer = next(item for item in document.layers if item.name == "outputs")
    decision_ids = set(layer.decision_ids)
    for output in reviewed_outputs:
        digest = hashlib.sha256(f"{candidate_id}\0{output.key}".encode()).hexdigest()[
            :16
        ]
        new_id = f"output:{digest}"
        _ensure_unique_output_key(document, output, new_id)
        decisions[new_id] = Decision(
            id=new_id,
            status=DecisionStatus.REVIEWED,
            value=output.model_dump(mode="json"),
            evidence_ids=source.evidence_ids,
        )
        decision_ids.add(new_id)
    replacement_layer = layer.model_copy(
        update={"decision_ids": tuple(sorted(decision_ids))}
    )
    updated = AuthoringDocument(
        schema_version=document.schema_version,
        pipeline=document.pipeline,
        output_contract=document.output_contract,
        evidence=document.evidence,
        decisions=tuple(sorted(decisions.values(), key=lambda item: item.id)),
        layers=_replace_layer(document.layers, replacement_layer),
    )
    _write_document(_document_path(repository_root), updated)
    return updated


def apply_output_decision_file(
    repository_root: str | Path, decision_file: str | Path
) -> AuthoringDocument:
    """Apply explicit accept, reject, merge, and split actions from YAML."""
    loaded = yaml.safe_load(Path(decision_file).read_text(encoding="utf-8"))
    if not isinstance(loaded, dict) or not isinstance(loaded.get("actions"), list):
        raise OutputReviewError("decision file must contain an actions list")
    document = load_repository_document(repository_root)
    for index, action in enumerate(loaded["actions"]):
        if not isinstance(action, dict) or not isinstance(action.get("action"), str):
            raise OutputReviewError(f"decision action {index} is invalid")
        kind = action["action"]
        if kind == "accept":
            document = accept_output(
                repository_root,
                str(action.get("candidate_id", "")),
                action.get("output", {}),
            )
        elif kind == "reject":
            document = reject_output(
                repository_root,
                str(action.get("candidate_id", "")),
                str(action.get("reason", "")),
            )
        elif kind == "merge":
            candidate_ids = action.get("candidate_ids")
            if not isinstance(candidate_ids, list):
                raise OutputReviewError(f"merge action {index} needs candidate_ids")
            document = merge_outputs(
                repository_root,
                [str(item) for item in candidate_ids],
                action.get("output", {}),
            )
        elif kind == "split":
            outputs = action.get("outputs")
            if not isinstance(outputs, list):
                raise OutputReviewError(f"split action {index} needs outputs")
            document = split_output(
                repository_root,
                str(action.get("candidate_id", "")),
                outputs,
            )
        else:
            raise OutputReviewError(f"unknown output review action {kind!r}")
    return document
