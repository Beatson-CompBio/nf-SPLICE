"""Render the output catalogue and runtime schema from reviewed state only."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

import yaml  # type: ignore[import-untyped]
from pydantic import ValidationError

from nf_splice.domain import (
    AuthoringDocument,
    DecisionStatus,
    OutputCategory,
    ReviewedOutput,
    expand_output_path_pattern,
)

OUTPUT_VOCABULARY_VERSION = "1.0.0"

_CATEGORY_DETAILS: dict[OutputCategory, tuple[str, str]] = {
    OutputCategory.RUN_REPORT: (
        "Workflow reporting and run metadata",
        "Run-level reports, execution traces, and pipeline metadata.",
    ),
    OutputCategory.SAMPLE_METADATA: (
        "Sample metadata",
        "Samplesheets, sample maps, and other reviewed sample metadata.",
    ),
    OutputCategory.AGGREGATE_QC: (
        "Aggregate quality control",
        "Run-level summaries combining quality-control results.",
    ),
    OutputCategory.QUALITY_CONTROL: (
        "Quality control",
        "Reports and measurements used to assess data quality.",
    ),
    OutputCategory.PREPROCESSING: (
        "Preprocessing",
        "Outputs created while preparing data for primary analysis.",
    ),
    OutputCategory.ALIGNMENT: (
        "Alignment",
        "Aligned reads, indexes, and alignment reports.",
    ),
    OutputCategory.POSTPROCESSING: (
        "Postprocessing",
        "Outputs created by processing primary analysis results.",
    ),
    OutputCategory.COVERAGE: (
        "Coverage",
        "Coverage tracks and related browser-ready files.",
    ),
    OutputCategory.QUANTIFICATION: (
        "Quantification",
        "Per-sample and aggregate abundance measurements.",
    ),
    OutputCategory.UMI: (
        "UMI processing",
        "Unique molecular identifier processing outputs.",
    ),
    OutputCategory.REFERENCE: (
        "Reference files",
        "Reference data materialised by the pipeline run.",
    ),
}


class OutputContractError(ValueError):
    """Raised when reviewed state cannot safely produce output contracts."""


@dataclass(frozen=True, slots=True)
class RenderedOutputContracts:
    """Byte-stable output contract artefacts and their parsed schema."""

    catalogue: str
    schema: str
    schema_document: dict[str, object]


def _reviewed_outputs(document: AuthoringDocument) -> tuple[ReviewedOutput, ...]:
    layer = next((item for item in document.layers if item.name == "outputs"), None)
    if layer is None or not layer.configured:
        raise OutputContractError("output review is not configured")
    if layer.unresolved:
        raise OutputContractError(
            f"output contract is blocked by {len(layer.unresolved)} unresolved "
            "decision(s)"
        )
    if document.output_contract is None:
        raise OutputContractError(
            "output contract version is not reviewed; run configure outputs "
            "--contract-version X.Y.Z"
        )

    decisions = {item.id: item for item in document.decisions}
    outputs: list[ReviewedOutput] = []
    for decision_id in layer.decision_ids:
        decision = decisions[decision_id]
        if decision.status is DecisionStatus.REJECTED:
            continue
        if decision.status is not DecisionStatus.REVIEWED:
            raise OutputContractError(
                f"output decision {decision_id!r} is not reviewed"
            )
        try:
            outputs.append(ReviewedOutput.model_validate(decision.value))
        except ValidationError as error:
            raise OutputContractError(
                f"reviewed output decision {decision_id!r} is invalid: {error}"
            ) from error
    return tuple(sorted(outputs, key=lambda item: (item.category.value, item.key)))


def _pipeline(document: AuthoringDocument) -> dict[str, str]:
    pipeline = document.pipeline
    missing = [
        name
        for name in ("name", "version", "repository_url")
        if getattr(pipeline, name) is None
    ]
    if missing:
        raise OutputContractError(
            f"reviewed pipeline identity is missing: {', '.join(missing)}"
        )
    rendered = {
        "name": str(pipeline.name),
        "version": str(pipeline.version),
        "repository_url": str(pipeline.repository_url),
    }
    if pipeline.release_url is not None:
        rendered["release_url"] = pipeline.release_url
    return rendered


def _schema_id(document: AuthoringDocument) -> str:
    repository_url = str(document.pipeline.repository_url).rstrip("/")
    version = document.output_contract.schema_version  # type: ignore[union-attr]
    return f"{repository_url}/schema/analysis-output/v{version}"


def _category_documents(outputs: tuple[ReviewedOutput, ...]) -> list[dict[str, str]]:
    used = {item.category for item in outputs}
    categories = []
    for category in OutputCategory:
        if category not in used:
            continue
        title, description = _CATEGORY_DETAILS[category]
        categories.append(
            {"key": category.value, "title": title, "description": description}
        )
    return categories


def _output_document(output: ReviewedOutput) -> dict[str, object]:
    rendered: dict[str, object] = {
        "key": output.key,
        "title": output.title,
        "description": output.description,
        "category": output.category.value,
        "scope": [item.value for item in output.scopes],
        "entity_type": [item.value for item in output.entity_types],
        "format": [item.value for item in output.formats],
        "path_patterns": list(output.path_patterns),
    }
    if output.stage is not None:
        rendered["stage"] = output.stage.value
    if output.labels:
        rendered["labels"] = {item.name: item.value for item in output.labels}
    return rendered


def _json_schema_pattern(pattern: str) -> str:
    """Remove Python capture names while retaining the reviewed path constraint."""
    expanded = expand_output_path_pattern(pattern)
    return re.sub(r"\(\?P<[^>]+>", "(?:", expanded)


def _path_constraint(patterns: tuple[str, ...]) -> dict[str, object]:
    expanded = [_json_schema_pattern(item) for item in patterns]
    if len(expanded) == 1:
        return {"pattern": expanded[0]}
    return {"anyOf": [{"pattern": item} for item in expanded]}


def _schema_document(
    document: AuthoringDocument,
    pipeline: dict[str, str],
    categories: list[dict[str, str]],
    outputs: tuple[ReviewedOutput, ...],
) -> dict[str, object]:
    version = document.output_contract.schema_version  # type: ignore[union-attr]
    schema_id = _schema_id(document)
    category_one_of = [
        {
            "const": item["key"],
            "title": item["title"],
            "description": item["description"],
        }
        for item in categories
    ]
    output_one_of = [
        {
            "const": item.key,
            "title": item.title,
            "description": item.description,
        }
        for item in outputs
    ]
    conditions = []
    for output in outputs:
        then_properties: dict[str, object] = {
            "category": {"const": output.category.value},
            "scope": {"enum": [item.value for item in output.scopes]},
            "entity_type": {"enum": [item.value for item in output.entity_types]},
            "format": {"enum": [item.value for item in output.formats]},
            "path": _path_constraint(output.path_patterns),
        }
        if output.stage is not None:
            then_properties["stage"] = {"const": output.stage.value}
        if output.labels:
            then_properties["labels"] = {
                "type": "object",
                "properties": {
                    item.name: {"const": item.value} for item in output.labels
                },
                "required": [item.name for item in output.labels],
            }
        conditions.append(
            {
                "if": {
                    "properties": {"output_type": {"const": output.key}},
                    "required": ["output_type"],
                },
                "then": {"properties": then_properties},
            }
        )

    file_properties: dict[str, object] = {
        "path": {
            "type": "string",
            "pattern": r"^(?!/)(?!.*//)(?!.*(?:^|/)\.\.(?:/|$)).+",
            "description": "Relative path from the completed publish directory.",
        },
        "category": {"oneOf": category_one_of},
        "output_type": {"oneOf": output_one_of},
        "scope": {"type": "string", "enum": ["run", "sample", "library"]},
        "entity_type": {"type": "string", "enum": ["file", "directory"]},
        "format": {"type": "string"},
        "sample_id": {"type": "string"},
        "library_id": {"type": "string"},
        "read": {"type": "string"},
        "aligner": {"type": "string"},
        "stage": {"type": "string"},
        "labels": {
            "type": "object",
            "additionalProperties": {"type": "string"},
        },
        "size_bytes": {"type": "integer", "minimum": 0},
        "checksum": {"type": "string"},
        "checksum_algorithm": {"type": "string"},
        "storage_uri": {"type": "string"},
    }
    properties: dict[str, object] = {
        "analysis_output_schema_version": {
            "type": "string",
            "const": version,
        },
        "schema_id": {"type": "string", "const": schema_id},
        "pipeline_name": {"type": "string", "const": pipeline["name"]},
        "pipeline_version": {"type": "string", "const": pipeline["version"]},
        "repository_url": {"type": "string", "const": pipeline["repository_url"]},
        "release_url": {"type": "string"},
        "job_id_short": {"type": "string", "pattern": "^[A-Za-z][0-9]{3}$"},
        "job_id_long": {"type": "string", "format": "uuid"},
        "platform_run_id": {"type": "string"},
        "workflow_run_id": {"type": "string"},
        "nextflow_session_id": {"type": "string"},
        "nextflow_run_name": {"type": "string"},
        "config_profile": {"type": "string"},
        "publish_directory": {"type": "string"},
        "execution_timestamp": {"type": "string", "format": "date-time"},
        "run_metadata": {"type": "object", "additionalProperties": True},
        "files": {
            "type": "array",
            "uniqueItems": True,
            "items": {"$ref": "#/definitions/file_record"},
            "description": (
                "Files and directories produced by one completed run; absent optional "
                "outputs are valid."
            ),
        },
    }
    return {
        "$schema": "https://json-schema.org/draft-07/schema#",
        "$id": schema_id,
        "title": f"SPLICE {pipeline['name']} analysis output",
        "description": (
            "Versioned contract for analysis_output.json files produced by "
            f"{pipeline['name']} {pipeline['version']}."
        ),
        "type": "object",
        "required": ["files"],
        "properties": properties,
        "additionalProperties": False,
        "definitions": {
            "file_record": {
                "type": "object",
                "required": [
                    "path",
                    "category",
                    "output_type",
                    "scope",
                    "entity_type",
                    "format",
                ],
                "additionalProperties": False,
                "properties": file_properties,
                "allOf": conditions,
            }
        },
        "x-output-catalog": {
            "schema_semantics": (
                "The catalogue defines every reviewed output type; each completed run "
                "may contain any produced subset."
            ),
            "categories": {
                item["key"]: {
                    "title": item["title"],
                    "description": item["description"],
                }
                for item in categories
            },
            "output_types": [_output_document(item) for item in outputs],
        },
    }


def render_output_contracts(document: AuthoringDocument) -> RenderedOutputContracts:
    """Render byte-stable catalogue and schema text from reviewed state."""
    outputs = _reviewed_outputs(document)
    pipeline = _pipeline(document)
    categories = _category_documents(outputs)
    catalogue_document: dict[str, object] = {
        "schema_version": document.output_contract.schema_version,  # type: ignore[union-attr]
        "vocabulary_version": OUTPUT_VOCABULARY_VERSION,
        "pipeline": pipeline,
        "schema_id": _schema_id(document),
        "categories": categories,
        "outputs": [_output_document(item) for item in outputs],
    }
    catalogue = yaml.safe_dump(
        catalogue_document,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=88,
    )
    schema_document = _schema_document(document, pipeline, categories, outputs)
    schema = json.dumps(schema_document, indent=2, ensure_ascii=False) + "\n"
    return RenderedOutputContracts(
        catalogue=catalogue,
        schema=schema,
        schema_document=schema_document,
    )
