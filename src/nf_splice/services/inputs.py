"""Discover, review, and persist pipeline input classifications."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from pydantic import JsonValue, ValidationError

from nf_splice.domain import (
    AuthoringDocument,
    Decision,
    DecisionStatus,
    Evidence,
    EvidenceProvenance,
    InputCandidate,
    InputClassification,
    LayerState,
    ReviewedInput,
    UnresolvedDecision,
)
from nf_splice.services.authoring import (
    AuthoringOperationError,
    load_repository_document,
    save_repository_document,
)


class InputReviewError(ValueError):
    """Raised when input discovery or classification is incomplete or invalid."""


def _replace_layer(
    layers: tuple[LayerState, ...], replacement: LayerState
) -> tuple[LayerState, ...]:
    retained = [item for item in layers if item.name != replacement.name]
    retained.append(replacement)
    return tuple(sorted(retained, key=lambda item: item.name))


def _schema_parameters(
    root: Path,
) -> tuple[tuple[InputCandidate, Evidence], ...]:
    path = root / "nextflow_schema.json"
    if not path.is_file():
        raise InputReviewError(
            "nextflow_schema.json is required to discover pipeline parameters"
        )
    try:
        loaded: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise InputReviewError(f"invalid nextflow_schema.json: {error}") from error
    if not isinstance(loaded, dict):
        raise InputReviewError("nextflow_schema.json must contain a JSON object")

    groups: list[tuple[str, dict[str, object]]] = []
    definitions = loaded.get("$defs", loaded.get("definitions", {}))
    if isinstance(definitions, dict):
        groups.extend(
            (str(name), value)
            for name, value in definitions.items()
            if isinstance(value, dict)
        )
    root_properties = loaded.get("properties")
    if isinstance(root_properties, dict):
        groups.append(
            (
                "inputs",
                {
                    "title": "Inputs",
                    "description": str(loaded.get("description", "")),
                    "properties": root_properties,
                },
            )
        )

    discovered: list[tuple[InputCandidate, Evidence]] = []
    for group, definition in sorted(groups):
        properties = definition.get("properties")
        if not isinstance(properties, dict):
            continue
        title = definition.get("title")
        group_title = title if isinstance(title, str) and title else group
        description = definition.get("description")
        group_description = description if isinstance(description, str) else ""
        for name, raw_fragment in sorted(properties.items()):
            if not isinstance(raw_fragment, dict):
                continue
            fragment = {
                str(key): value
                for key, value in raw_fragment.items()
                if isinstance(key, str)
            }
            json_fragment = cast(dict[str, JsonValue], fragment)
            unresolved = ["classification"]
            if not isinstance(fragment.get("type"), str):
                unresolved.append("type")
            if (
                not isinstance(fragment.get("description"), str)
                or not str(fragment.get("description", "")).strip()
            ):
                unresolved.append("description")
            candidate = InputCandidate(
                id=f"input:{name}",
                name=name,
                group=group,
                group_title=group_title,
                group_description=group_description,
                schema_fragment=json_fragment,
                unresolved_fields=tuple(unresolved),
            )
            evidence_id = f"input-schema:{group}:{name}"
            evidence = Evidence(
                id=evidence_id,
                provenance=EvidenceProvenance(
                    source="nextflow_schema",
                    location=(f"nextflow_schema.json#/$defs/{group}/properties/{name}"),
                ),
                observed_value=raw_fragment,
                confidence=1.0,
            )
            discovered.append((candidate, evidence))
    return tuple(discovered)


def discover_inputs(repository_root: str | Path) -> AuthoringDocument:
    """Persist upstream parameters as unresolved candidates without guessing."""
    root = Path(repository_root).resolve()
    document = load_repository_document(root)
    evidence = {item.id: item for item in document.evidence}
    decisions = {item.id: item for item in document.decisions}
    input_ids: set[str] = set()
    seen_candidates: dict[str, InputCandidate] = {}

    for candidate, item_evidence in _schema_parameters(root):
        evidence[item_evidence.id] = item_evidence
        input_ids.add(candidate.id)
        existing_candidate = seen_candidates.get(candidate.id)
        existing = decisions.get(candidate.id)
        if existing is not None and existing.status in {
            DecisionStatus.REVIEWED,
            DecisionStatus.REJECTED,
        }:
            seen_candidates[candidate.id] = candidate
            continue
        if existing_candidate is not None and (
            existing_candidate.schema_fragment != candidate.schema_fragment
            or existing_candidate.group != candidate.group
        ):
            decisions[candidate.id] = Decision(
                id=candidate.id,
                status=DecisionStatus.CONFLICT,
                value=candidate.model_dump(mode="json"),
                evidence_ids=tuple(
                    sorted(
                        set(existing.evidence_ids if existing else ())
                        | {item_evidence.id}
                    )
                ),
                reason="parameter is defined differently in more than one schema group",
            )
            continue
        seen_candidates[candidate.id] = candidate
        decisions[candidate.id] = Decision(
            id=candidate.id,
            value=candidate.model_dump(mode="json"),
            evidence_ids=tuple(
                sorted(
                    set(existing.evidence_ids if existing else ()) | {item_evidence.id}
                )
            ),
        )

    unresolved = tuple(
        UnresolvedDecision(
            decision_id=decision_id,
            reason="Parameter ownership requires explicit classification",
        )
        for decision_id in sorted(input_ids)
        if decisions[decision_id].status
        in {DecisionStatus.CANDIDATE, DecisionStatus.CONFLICT}
    )
    layer = LayerState(
        name="inputs",
        configured=True,
        decision_ids=tuple(sorted(input_ids)),
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


def unresolved_input_candidates(
    document: AuthoringDocument,
) -> tuple[InputCandidate, ...]:
    """Return parameter candidates still requiring classification."""
    layer = next((item for item in document.layers if item.name == "inputs"), None)
    if layer is None:
        return ()
    decisions = {item.id: item for item in document.decisions}
    result: list[InputCandidate] = []
    for decision_id in layer.decision_ids:
        decision = decisions[decision_id]
        if decision.status not in {DecisionStatus.CANDIDATE, DecisionStatus.CONFLICT}:
            continue
        try:
            result.append(InputCandidate.model_validate(decision.value))
        except ValidationError:
            continue
    return tuple(sorted(result, key=lambda item: (item.group, item.name)))


def review_input(
    repository_root: str | Path,
    candidate_id: str,
    classification: InputClassification | str,
    *,
    type_override: str | None = None,
    description_override: str | None = None,
) -> AuthoringDocument:
    """Apply one explicit input classification through shared transition rules."""
    root = Path(repository_root).resolve()
    document = load_repository_document(root)
    decisions = {item.id: item for item in document.decisions}
    decision = decisions.get(candidate_id)
    if decision is None:
        raise InputReviewError(f"unknown input candidate {candidate_id!r}")
    try:
        candidate = InputCandidate.model_validate(decision.value)
        selected_classification = InputClassification(classification)
    except (ValidationError, ValueError) as error:
        raise InputReviewError(str(error)) from error
    fragment: dict[str, Any] = dict(candidate.schema_fragment)
    if type_override is not None:
        fragment["type"] = type_override
    if description_override is not None:
        fragment["description"] = description_override
    try:
        reviewed = ReviewedInput(
            name=candidate.name,
            group=candidate.group,
            group_title=candidate.group_title,
            group_description=candidate.group_description,
            classification=selected_classification,
            schema_fragment=fragment,
        )
    except ValidationError as error:
        raise InputReviewError(str(error)) from error
    decisions[candidate_id] = Decision(
        id=candidate_id,
        status=DecisionStatus.REVIEWED,
        value=reviewed.model_dump(mode="json"),
        evidence_ids=decision.evidence_ids,
    )
    layer = next((item for item in document.layers if item.name == "inputs"), None)
    if layer is None or candidate_id not in layer.decision_ids:
        raise AuthoringOperationError(f"{candidate_id!r} is not in the input layer")
    replacement = layer.model_copy(
        update={
            "unresolved": tuple(
                item for item in layer.unresolved if item.decision_id != candidate_id
            )
        }
    )
    updated = AuthoringDocument(
        schema_version=document.schema_version,
        pipeline=document.pipeline,
        output_contract=document.output_contract,
        evidence=document.evidence,
        decisions=tuple(sorted(decisions.values(), key=lambda item: item.id)),
        layers=_replace_layer(document.layers, replacement),
    )
    save_repository_document(root, updated)
    return updated
