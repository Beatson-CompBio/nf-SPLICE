"""Deterministic rendering of reviewed configurable pipeline inputs."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from nf_splice.domain import AuthoringDocument, DecisionStatus, LayerStatus
from nf_splice.domain.inputs import InputClassification, ReviewedInput


class InputProjectionError(ValueError):
    """Raised when reviewed input state is not eligible for rendering."""


@dataclass(frozen=True, slots=True)
class RenderedInputProjection:
    """Byte-stable JSON Schema content for the SPLICE input projection."""

    schema: str


def _reviewed_inputs(document: AuthoringDocument) -> tuple[ReviewedInput, ...]:
    layer = next((item for item in document.layers if item.name == "inputs"), None)
    if layer is None or layer.status is not LayerStatus.READY:
        raise InputProjectionError(
            "input projection is not ready; classify every discovered parameter"
        )
    decisions = {item.id: item for item in document.decisions}
    reviewed: list[ReviewedInput] = []
    for decision_id in layer.decision_ids:
        decision = decisions[decision_id]
        if decision.status is not DecisionStatus.REVIEWED:
            raise InputProjectionError(
                f"input decision {decision_id!r} has not been reviewed"
            )
        try:
            reviewed.append(ReviewedInput.model_validate(decision.value))
        except ValidationError as error:
            raise InputProjectionError(
                f"input decision {decision_id!r} is invalid: {error}"
            ) from error
    return tuple(sorted(reviewed, key=lambda item: (item.group, item.name)))


def render_input_projection(document: AuthoringDocument) -> RenderedInputProjection:
    """Render only explicitly user-configurable parameters into JSON Schema."""
    grouped: dict[str, list[ReviewedInput]] = defaultdict(list)
    for item in _reviewed_inputs(document):
        if item.classification is InputClassification.USER_CONFIGURABLE:
            grouped[item.group].append(item)

    definitions: dict[str, Any] = {}
    for group in sorted(grouped):
        items = grouped[group]
        properties: dict[str, object] = {}
        for item in items:
            fragment = dict(item.schema_fragment)
            fragment.pop("hidden", None)
            properties[item.name] = fragment
        definitions[group] = {
            "title": items[0].group_title,
            "description": items[0].group_description,
            "type": "object",
            "properties": properties,
        }

    repository_url = (document.pipeline.repository_url or "").rstrip("/")
    identifier = (
        f"{repository_url}/splice/inputs.schema.json"
        if repository_url
        else "splice/inputs.schema.json"
    )
    pipeline_name = document.pipeline.name or "Pipeline"
    schema: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": identifier,
        "title": f"{pipeline_name} configurable inputs",
        "description": (
            f"Reviewed parameters configurable when running {pipeline_name} "
            "through the SPLICE platform."
        ),
        "type": "object",
        "$defs": definitions,
        "allOf": [{"$ref": f"#/$defs/{group}"} for group in sorted(definitions)],
        "unevaluatedProperties": False,
    }
    return RenderedInputProjection(
        schema=json.dumps(schema, indent=2, ensure_ascii=False) + "\n"
    )
