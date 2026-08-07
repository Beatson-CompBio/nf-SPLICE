"""Deterministic rendering of reviewed software and container inventory."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from nf_splice.domain import AuthoringDocument, DecisionStatus, LayerStatus
from nf_splice.domain.components import ReviewedComponent


class ComponentInventoryError(ValueError):
    """Raised when component state is not eligible for rendering."""


@dataclass(frozen=True, slots=True)
class RenderedComponentInventory:
    """Byte-stable component inventory JSON."""

    inventory: str


def _reviewed_components(
    document: AuthoringDocument,
) -> tuple[ReviewedComponent, ...]:
    layer = next((item for item in document.layers if item.name == "components"), None)
    if layer is None or layer.status is not LayerStatus.READY:
        raise ComponentInventoryError(
            "component inventory is not ready; review every detected component"
        )
    decisions = {item.id: item for item in document.decisions}
    reviewed: list[ReviewedComponent] = []
    for decision_id in layer.decision_ids:
        decision = decisions[decision_id]
        if decision.status is not DecisionStatus.REVIEWED:
            raise ComponentInventoryError(
                f"component decision {decision_id!r} has not been reviewed"
            )
        try:
            reviewed.append(ReviewedComponent.model_validate(decision.value))
        except ValidationError as error:
            raise ComponentInventoryError(
                f"component decision {decision_id!r} is invalid: {error}"
            ) from error
    return tuple(sorted(reviewed, key=lambda item: item.id))


def _container_id(uri: str) -> str:
    digest = hashlib.sha256(uri.encode("utf-8")).hexdigest()[:12]
    return f"container-{digest}"


def _container_type(uri: str) -> str:
    if uri.startswith("oras://"):
        return "oras"
    if uri.startswith("docker://"):
        return "docker"
    if "depot.galaxyproject.org/singularity/" in uri or uri.endswith(".sif"):
        return "singularity"
    return "docker"


def render_component_inventory(
    document: AuthoringDocument,
) -> RenderedComponentInventory:
    """Render reviewed components with deterministic container deduplication."""
    reviewed = _reviewed_components(document)
    uris = sorted(
        {item.container_uri for item in reviewed if item.container_uri is not None}
    )
    containers = [
        {"id": _container_id(uri), "type": _container_type(uri), "uri": uri}
        for uri in uris
    ]
    components: list[dict[str, Any]] = []
    for item in reviewed:
        tool: dict[str, str] = {"name": item.tool_name}
        if item.version is not None:
            tool["version"] = item.version
        component: dict[str, Any] = {
            "id": item.id.removeprefix("component:"),
            "type": "workflow_module",
            "name": item.name,
            "path": item.path,
            "namespace": item.namespace,
            "tool": tool,
            "evidence": list(item.evidence_locations),
        }
        if item.container_uri is not None:
            component["container_id"] = _container_id(item.container_uri)
        if item.conda_packages:
            component["conda_packages"] = list(item.conda_packages)
        components.append(component)
    content = {
        "schema_version": "1.0",
        "pipeline": {
            "id": document.pipeline.name,
            "version": document.pipeline.version,
        },
        "containers": containers,
        "components": components,
    }
    return RenderedComponentInventory(
        inventory=json.dumps(content, indent=2, ensure_ascii=False) + "\n"
    )
