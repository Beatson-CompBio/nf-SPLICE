"""Render ``outputs.yaml`` and ``outputs.schema.json`` from one reviewed model.

Both published files are generated from the same in-memory reviewed output
definitions. ``outputs.schema.json`` validates one completed job's
``analysis_output.json`` and embeds the complete ``x-output-catalog`` that
ingestion, DEX and runtime classification read; ``outputs.yaml`` is its
developer-readable companion.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field

import yaml  # type: ignore[import-untyped]
from pydantic import ValidationError

from nf_splice.contracts import OUTPUTS_FAMILY, contract_extension, current_revision
from nf_splice.domain import (
    AuthoringDocument,
    DecisionStatus,
    OutputScope,
    ReviewedOutput,
    expand_output_path_pattern,
)
from nf_splice.domain.identity import derive_pipeline_id

#: Format revision of the developer-readable ``outputs.yaml`` companion.
OUTPUT_CATALOGUE_FORMAT_VERSION = "0.3.0"
SCOPE_DESCRIPTIONS = {
    OutputScope.JOB.value: (
        "Produced once for the whole workflow job and its combined inputs; "
        "attached to the job, never to a platform run."
    ),
    OutputScope.SAMPLE.value: (
        "Produced for one biological or experimental sample, aggregating its "
        "platform runs; records carry sample_id."
    ),
    OutputScope.RUN.value: (
        "Produced for one platform file-level or acquisition-level run belonging "
        "to a sample; records carry run_id and the parent sample_id."
    ),
}


class OutputContractError(ValueError):
    """Raised when reviewed state cannot safely produce output contracts."""


@dataclass(frozen=True, slots=True)
class OutputPipeline:
    """Pipeline identity embedded in the output contract."""

    id: str
    name: str
    version: str
    repository_url: str
    engine: str = "nextflow"
    release_url: str | None = None


@dataclass(frozen=True, slots=True)
class CategoryDetails:
    """Optional per-pipeline display metadata for a free-text category."""

    title: str | None = None
    description: str | None = None


@dataclass(frozen=True, slots=True)
class OutputContractInput:
    """Everything needed to compile both published output files."""

    pipeline: OutputPipeline
    schema_version: str
    outputs: tuple[ReviewedOutput, ...]
    categories: Mapping[str, CategoryDetails] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RenderedOutputContracts:
    """Byte-stable output contract artefacts and their parsed schema."""

    catalogue: str
    schema: str
    schema_document: dict[str, object]


def _sorted_outputs(outputs: tuple[ReviewedOutput, ...]) -> tuple[ReviewedOutput, ...]:
    keys = [item.key for item in outputs]
    if len(keys) != len(set(keys)):
        raise OutputContractError("reviewed output keys must be unique")
    if not outputs:
        raise OutputContractError("the output contract needs at least one output")
    return tuple(sorted(outputs, key=lambda item: (item.category, item.key)))


def _pipeline_document(pipeline: OutputPipeline) -> dict[str, str]:
    rendered = {
        "id": pipeline.id,
        "name": pipeline.name,
        "version": pipeline.version,
        "engine": pipeline.engine,
        "repository_url": pipeline.repository_url,
    }
    return rendered


def schema_identifier(pipeline: OutputPipeline, schema_version: str) -> str:
    """Return the per-pipeline ``$id`` of the runtime instance schema."""
    base = pipeline.repository_url.rstrip("/")
    return f"{base}/schema/analysis-output/v{schema_version}"


def _categories(
    outputs: tuple[ReviewedOutput, ...], details: Mapping[str, CategoryDetails]
) -> list[dict[str, str]]:
    used = sorted({item.category for item in outputs})
    unknown = sorted(set(details) - set(used))
    if unknown:
        raise OutputContractError(
            f"category metadata is defined for unused categories: {', '.join(unknown)}"
        )
    rendered = []
    for category in used:
        entry = {"key": category}
        item = details.get(category, CategoryDetails())
        if item.title:
            entry["title"] = item.title
        if item.description:
            entry["description"] = item.description
        rendered.append(entry)
    return rendered


def _output_document(output: ReviewedOutput) -> dict[str, object]:
    rendered: dict[str, object] = {
        "key": output.key,
        "title": output.title,
        "description": output.description,
        "category": output.category,
        "scope": [item.value for item in output.scopes],
        "entity_type": [item.value for item in output.entity_types],
        "format": [item.value for item in output.formats],
        "path_patterns": list(output.path_patterns),
    }
    if output.stage is not None:
        rendered["stage"] = output.stage
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


_SCOPE_RULES: list[dict[str, object]] = [
    {
        "if": {"properties": {"scope": {"const": "job"}}, "required": ["scope"]},
        "then": {
            "not": {"anyOf": [{"required": ["sample_id"]}, {"required": ["run_id"]}]}
        },
    },
    {
        "if": {"properties": {"scope": {"const": "sample"}}, "required": ["scope"]},
        "then": {"required": ["sample_id"], "not": {"required": ["run_id"]}},
    },
    {
        "if": {"properties": {"scope": {"const": "run"}}, "required": ["scope"]},
        "then": {"required": ["run_id", "sample_id"]},
    },
]


def _schema_document(
    contract: OutputContractInput,
    categories: list[dict[str, str]],
    outputs: tuple[ReviewedOutput, ...],
) -> dict[str, object]:
    pipeline = contract.pipeline
    version = contract.schema_version
    schema_id = schema_identifier(pipeline, version)
    category_one_of = [
        {"const": item["key"]}
        | ({"title": item["title"]} if "title" in item else {})
        | ({"description": item["description"]} if "description" in item else {})
        for item in categories
    ]
    output_one_of = [
        {"const": item.key, "title": item.title, "description": item.description}
        for item in outputs
    ]
    conditions: list[dict[str, object]] = list(_SCOPE_RULES)
    for output in outputs:
        then_properties: dict[str, object] = {
            "category": {"const": output.category},
            "scope": {"enum": [item.value for item in output.scopes]},
            "entity_type": {"enum": [item.value for item in output.entity_types]},
            "format": {"enum": [item.value for item in output.formats]},
            "path": _path_constraint(output.path_patterns),
        }
        if output.stage is not None:
            then_properties["stage"] = {"const": output.stage}
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

    identifier = {"type": "string", "minLength": 1, "pattern": r"^[^/\s]+$"}
    file_properties: dict[str, object] = {
        "path": {
            "type": "string",
            "pattern": r"^(?!/)(?!.*//)(?!.*(?:^|/)\.\.(?:/|$)).+",
            "description": "Relative path from the completed job's publish directory.",
        },
        "category": {"oneOf": category_one_of},
        "output_type": {"oneOf": output_one_of},
        "scope": {
            "type": "string",
            "enum": [item.value for item in OutputScope],
            "description": "Platform granularity owning the record: job, sample, run.",
        },
        "entity_type": {"type": "string", "enum": ["file", "directory"]},
        "format": {"type": "string"},
        "sample_id": identifier
        | {"description": "Sample owning a sample record, or parent of a run record."},
        "run_id": identifier
        | {"description": "Platform file-level run identifier of a run record."},
        "library_id": {
            "type": "string",
            "description": "Optional descriptive library label; never an output scope.",
        },
        "read": {"type": "string"},
        "aligner": {"type": "string"},
        "stage": {"type": "string"},
        "labels": {"type": "object", "additionalProperties": {"type": "string"}},
        "size_bytes": {"type": "integer", "minimum": 0},
        "checksum": {"type": "string"},
        "checksum_algorithm": {"type": "string"},
        "storage_uri": {"type": "string"},
    }
    properties: dict[str, object] = {
        "analysis_output_schema_version": {"type": "string", "const": version},
        "schema_id": {"type": "string", "const": schema_id},
        "pipeline_name": {"type": "string", "const": pipeline.name},
        "pipeline_version": {"type": "string", "const": pipeline.version},
        "repository_url": {"type": "string", "const": pipeline.repository_url},
        "release_url": {"type": "string"},
        "job_id_short": {"type": "string", "pattern": "^[A-Za-z][0-9]{3}$"},
        "job_id_long": {"type": "string", "format": "uuid"},
        "job_metadata": {
            "type": "object",
            "description": (
                "Job-wide metadata. Engine-native identifiers are qualified by "
                "engine and never denote a platform run."
            ),
            "properties": {
                "engine": {"type": "string"},
                "engine_execution_id": {"type": "string"},
                "nextflow": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "run_name": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
                "annotations": {"type": "object"},
            },
            "additionalProperties": False,
        },
        "config_profile": {"type": "string"},
        "publish_directory": {"type": "string"},
        "execution_timestamp": {"type": "string", "format": "date-time"},
        "files": {
            "type": "array",
            "uniqueItems": True,
            "items": {"$ref": "#/definitions/file_record"},
            "description": (
                "Files and directories produced by one completed job at job, sample "
                "or run granularity; absent optional outputs are valid."
            ),
        },
    }
    return {
        "$schema": "https://json-schema.org/draft-07/schema#",
        "$id": schema_id,
        "title": f"SPLICE {pipeline.name} analysis output",
        "description": (
            "Versioned contract for the one analysis_output.json produced by each "
            f"completed {pipeline.name} {pipeline.version} job."
        ),
        "type": "object",
        "required": [
            "analysis_output_schema_version",
            "schema_id",
            "pipeline_name",
            "pipeline_version",
            "files",
        ],
        "anyOf": [{"required": ["job_id_short"]}, {"required": ["job_id_long"]}],
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
        "x-splice-contract": contract_extension(OUTPUTS_FAMILY),
        "x-output-catalog": {
            "catalog_version": current_revision(OUTPUTS_FAMILY),
            "schema_semantics": (
                "The catalogue defines every reviewed output type; each completed "
                "job may contain any produced subset at job, sample or run "
                "granularity."
            ),
            "analysis_output_schema_version": version,
            "pipeline": _pipeline_document(pipeline),
            "scopes": dict(SCOPE_DESCRIPTIONS),
            "categories": {
                item["key"]: {key: value for key, value in item.items() if key != "key"}
                for item in categories
            },
            "output_types": [_output_document(item) for item in outputs],
        },
    }


def render_outputs(contract: OutputContractInput) -> RenderedOutputContracts:
    """Render byte-stable catalogue and schema text from one reviewed model."""
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", contract.schema_version):
        raise OutputContractError("output contract schema_version must be X.Y.Z")
    outputs = _sorted_outputs(contract.outputs)
    categories = _categories(outputs, contract.categories)
    pipeline = contract.pipeline
    catalogue_pipeline: dict[str, str] = {
        "id": pipeline.id,
        "name": pipeline.name,
        "version": pipeline.version,
        "engine": pipeline.engine,
        "repository_url": pipeline.repository_url,
    }
    if pipeline.release_url is not None:
        catalogue_pipeline["release_url"] = pipeline.release_url
    catalogue_document: dict[str, object] = {
        "catalogue_format_version": OUTPUT_CATALOGUE_FORMAT_VERSION,
        "schema_version": contract.schema_version,
        "pipeline": catalogue_pipeline,
        "schema_id": schema_identifier(pipeline, contract.schema_version),
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
    schema_document = _schema_document(contract, categories, outputs)
    schema = json.dumps(schema_document, indent=2, ensure_ascii=False) + "\n"
    return RenderedOutputContracts(
        catalogue=catalogue, schema=schema, schema_document=schema_document
    )


def _reviewed_outputs(document: AuthoringDocument) -> tuple[ReviewedOutput, ...]:
    layer = next((item for item in document.layers if item.name == "outputs"), None)
    if layer is None or not layer.configured:
        raise OutputContractError("output review is not configured")
    if layer.unresolved:
        raise OutputContractError(
            f"output contract is blocked by {len(layer.unresolved)} unresolved "
            "decision(s)"
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
    return tuple(outputs)


def output_contract_input(document: AuthoringDocument) -> OutputContractInput:
    """Adapt reviewed authoring state into the typed output-contract input."""
    outputs = _reviewed_outputs(document)
    if document.output_contract is None:
        raise OutputContractError(
            "output contract version is not reviewed; run configure outputs "
            "--contract-version X.Y.Z"
        )
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
    return OutputContractInput(
        pipeline=OutputPipeline(
            id=derive_pipeline_id(str(pipeline.name)),
            name=str(pipeline.name),
            version=str(pipeline.version),
            repository_url=str(pipeline.repository_url),
            release_url=pipeline.release_url,
        ),
        schema_version=document.output_contract.schema_version,
        outputs=outputs,
    )


def render_output_contracts(document: AuthoringDocument) -> RenderedOutputContracts:
    """Render both output files from reviewed authoring state."""
    return render_outputs(output_contract_input(document))
