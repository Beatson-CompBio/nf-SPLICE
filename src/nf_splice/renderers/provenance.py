"""Deterministic generation and normalization of workflow RO-Crate metadata."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from nf_splice.domain import AuthoringDocument, DecisionStatus, LayerStatus
from nf_splice.domain.components import ReviewedComponent
from nf_splice.domain.provenance import (
    ProvenanceStrategy,
    ReviewedAuthor,
    ReviewedProvenance,
)


class ProvenanceRenderError(ValueError):
    """Raised when reviewed provenance cannot form a valid deterministic crate."""


@dataclass(frozen=True, slots=True)
class RenderedProvenance:
    """Byte-stable RO-Crate metadata JSON."""

    metadata: str


def _reviewed_provenance(document: AuthoringDocument) -> ReviewedProvenance:
    layer = next((item for item in document.layers if item.name == "provenance"), None)
    if layer is None or layer.status is not LayerStatus.READY:
        raise ProvenanceRenderError(
            "provenance is not ready; select and review one RO-Crate strategy"
        )
    decisions = {item.id: item for item in document.decisions}
    reviewed = [
        decisions[item].value
        for item in layer.decision_ids
        if decisions[item].status is DecisionStatus.REVIEWED
    ]
    if len(reviewed) != 1:
        raise ProvenanceRenderError(
            "provenance requires exactly one reviewed source strategy"
        )
    try:
        return ReviewedProvenance.model_validate(reviewed[0])
    except ValidationError as error:
        raise ProvenanceRenderError(
            f"reviewed provenance is invalid: {error}"
        ) from error


def _reviewed_components(document: AuthoringDocument) -> tuple[ReviewedComponent, ...]:
    layer = next((item for item in document.layers if item.name == "components"), None)
    if layer is None or layer.status is not LayerStatus.READY:
        raise ProvenanceRenderError(
            "RO-Crate generation requires the reviewed component layer"
        )
    decisions = {item.id: item for item in document.decisions}
    reviewed = []
    for decision_id in layer.decision_ids:
        decision = decisions[decision_id]
        if decision.status is not DecisionStatus.REVIEWED:
            raise ProvenanceRenderError(
                f"component decision {decision_id!r} is not reviewed"
            )
        try:
            reviewed.append(ReviewedComponent.model_validate(decision.value))
        except ValidationError as error:
            raise ProvenanceRenderError(
                f"component decision {decision_id!r} is invalid: {error}"
            ) from error
    return tuple(sorted(reviewed, key=lambda item: item.id))


def _source_graph(root: Path, review: ReviewedProvenance) -> list[dict[str, Any]]:
    if review.strategy is ProvenanceStrategy.MINIMAL_INTERNAL:
        return []
    if review.source_path is None:
        raise ProvenanceRenderError("selected provenance strategy requires a source")
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
    try:
        loaded: object = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProvenanceRenderError(f"invalid RO-Crate source: {error}") from error
    if not isinstance(loaded, dict) or not isinstance(loaded.get("@graph"), list):
        raise ProvenanceRenderError("RO-Crate source must contain an @graph array")
    if not all(isinstance(item, dict) for item in loaded["@graph"]):
        raise ProvenanceRenderError("RO-Crate @graph entries must be objects")
    return list(loaded["@graph"])


def _author_id(author: ReviewedAuthor) -> str:
    if author.identifier is not None:
        return author.identifier
    slug = re.sub(r"[^a-z0-9]+", "-", author.name.lower()).strip("-") or "author"
    digest = hashlib.sha256(author.name.encode("utf-8")).hexdigest()[:8]
    return f"#author-{slug}-{digest}"


def _component_id(component: ReviewedComponent) -> str:
    digest = hashlib.sha256(component.id.encode("utf-8")).hexdigest()[:12]
    return f"#component-{digest}"


def _crate_graph(
    document: AuthoringDocument,
    review: ReviewedProvenance,
    components: tuple[ReviewedComponent, ...],
    source_graph: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    author_nodes = [
        {
            "@id": _author_id(author),
            "@type": "Person",
            "name": author.name,
        }
        for author in review.authors
    ]
    component_nodes = []
    for component in components:
        node: dict[str, Any] = {
            "@id": _component_id(component),
            "@type": "SoftwareApplication",
            "name": component.tool_name,
        }
        if component.version is not None:
            node["version"] = component.version
        if component.container_uri is not None:
            node["softwareRequirements"] = component.container_uri
        component_nodes.append(node)

    metadata = {
        "@id": "ro-crate-metadata.json",
        "@type": "CreativeWork",
        "about": {"@id": "./"},
        "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"},
    }
    root: dict[str, Any] = {
        "@id": "./",
        "@type": "Dataset",
        "name": document.pipeline.name,
        "version": document.pipeline.version,
        "isBasedOn": document.pipeline.repository_url,
        "datePublished": review.published_at,
        "identifier": review.source_revision,
        "license": [{"@id": item} for item in review.licenses],
        "creator": [{"@id": _author_id(item)} for item in review.authors],
        "mainEntity": {"@id": "main.nf"},
        "hasPart": [
            {"@id": "main.nf"},
            {"@id": "components.json"},
            *({"@id": _component_id(item)} for item in components),
        ],
    }
    if document.pipeline.release_url is not None:
        root["url"] = document.pipeline.release_url
    workflow: dict[str, Any] = {
        "@id": "main.nf",
        "@type": ["File", "SoftwareSourceCode", "ComputationalWorkflow"],
        "name": document.pipeline.name,
        "version": document.pipeline.version,
        "url": document.pipeline.repository_url,
        "programmingLanguage": {
            "@id": "https://w3id.org/workflowhub/workflow-ro-crate#nextflow"
        },
        "softwareRequirements": [{"@id": _component_id(item)} for item in components],
    }
    components_index = {
        "@id": "components.json",
        "@type": "File",
        "name": "Reviewed workflow software inventory",
    }
    owned_ids = {
        "ro-crate-metadata.json",
        "./",
        "main.nf",
        "components.json",
        *(_author_id(item) for item in review.authors),
        *(_component_id(item) for item in components),
    }
    preserved = [
        item
        for item in source_graph
        if isinstance(item.get("@id"), str) and item["@id"] not in owned_ids
    ]
    preserved.sort(key=lambda item: str(item["@id"]))
    author_nodes.sort(key=lambda item: str(item["@id"]))
    component_nodes.sort(key=lambda item: str(item["@id"]))
    return [
        metadata,
        root,
        workflow,
        components_index,
        *author_nodes,
        *component_nodes,
        *preserved,
    ]


def validate_ro_crate(payload: dict[str, Any]) -> None:
    """Validate the agreed deterministic workflow RO-Crate relationship contract."""
    context = payload.get("@context")
    if context != "https://w3id.org/ro/crate/1.1/context":
        raise ProvenanceRenderError("RO-Crate must use the 1.1 context")
    graph = payload.get("@graph")
    if not isinstance(graph, list) or not all(isinstance(item, dict) for item in graph):
        raise ProvenanceRenderError("RO-Crate must contain an object @graph")
    identifiers = [item.get("@id") for item in graph]
    if not all(isinstance(item, str) and item for item in identifiers):
        raise ProvenanceRenderError("every RO-Crate graph entity requires an @id")
    if len(identifiers) != len(set(identifiers)):
        raise ProvenanceRenderError("RO-Crate graph entity ids must be unique")
    by_id = {str(item["@id"]): item for item in graph}
    for required in ("ro-crate-metadata.json", "./", "main.nf", "components.json"):
        if required not in by_id:
            raise ProvenanceRenderError(
                f"RO-Crate is missing required entity {required}"
            )
    metadata = by_id["ro-crate-metadata.json"]
    root = by_id["./"]
    if metadata.get("about") != {"@id": "./"}:
        raise ProvenanceRenderError("RO-Crate metadata must describe the root dataset")
    if root.get("mainEntity") != {"@id": "main.nf"}:
        raise ProvenanceRenderError("RO-Crate root must identify main.nf")
    for field in ("name", "version", "isBasedOn", "datePublished", "identifier"):
        if not root.get(field):
            raise ProvenanceRenderError(f"RO-Crate root is missing reviewed {field}")
    for field in ("creator", "license"):
        values = root.get(field)
        if not isinstance(values, list) or not values:
            raise ProvenanceRenderError(f"RO-Crate root requires reviewed {field}")
    references: list[str] = []
    for item in graph:
        for field in (
            "about",
            "creator",
            "hasPart",
            "mainEntity",
            "softwareRequirements",
        ):
            value = item.get(field)
            values = value if isinstance(value, list) else [value]
            references.extend(
                ref["@id"]
                for ref in values
                if isinstance(ref, dict) and isinstance(ref.get("@id"), str)
            )
    missing = sorted(
        reference
        for reference in references
        if not reference.startswith(("http://", "https://")) and reference not in by_id
    )
    if missing:
        raise ProvenanceRenderError(
            "RO-Crate contains unresolved local references: " + ", ".join(missing)
        )


def render_provenance(
    document: AuthoringDocument, repository_root: str | Path
) -> RenderedProvenance:
    """Render or normalize one reviewed workflow RO-Crate strategy."""
    root = Path(repository_root).resolve()
    review = _reviewed_provenance(document)
    components = _reviewed_components(document)
    payload = {
        "@context": "https://w3id.org/ro/crate/1.1/context",
        "@graph": _crate_graph(
            document,
            review,
            components,
            _source_graph(root, review),
        ),
    }
    validate_ro_crate(payload)
    return RenderedProvenance(
        metadata=json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    )
