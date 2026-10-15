"""Rendering of outputs.yaml and outputs.schema.json from one reviewed model."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from layer_fixtures import ADA, ready_repository
from nf_splice.domain import (
    DEFAULT_JOB_CATEGORY,
    OutputEntityType,
    OutputFormat,
    OutputScope,
    ReviewedOutput,
)
from nf_splice.renderers import (
    CategoryDetails,
    OutputContractError,
    OutputContractInput,
    OutputPipeline,
    render_outputs,
)
from nf_splice.services.lifecycle import LifecycleError, promote

OUTPUTS = (
    ReviewedOutput(
        key="run_report_html",
        title="Run report",
        description="Job-level HTML report.",
        category=DEFAULT_JOB_CATEGORY,
        formats=(OutputFormat.HTML,),
        scopes=(OutputScope.JOB,),
        entity_types=(OutputEntityType.FILE,),
        path_patterns=(r"^reports/report\.html$",),
    ),
    ReviewedOutput(
        key="sample_metrics_json",
        title="Sample metrics",
        description="Per-sample JSON metrics.",
        category="quality_control",
        formats=(OutputFormat.JSON,),
        scopes=(OutputScope.SAMPLE,),
        entity_types=(OutputEntityType.FILE,),
        path_patterns=(r"^metrics/{sample}\.json$",),
    ),
    ReviewedOutput(
        key="sample_quantification",
        title="Sample quantification directory",
        description="Complete per-sample quantification results.",
        category="quantification",
        formats=(OutputFormat.DIRECTORY,),
        scopes=(OutputScope.SAMPLE,),
        entity_types=(OutputEntityType.DIRECTORY,),
        path_patterns=(r"^quant/{sample}$",),
    ),
)
PIPELINE = OutputPipeline(
    id="pipeline",
    name="pipeline",
    version="2.3.4",
    repository_url="https://github.com/org/pipeline",
)


def contract(**changes: object) -> OutputContractInput:
    base = OutputContractInput(
        pipeline=PIPELINE, schema_version="1.2.0", outputs=OUTPUTS
    )
    return dataclasses.replace(base, **changes)  # type: ignore[arg-type]


def test_renderer_is_deterministic_and_catalogue_matches_schema() -> None:
    first = render_outputs(contract())
    second = render_outputs(contract())
    catalogue = yaml.safe_load(first.catalogue)
    schema = json.loads(first.schema)

    assert first == second
    assert catalogue["schema_version"] == "1.2.0"
    assert catalogue["catalogue_format_version"] == "0.3.0"
    assert catalogue["pipeline"]["version"] == "2.3.4"
    assert [item["key"] for item in catalogue["outputs"]] == [
        "run_report_html",
        "sample_metrics_json",
        "sample_quantification",
    ]
    assert schema["x-splice-contract"]["id"] == (
        "https://schemas.splice-data.io/workflow-bundle/outputs"
    )
    catalog = schema["x-output-catalog"]
    assert catalog["analysis_output_schema_version"] == "1.2.0"
    assert set(catalog["scopes"]) == {"job", "sample", "run"}
    assert catalogue["outputs"] == catalog["output_types"]
    assert {item["key"] for item in catalogue["categories"]} == set(
        catalog["categories"]
    )
    constrained = {
        item["if"]["properties"]["output_type"]["const"]: item["then"]["properties"]
        for item in schema["definitions"]["file_record"]["allOf"]
        if "output_type" in item["if"]["properties"]
    }
    for output in catalog["output_types"]:
        assert constrained[output["key"]]["category"]["const"] == output["category"]
        assert constrained[output["key"]]["scope"]["enum"] == output["scope"]
    assert "manifest" not in first.catalogue.lower()
    assert "manifest" not in first.schema.lower()


def test_category_metadata_is_optional_and_must_be_used() -> None:
    rendered = render_outputs(
        contract(categories={"quality_control": CategoryDetails(title="QC")})
    )
    catalog = json.loads(rendered.schema)["x-output-catalog"]
    assert catalog["categories"]["quality_control"] == {"title": "QC"}
    assert catalog["categories"]["quantification"] == {}
    with pytest.raises(OutputContractError, match="unused"):
        render_outputs(contract(categories={"unused": CategoryDetails(title="x")}))


def test_renderer_rejects_invalid_contract_inputs() -> None:
    with pytest.raises(OutputContractError, match=r"X\.Y\.Z"):
        render_outputs(contract(schema_version="1"))
    with pytest.raises(OutputContractError, match="at least one"):
        render_outputs(contract(outputs=()))
    with pytest.raises(OutputContractError, match="unique"):
        render_outputs(contract(outputs=(OUTPUTS[0], OUTPUTS[0])))


def test_malformed_recognized_contract_is_never_overwritten(tmp_path: Path) -> None:
    ready_repository(tmp_path)
    splice = tmp_path / "splice"
    splice.mkdir(exist_ok=True)
    malformed = splice / "outputs.yaml"
    malformed.write_text("outputs: not-a-list\n", encoding="utf-8")
    with pytest.raises(LifecycleError, match="unrecognised content"):
        promote(tmp_path, "outputs", ADA, replace_existing=True)
    assert malformed.read_text(encoding="utf-8") == "outputs: not-a-list\n"
