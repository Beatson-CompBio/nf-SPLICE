"""Validation and unchanged inclusion of a developer-generated workflow RO-Crate."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from nf_splice.domain import AuthoringDocument, DecisionStatus, LayerStatus
from nf_splice.domain.provenance import ReviewedProvenance


class ProvenanceRenderError(ValueError):
    """Raised when the reviewed repository-root RO-Crate cannot be included."""


@dataclass(frozen=True, slots=True)
class RenderedProvenance:
    """The validated source RO-Crate bytes."""

    metadata: bytes


def _reviewed_provenance(document: AuthoringDocument) -> ReviewedProvenance:
    layer = next((item for item in document.layers if item.name == "provenance"), None)
    if layer is None or layer.status is not LayerStatus.READY:
        raise ProvenanceRenderError(
            "provenance is not ready; review the repository-root RO-Crate"
        )
    decisions = {item.id: item for item in document.decisions}
    reviewed = [
        decisions[item].value
        for item in layer.decision_ids
        if decisions[item].status is DecisionStatus.REVIEWED
    ]
    if len(reviewed) != 1:
        raise ProvenanceRenderError(
            "provenance requires exactly one reviewed repository-root RO-Crate"
        )
    try:
        return ReviewedProvenance.model_validate(reviewed[0])
    except ValidationError as error:
        raise ProvenanceRenderError(
            f"reviewed provenance is invalid: {error}"
        ) from error


def validate_ro_crate(payload: dict[str, Any]) -> None:
    """Validate the structural relationships required of an RO-Crate root file."""
    if "@context" not in payload:
        raise ProvenanceRenderError("RO-Crate must declare an @context")
    graph = payload.get("@graph")
    if not isinstance(graph, list) or not all(isinstance(item, dict) for item in graph):
        raise ProvenanceRenderError("RO-Crate must contain an object @graph")
    identifiers = [item.get("@id") for item in graph]
    if not all(isinstance(item, str) and item for item in identifiers):
        raise ProvenanceRenderError("every RO-Crate graph entity requires an @id")
    if len(identifiers) != len(set(identifiers)):
        raise ProvenanceRenderError("RO-Crate graph entity ids must be unique")
    by_id = {str(item["@id"]): item for item in graph}
    for required in ("ro-crate-metadata.json", "./"):
        if required not in by_id:
            raise ProvenanceRenderError(
                f"RO-Crate is missing required entity {required}"
            )
    metadata = by_id["ro-crate-metadata.json"]
    if metadata.get("about") != {"@id": "./"}:
        raise ProvenanceRenderError("RO-Crate metadata must describe the root dataset")


def render_provenance(
    document: AuthoringDocument, repository_root: str | Path
) -> RenderedProvenance:
    """Validate and return the reviewed root RO-Crate without changing its bytes."""
    root = Path(repository_root).resolve()
    review = _reviewed_provenance(document)
    requested = root / review.source_path
    if requested.is_symlink():
        raise ProvenanceRenderError(
            f"RO-Crate source is not a regular file: {review.source_path}"
        )
    source = requested.resolve()
    try:
        source.relative_to(root)
    except ValueError as error:
        raise ProvenanceRenderError("RO-Crate source escapes the repository") from error
    if not source.is_file():
        raise ProvenanceRenderError(
            f"RO-Crate source is not a regular file: {review.source_path}"
        )
    metadata = source.read_bytes()
    try:
        loaded: object = json.loads(metadata.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ProvenanceRenderError(f"invalid RO-Crate source: {error}") from error
    if not isinstance(loaded, dict):
        raise ProvenanceRenderError("RO-Crate source must be a JSON object")
    validate_ro_crate(loaded)
    return RenderedProvenance(metadata=metadata)
