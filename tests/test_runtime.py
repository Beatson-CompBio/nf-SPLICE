"""Acceptance tests for per-run analysis_output.json generation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nf_splice.domain import (
    AuthoringDocument,
    Decision,
    DecisionStatus,
    LayerState,
    OutputCategory,
    OutputContractSettings,
    OutputEntityType,
    OutputFormat,
    OutputScope,
    PipelineIdentity,
    ReviewedOutput,
    dump_authoring_document,
)
from nf_splice.runtime import (
    ANALYSIS_OUTPUT_FILENAME,
    AnalysisOutputError,
    generate_analysis_output,
    load_and_validate_analysis_output,
)
from nf_splice.services import build_output_contracts


def _reviewed_document() -> AuthoringDocument:
    outputs = (
        ReviewedOutput(
            key="run_report_html",
            title="Run report",
            description="Run-level HTML report.",
            category=OutputCategory.RUN_REPORT,
            formats=(OutputFormat.HTML,),
            scopes=(OutputScope.RUN,),
            entity_types=(OutputEntityType.FILE,),
            path_patterns=(r"^reports/report\.html$",),
        ),
        ReviewedOutput(
            key="sample_metrics_json",
            title="Sample metrics",
            description="Per-sample JSON metrics.",
            category=OutputCategory.QUALITY_CONTROL,
            formats=(OutputFormat.JSON,),
            scopes=(OutputScope.SAMPLE,),
            entity_types=(OutputEntityType.FILE,),
            path_patterns=(r"^metrics/{sample}\.json$",),
        ),
        ReviewedOutput(
            key="sample_quantification",
            title="Sample quantification directory",
            description="Complete per-sample quantification results.",
            category=OutputCategory.QUANTIFICATION,
            formats=(OutputFormat.DIRECTORY,),
            scopes=(OutputScope.SAMPLE,),
            entity_types=(OutputEntityType.DIRECTORY,),
            path_patterns=(r"^quant/{sample}$",),
        ),
    )
    decisions = tuple(
        Decision(
            id=f"output:{index}",
            status=DecisionStatus.REVIEWED,
            value=output.model_dump(mode="json"),
        )
        for index, output in enumerate(outputs)
    )
    return AuthoringDocument(
        pipeline=PipelineIdentity(
            name="pipeline",
            version="2.3.4",
            repository_url="https://github.com/org/pipeline",
        ),
        output_contract=OutputContractSettings(schema_version="1.2.0"),
        decisions=decisions,
        layers=(
            LayerState(
                name="outputs",
                configured=True,
                decision_ids=tuple(item.id for item in decisions),
            ),
        ),
    )


def _contracts(root: Path) -> bytes:
    (root / "nf-splice.yaml").write_text(
        dump_authoring_document(_reviewed_document()), encoding="utf-8"
    )
    authoring = (root / "nf-splice.yaml").read_bytes()
    build_output_contracts(root)
    return authoring


def _publish_directory(root: Path) -> Path:
    publish = root / "published"
    (publish / "reports").mkdir(parents=True)
    (publish / "metrics").mkdir()
    (publish / "quant" / "S1").mkdir(parents=True)
    (publish / "reports" / "report.html").write_text("<html/>\n", encoding="utf-8")
    (publish / "metrics" / "S1.json").write_text("{}\n", encoding="utf-8")
    (publish / "quant" / "S1" / "quant.sf").write_text(
        "Name\tLength\n", encoding="utf-8"
    )
    return publish


def test_publish_directory_generates_valid_inventory_without_static_mutation(
    tmp_path: Path,
) -> None:
    original_authoring = _contracts(tmp_path)
    contract_bytes = {
        path.name: path.read_bytes() for path in (tmp_path / "splice").iterdir()
    }
    publish = _publish_directory(tmp_path)
    samples = tmp_path / "samples.csv"
    samples.write_text("sample\nS1\n", encoding="utf-8")
    run_metadata = {
        "job_id_short": "A123",
        "execution_timestamp": "2026-08-07T12:00:00Z",
        "instrument": "NovaSeq",
    }

    result = generate_analysis_output(
        tmp_path,
        publish_directory=publish,
        sample_metadata=samples,
        run_metadata=run_metadata,
        checksum_algorithm="sha256",
        output_directory=publish,
    )

    assert result.validation.valid
    assert result.path == publish / ANALYSIS_OUTPUT_FILENAME
    assert result.unclassified == ()
    assert [item["path"] for item in result.document["files"]] == [
        "metrics/S1.json",
        "quant/S1",
        "reports/report.html",
    ]
    by_path = {item["path"]: item for item in result.document["files"]}
    assert by_path["metrics/S1.json"]["sample_id"] == "S1"
    assert by_path["quant/S1"]["entity_type"] == "directory"
    assert "checksum" in by_path["reports/report.html"]
    assert result.document["run_metadata"] == {"instrument": "NovaSeq"}
    assert (tmp_path / "nf-splice.yaml").read_bytes() == original_authoring
    assert {
        path.name: path.read_bytes() for path in (tmp_path / "splice").iterdir()
    } == contract_bytes

    repeated = generate_analysis_output(
        tmp_path,
        publish_directory=publish,
        sample_metadata=samples,
        run_metadata=run_metadata,
        checksum_algorithm="sha256",
    )
    assert repeated.content == result.content


def test_optional_outputs_may_be_absent_and_unclassified_outputs_are_explicit(
    tmp_path: Path,
) -> None:
    _contracts(tmp_path)
    publish = tmp_path / "published"
    (publish / "reports").mkdir(parents=True)
    (publish / "reports" / "report.html").write_text("ok\n", encoding="utf-8")

    optional = generate_analysis_output(tmp_path, publish_directory=publish)
    assert [item["output_type"] for item in optional.document["files"]] == [
        "run_report_html"
    ]

    (publish / "unexpected.txt").write_text("preserve\n", encoding="utf-8")
    with pytest.raises(
        AnalysisOutputError, match="not in the reviewed output contract"
    ):
        generate_analysis_output(tmp_path, publish_directory=publish)

    allowed = generate_analysis_output(
        tmp_path, publish_directory=publish, allow_unclassified=True
    )
    assert allowed.unclassified == ("unexpected.txt",)
    assert [item["output_type"] for item in allowed.document["files"]] == [
        "run_report_html"
    ]


@pytest.mark.parametrize("source_kind", ["native", "tree"])
def test_runtime_can_use_completed_output_indexes(
    tmp_path: Path, source_kind: str
) -> None:
    _contracts(tmp_path)
    if source_kind == "native":
        source = tmp_path / "outputs.json"
        source.write_text(
            json.dumps(
                {
                    "outputs": [
                        {"path": "reports/report.html", "type": "file"},
                        {"path": "metrics/S2.json", "type": "file"},
                    ]
                }
            ),
            encoding="utf-8",
        )
        result = generate_analysis_output(tmp_path, native_output_index=source)
    else:
        source = tmp_path / "outputs.tree.txt"
        source.write_text(
            ".:\nreports\nmetrics\n\n./reports:\nreport.html\n\n./metrics:\nS2.json\n",
            encoding="utf-8",
        )
        result = generate_analysis_output(tmp_path, output_tree=source)

    assert result.validation.valid
    assert [item["path"] for item in result.document["files"]] == [
        "metrics/S2.json",
        "reports/report.html",
    ]


def test_invalid_existing_analysis_output_is_rejected(tmp_path: Path) -> None:
    _contracts(tmp_path)
    publish = _publish_directory(tmp_path)
    valid = generate_analysis_output(
        tmp_path, publish_directory=publish, allow_unclassified=True
    ).document
    invalid = json.loads(json.dumps(valid))
    invalid["files"][0]["category"] = "run_report"
    path = tmp_path / ANALYSIS_OUTPUT_FILENAME
    path.write_text(json.dumps(invalid), encoding="utf-8")

    report = load_and_validate_analysis_output(tmp_path, path)

    assert not report.valid
    assert any(item.json_pointer.startswith("/files/0") for item in report.issues)


def test_sample_metadata_rejects_unknown_captured_sample(tmp_path: Path) -> None:
    _contracts(tmp_path)
    publish = _publish_directory(tmp_path)
    samples = tmp_path / "samples.csv"
    samples.write_text("sample\nOTHER\n", encoding="utf-8")

    with pytest.raises(AnalysisOutputError, match="unknown sample 'S1'"):
        generate_analysis_output(
            tmp_path,
            publish_directory=publish,
            sample_metadata=samples,
        )
