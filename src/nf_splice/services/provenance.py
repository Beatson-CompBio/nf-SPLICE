"""Discover, review, and safely include developer-generated workflow provenance."""

from __future__ import annotations

import difflib
import os
from pathlib import Path

from nf_splice.domain import (
    AuthoringDocument,
    Decision,
    DecisionStatus,
    Evidence,
    EvidenceProvenance,
    LayerState,
    PathClassification,
    UnresolvedDecision,
)
from nf_splice.domain.provenance import ProvenanceCandidate, ReviewedProvenance
from nf_splice.inspectors import inspect_splice_tree
from nf_splice.renderers.provenance import render_provenance
from nf_splice.services.authoring import (
    load_repository_document,
    save_repository_document,
)
from nf_splice.services.static_layers import (
    StaticChangeKind,
    StaticLayerBuildResult,
    StaticLayerChange,
)


class ProvenanceReviewError(ValueError):
    """Raised when the required root RO-Crate cannot be reviewed safely."""


_CANDIDATE_ID = "provenance:root-ro-crate"
_SOURCE_PATH = "ro-crate-metadata.json"
_MISSING_MESSAGE = (
    "repository-root ro-crate-metadata.json is required; generate it with "
    "`nf-core pipelines rocrate .`, then retry"
)


def _replace_layer(
    layers: tuple[LayerState, ...], replacement: LayerState
) -> tuple[LayerState, ...]:
    retained = [item for item in layers if item.name != replacement.name]
    retained.append(replacement)
    return tuple(sorted(retained, key=lambda item: item.name))


def discover_provenance(repository_root: str | Path) -> AuthoringDocument:
    """Offer only the repository-root RO-Crate for explicit inclusion review."""
    root = Path(repository_root).resolve()
    source = root / _SOURCE_PATH
    if source.is_symlink() or not source.is_file():
        raise ProvenanceReviewError(_MISSING_MESSAGE)
    document = load_repository_document(root)
    candidate = ProvenanceCandidate(
        id=_CANDIDATE_ID,
        source_path=_SOURCE_PATH,
        evidence_locations=(_SOURCE_PATH,),
    )
    evidence_item = Evidence(
        id=f"{_CANDIDATE_ID}:evidence",
        provenance=EvidenceProvenance(source="ro_crate", location=_SOURCE_PATH),
        observed_value=candidate.model_dump(mode="json"),
        confidence=1.0,
    )
    evidence = {item.id: item for item in document.evidence}
    decisions = {item.id: item for item in document.decisions}
    evidence[evidence_item.id] = evidence_item
    existing = decisions.get(_CANDIDATE_ID)
    if existing is None or existing.status not in {
        DecisionStatus.REVIEWED,
        DecisionStatus.REJECTED,
    }:
        decisions[_CANDIDATE_ID] = Decision(
            id=_CANDIDATE_ID,
            value=candidate.model_dump(mode="json"),
            evidence_ids=(evidence_item.id,),
        )
    decision = decisions[_CANDIDATE_ID]
    unresolved = (
        (
            UnresolvedDecision(
                decision_id=_CANDIDATE_ID,
                reason="Review inclusion of repository-root ro-crate-metadata.json",
            ),
        )
        if decision.status in {DecisionStatus.CANDIDATE, DecisionStatus.CONFLICT}
        else ()
    )
    layer = LayerState(
        name="provenance",
        configured=True,
        decision_ids=(_CANDIDATE_ID,),
        unresolved=unresolved,
    )
    updated = AuthoringDocument(
        schema_version=document.schema_version,
        pipeline=document.pipeline,
        output_contract=document.output_contract,
        evidence=tuple(sorted(evidence.values(), key=lambda item: item.id)),
        decisions=tuple(sorted(decisions.values(), key=lambda item: item.id)),
        layers=_replace_layer(document.layers, layer),
    )
    save_repository_document(root, updated)
    return updated


def unresolved_provenance_candidates(
    document: AuthoringDocument,
) -> tuple[ProvenanceCandidate, ...]:
    """Return the root RO-Crate while it still needs explicit approval."""
    layer = next((item for item in document.layers if item.name == "provenance"), None)
    if layer is None:
        return ()
    decisions = {item.id: item for item in document.decisions}
    decision = decisions.get(_CANDIDATE_ID)
    if decision is None or decision.status not in {
        DecisionStatus.CANDIDATE,
        DecisionStatus.CONFLICT,
    }:
        return ()
    return (ProvenanceCandidate.model_validate(decision.value),)


def review_provenance(
    repository_root: str | Path, candidate_id: str
) -> AuthoringDocument:
    """Approve unchanged inclusion of the root RO-Crate."""
    root = Path(repository_root).resolve()
    document = load_repository_document(root)
    decisions = {item.id: item for item in document.decisions}
    layer = next((item for item in document.layers if item.name == "provenance"), None)
    decision = decisions.get(candidate_id)
    if layer is None or decision is None or candidate_id not in layer.decision_ids:
        raise ProvenanceReviewError(f"unknown provenance candidate {candidate_id!r}")
    candidate = ProvenanceCandidate.model_validate(decision.value)
    reviewed = ReviewedProvenance(
        source_path=candidate.source_path,
        evidence_locations=candidate.evidence_locations,
    )
    decisions[candidate_id] = Decision(
        id=candidate_id,
        status=DecisionStatus.REVIEWED,
        value=reviewed.model_dump(mode="json"),
        evidence_ids=decision.evidence_ids,
    )
    updated = AuthoringDocument(
        schema_version=document.schema_version,
        pipeline=document.pipeline,
        output_contract=document.output_contract,
        evidence=document.evidence,
        decisions=tuple(sorted(decisions.values(), key=lambda item: item.id)),
        layers=_replace_layer(
            document.layers, layer.model_copy(update={"unresolved": ()})
        ),
    )
    save_repository_document(root, updated)
    return updated


def _plan(repository_root: str | Path) -> tuple[StaticLayerBuildResult, bytes]:
    root = Path(repository_root).resolve()
    path = root / "splice" / "ro-crate-metadata.json"
    proposed = render_provenance(load_repository_document(root), root).metadata
    current = path.read_bytes() if path.is_file() else b""
    kind = (
        StaticChangeKind.UNCHANGED
        if current == proposed
        else StaticChangeKind.UPDATE
        if path.exists()
        else StaticChangeKind.CREATE
    )
    relative = "splice/ro-crate-metadata.json"
    diff = (
        ""
        if kind is StaticChangeKind.UNCHANGED
        else "".join(
            difflib.unified_diff(
                current.decode("utf-8", errors="replace").splitlines(keepends=True),
                proposed.decode("utf-8", errors="replace").splitlines(keepends=True),
                fromfile=relative if current else "/dev/null",
                tofile=relative,
            )
        )
    )
    return (
        StaticLayerBuildResult(
            change=StaticLayerChange(path=path, kind=kind, diff=diff),
            wrote=False,
        ),
        proposed,
    )


def plan_provenance(repository_root: str | Path) -> StaticLayerBuildResult:
    """Preview unchanged inclusion of the reviewed root RO-Crate."""
    return _plan(repository_root)[0]


def build_provenance(
    repository_root: str | Path, *, replace_existing: bool = False
) -> StaticLayerBuildResult:
    """Copy the reviewed root RO-Crate with exact-path collision protection."""
    root = Path(repository_root).resolve()
    plan, proposed = _plan(root)
    if plan.change.kind is StaticChangeKind.UNCHANGED:
        return plan
    inspected = inspect_splice_tree(root)
    classification = next(
        (
            item.classification
            for item in inspected.paths
            if item.path == "ro-crate-metadata.json"
        ),
        None,
    )
    if classification is PathClassification.MALFORMED:
        raise ProvenanceReviewError(
            f"refusing to replace malformed recognized artefact: {plan.change.path}"
        )
    if classification is PathClassification.UNKNOWN:
        raise ProvenanceReviewError(
            f"refusing to replace unknown content: {plan.change.path}"
        )
    if classification is PathClassification.RECOGNIZED and not replace_existing:
        raise ProvenanceReviewError(
            "review the displayed provenance diff, then pass --replace-existing"
        )
    temporary = plan.change.path.with_name(".ro-crate-metadata.json.nf-splice.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(proposed)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, plan.change.path)
    finally:
        temporary.unlink(missing_ok=True)
    return StaticLayerBuildResult(change=plan.change, wrote=True)
