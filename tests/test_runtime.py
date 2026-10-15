"""Acceptance tests for per-run analysis_output.json generation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nf_splice.renderers import render_outputs
from nf_splice.runtime import (
    ANALYSIS_OUTPUT_FILENAME,
    AnalysisOutputError,
    generate_analysis_output,
    load_and_validate_analysis_output,
)

JOB = {"job_id_short": "A123"}


def _contracts(root: Path) -> bytes:
    """Publish a reviewed output contract; return its bytes for comparison."""
    from test_output_contracts import contract

    rendered = render_outputs(contract())
    splice = root / "splice"
    splice.mkdir(exist_ok=True)
    (splice / "outputs.yaml").write_text(rendered.catalogue, encoding="utf-8")
    (splice / "outputs.schema.json").write_text(rendered.schema, encoding="utf-8")
    return rendered.schema.encode("utf-8")


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
    original_schema = _contracts(tmp_path)
    contract_bytes = {
        path.name: path.read_bytes() for path in (tmp_path / "splice").iterdir()
    }
    publish = _publish_directory(tmp_path)
    samples = tmp_path / "samples.csv"
    samples.write_text("sample\nS1\n", encoding="utf-8")
    job_metadata = {
        "job_id_short": "A123",
        "execution_timestamp": "2026-08-07T12:00:00Z",
        "job_metadata": {"annotations": {"instrument": "NovaSeq"}},
    }

    result = generate_analysis_output(
        tmp_path,
        publish_directory=publish,
        sample_metadata=samples,
        job_metadata=job_metadata,
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
    assert result.document["job_metadata"] == {"annotations": {"instrument": "NovaSeq"}}
    assert "run_metadata" not in result.document
    assert (tmp_path / "splice" / "outputs.schema.json").read_bytes() == original_schema
    assert {
        path.name: path.read_bytes() for path in (tmp_path / "splice").iterdir()
    } == contract_bytes

    repeated = generate_analysis_output(
        tmp_path,
        publish_directory=publish,
        sample_metadata=samples,
        job_metadata=job_metadata,
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

    optional = generate_analysis_output(
        tmp_path, publish_directory=publish, job_metadata=JOB
    )
    assert [item["output_type"] for item in optional.document["files"]] == [
        "run_report_html"
    ]

    (publish / "unexpected.txt").write_text("preserve\n", encoding="utf-8")
    with pytest.raises(
        AnalysisOutputError, match="not in the reviewed output contract"
    ):
        generate_analysis_output(tmp_path, publish_directory=publish, job_metadata=JOB)

    allowed = generate_analysis_output(
        tmp_path, publish_directory=publish, allow_unclassified=True, job_metadata=JOB
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
        result = generate_analysis_output(
            tmp_path, native_output_index=source, job_metadata=JOB
        )
    else:
        source = tmp_path / "outputs.tree.txt"
        source.write_text(
            ".:\nreports\nmetrics\n\n./reports:\nreport.html\n\n./metrics:\nS2.json\n",
            encoding="utf-8",
        )
        result = generate_analysis_output(
            tmp_path, output_tree=source, job_metadata=JOB
        )

    assert result.validation.valid
    assert [item["path"] for item in result.document["files"]] == [
        "metrics/S2.json",
        "reports/report.html",
    ]


def test_invalid_existing_analysis_output_is_rejected(tmp_path: Path) -> None:
    _contracts(tmp_path)
    publish = _publish_directory(tmp_path)
    valid = generate_analysis_output(
        tmp_path, publish_directory=publish, allow_unclassified=True, job_metadata=JOB
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
            job_metadata=JOB,
        )
