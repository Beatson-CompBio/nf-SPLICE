"""Discover, review, and safely materialise workflow provenance."""

from __future__ import annotations

import difflib
import os
import subprocess
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
from nf_splice.domain.provenance import (
    ProvenanceCandidate,
    ProvenanceStrategy,
    ReviewedAuthor,
    ReviewedProvenance,
)
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
    """Raised when a provenance choice or source cannot be reviewed safely."""


def _replace_layer(
    layers: tuple[LayerState, ...], replacement: LayerState
) -> tuple[LayerState, ...]:
    retained = [item for item in layers if item.name != replacement.name]
    retained.append(replacement)
    return tuple(sorted(retained, key=lambda item: item.name))


def _source_candidate(
    root: Path, relative: str, strategy: ProvenanceStrategy
) -> tuple[ProvenanceCandidate, Evidence]:
    requested = root / relative
    if requested.is_symlink():
        raise ProvenanceReviewError(
            f"RO-Crate source is not a regular file: {relative}"
        )
    path = requested.resolve()
    try:
        normalized = path.relative_to(root).as_posix()
    except ValueError as error:
        raise ProvenanceReviewError(
            f"RO-Crate source escapes repository: {relative}"
        ) from error
    if not path.is_file():
        raise ProvenanceReviewError(
            f"RO-Crate source is not a regular file: {relative}"
        )
    suffix = normalized.replace("/", "__")
    candidate = ProvenanceCandidate(
        id=f"provenance:{strategy.value}:{suffix}",
        strategy=strategy,
        source_path=normalized,
        evidence_locations=(normalized,),
    )
    evidence = Evidence(
        id=f"{candidate.id}:evidence",
        provenance=EvidenceProvenance(source="ro_crate", location=normalized),
        observed_value=candidate.model_dump(mode="json"),
        confidence=1.0,
    )
    return candidate, evidence


def discover_provenance(
    repository_root: str | Path, *, supplied_file: str | Path | None = None
) -> AuthoringDocument:
    """Persist explicit internal, existing, and optionally supplied strategies."""
    root = Path(repository_root).resolve()
    document = load_repository_document(root)
    internal = ProvenanceCandidate(
        id="provenance:minimal_internal",
        strategy=ProvenanceStrategy.MINIMAL_INTERNAL,
        evidence_locations=("nf-splice:minimal-internal-renderer",),
    )
    internal_evidence = Evidence(
        id="provenance:minimal_internal:evidence",
        provenance=EvidenceProvenance(
            source="nf_splice_renderer",
            location="nf-splice:minimal-internal-renderer",
        ),
        observed_value=internal.model_dump(mode="json"),
        confidence=1.0,
    )
    candidates = [(internal, internal_evidence)]
    for relative in ("ro-crate-metadata.json", "splice/ro-crate-metadata.json"):
        if (root / relative).is_file():
            candidates.append(
                _source_candidate(root, relative, ProvenanceStrategy.NORMALIZE_EXISTING)
            )
    if supplied_file is not None:
        supplied_path = Path(supplied_file)
        if supplied_path.is_absolute():
            try:
                supplied_path = supplied_path.resolve().relative_to(root)
            except ValueError as error:
                raise ProvenanceReviewError(
                    "supplied RO-Crate must be inside the pipeline repository"
                ) from error
        candidates.append(
            _source_candidate(
                root,
                supplied_path.as_posix(),
                ProvenanceStrategy.SUPPLIED_FILE,
            )
        )
    evidence = {item.id: item for item in document.evidence}
    decisions = {item.id: item for item in document.decisions}
    strategy_ids = set()
    for candidate, item_evidence in candidates:
        strategy_ids.add(candidate.id)
        evidence[item_evidence.id] = item_evidence
        existing = decisions.get(candidate.id)
        if existing is not None and existing.status in {
            DecisionStatus.REVIEWED,
            DecisionStatus.REJECTED,
        }:
            continue
        decisions[candidate.id] = Decision(
            id=candidate.id,
            value=candidate.model_dump(mode="json"),
            evidence_ids=(item_evidence.id,),
        )
    unresolved = tuple(
        UnresolvedDecision(
            decision_id=decision_id,
            reason="Select exactly one RO-Crate source strategy",
        )
        for decision_id in sorted(strategy_ids)
        if decisions[decision_id].status
        in {DecisionStatus.CANDIDATE, DecisionStatus.CONFLICT}
    )
    layer = LayerState(
        name="provenance",
        configured=True,
        decision_ids=tuple(sorted(strategy_ids)),
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
    """Return source strategies still awaiting an explicit selection."""
    layer = next((item for item in document.layers if item.name == "provenance"), None)
    if layer is None:
        return ()
    decisions = {item.id: item for item in document.decisions}
    candidates = []
    for decision_id in layer.decision_ids:
        decision = decisions[decision_id]
        if decision.status not in {DecisionStatus.CANDIDATE, DecisionStatus.CONFLICT}:
            continue
        candidate = ProvenanceCandidate.model_validate(decision.value)
        candidates.append(candidate)
    return tuple(sorted(candidates, key=lambda item: item.id))


def _git_revision(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ("git", "-C", str(root), "rev-parse", "HEAD"),
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    revision = result.stdout.strip()
    return revision if result.returncode == 0 and revision else None


def review_provenance(
    repository_root: str | Path,
    candidate_id: str,
    *,
    authors: tuple[ReviewedAuthor, ...],
    licenses: tuple[str, ...],
    published_at: str,
    source_revision: str | None = None,
) -> AuthoringDocument:
    """Select one strategy and persist complete reviewed release metadata."""
    root = Path(repository_root).resolve()
    document = load_repository_document(root)
    decisions = {item.id: item for item in document.decisions}
    layer = next((item for item in document.layers if item.name == "provenance"), None)
    decision = decisions.get(candidate_id)
    if layer is None or decision is None or candidate_id not in layer.decision_ids:
        raise ProvenanceReviewError(f"unknown provenance candidate {candidate_id!r}")
    candidate = ProvenanceCandidate.model_validate(decision.value)
    revision = source_revision or _git_revision(root)
    if revision is None:
        raise ProvenanceReviewError(
            "source revision was not detected; provide it explicitly"
        )
    review = ReviewedProvenance(
        strategy=candidate.strategy,
        source_path=candidate.source_path,
        authors=authors,
        licenses=tuple(sorted(set(item.strip() for item in licenses if item.strip()))),
        published_at=published_at,
        source_revision=revision,
        evidence_locations=candidate.evidence_locations,
    )
    for decision_id in layer.decision_ids:
        current = decisions[decision_id]
        if decision_id == candidate_id:
            decisions[decision_id] = Decision(
                id=decision_id,
                status=DecisionStatus.REVIEWED,
                value=review.model_dump(mode="json"),
                evidence_ids=current.evidence_ids,
            )
        else:
            decisions[decision_id] = Decision(
                id=decision_id,
                status=DecisionStatus.REJECTED,
                value=current.value,
                evidence_ids=current.evidence_ids,
                reason=f"strategy {candidate.strategy.value!r} was selected instead",
            )
    updated_layer = layer.model_copy(update={"unresolved": ()})
    updated = AuthoringDocument(
        schema_version=document.schema_version,
        pipeline=document.pipeline,
        output_contract=document.output_contract,
        evidence=document.evidence,
        decisions=tuple(sorted(decisions.values(), key=lambda item: item.id)),
        layers=_replace_layer(document.layers, updated_layer),
    )
    save_repository_document(root, updated)
    return updated


def _plan(repository_root: str | Path) -> tuple[StaticLayerBuildResult, str]:
    root = Path(repository_root).resolve()
    path = root / "splice" / "ro-crate-metadata.json"
    proposed = render_provenance(load_repository_document(root), root).metadata
    current = path.read_text(encoding="utf-8") if path.is_file() else ""
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
                current.splitlines(keepends=True),
                proposed.splitlines(keepends=True),
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
    """Preview deterministic reviewed RO-Crate metadata without writing."""
    return _plan(repository_root)[0]


def build_provenance(
    repository_root: str | Path, *, replace_existing: bool = False
) -> StaticLayerBuildResult:
    """Write reviewed RO-Crate metadata with exact-path collision protection."""
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
        with temporary.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(proposed)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, plan.change.path)
    finally:
        temporary.unlink(missing_ok=True)
    return StaticLayerBuildResult(change=plan.change, wrote=True)
