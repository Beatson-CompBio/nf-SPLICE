"""SPLICE job/sample/run output scopes, catalogue authority and migration."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]
from pydantic import ValidationError
from typer.testing import CliRunner

from nf_splice.cli import app
from nf_splice.domain import (
    OutputEntityType,
    OutputFormat,
    OutputScope,
    ReviewedOutput,
)
from nf_splice.inspectors import discover_output_candidates
from nf_splice.renderers import OutputContractInput, OutputPipeline, render_outputs
from nf_splice.runtime import (
    AnalysisOutputError,
    generate_analysis_output,
    legacy_run_metadata_to_job_metadata,
    load_and_validate_analysis_output,
    load_output_catalogue,
)

LEGACY = Path(__file__).parent / "fixtures" / "legacy-0.1.0"
JOB = {"job_id_short": "A123"}
runner = CliRunner()


def _output(key: str, scopes: tuple[OutputScope, ...], pattern: str) -> ReviewedOutput:
    return ReviewedOutput(
        key=key,
        title=key.replace("_", " ").title(),
        description=f"{key} description.",
        category="Free-text category" if key == "run_qc" else "job_report",
        formats=(
            OutputFormat.JSON if pattern.endswith(r"\.json$") else OutputFormat.TSV,
        ),
        scopes=scopes,
        entity_types=(OutputEntityType.FILE,),
        path_patterns=(pattern,),
    )


OUTPUTS = (
    ReviewedOutput(
        key="multiqc_report",
        title="MultiQC report",
        description="Job-wide MultiQC report.",
        category="job_report",
        formats=(OutputFormat.HTML,),
        scopes=(OutputScope.JOB,),
        entity_types=(OutputEntityType.FILE,),
        path_patterns=(r"^multiqc/multiqc_report\.html$",),
    ),
    _output("counts", (OutputScope.SAMPLE,), r"^quant/{sample}/counts\.tsv$"),
    _output("run_qc", (OutputScope.RUN,), r"^qc/{sample}/{run}\.json$"),
    _output("raw_metrics", (OutputScope.RUN,), r"^raw/{run}\.json$"),
)


def _publish(root: Path, outputs: tuple[ReviewedOutput, ...] = OUTPUTS) -> None:
    rendered = render_outputs(
        OutputContractInput(
            pipeline=OutputPipeline(
                id="example",
                name="example",
                version="1.0.0",
                repository_url="https://github.com/org/example",
            ),
            schema_version="2.0.0",
            outputs=outputs,
        )
    )
    splice = root / "splice"
    splice.mkdir(exist_ok=True)
    (splice / "outputs.schema.json").write_text(rendered.schema, encoding="utf-8")
    (splice / "outputs.yaml").write_text(rendered.catalogue, encoding="utf-8")


def _job_tree(root: Path, name: str = "results") -> Path:
    publish = root / name
    for relative in (
        "multiqc/multiqc_report.html",
        "quant/S1/counts.tsv",
        "quant/S2/counts.tsv",
        "qc/S1/S1_R1.json",
        "qc/S1/S1_R2.json",
        "qc/S2/S2_R1.json",
        "raw/S1_R1.json",
    ):
        path = publish / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(relative, encoding="utf-8")
    return publish


def _samples(root: Path) -> Path:
    path = root / "samples.csv"
    path.write_text("sample,run_id\nS1,S1_R1\nS1,S1_R2\nS2,S2_R1\n", encoding="utf-8")
    return path


def test_scope_guards_require_identifiers_for_their_owner() -> None:
    assert [item.value for item in OutputScope] == ["job", "sample", "run"]
    with pytest.raises(ValidationError, match="platform run identifier"):
        _output("bad", (OutputScope.RUN,), r"^qc/{sample}\.json$")
    with pytest.raises(ValidationError, match=r"\{sample\}"):
        _output("bad", (OutputScope.SAMPLE,), r"^qc/report\.json$")
    with pytest.raises(ValidationError, match="captures no identifier"):
        ReviewedOutput.model_validate(
            {
                **_output("x", (OutputScope.RUN,), r"^qc/{run}\.json$").model_dump(),
                "path_patterns": [r"^qc/{run}\.json$", r"^plain\.json$"],
            }
        )
    mixed = ReviewedOutput.model_validate(
        {
            **_output("x", (OutputScope.RUN,), r"^qc/{run}\.json$").model_dump(),
            "scopes": ["job", "run"],
            "path_patterns": [r"^qc/{run}\.json$", r"^plain\.json$"],
        }
    )
    assert mixed.scopes == (OutputScope.JOB, OutputScope.RUN)


def test_one_job_with_samples_and_runs_classifies_each_granularity(
    tmp_path: Path,
) -> None:
    _publish(tmp_path)
    (tmp_path / "splice" / "outputs.yaml").unlink()
    publish = _job_tree(tmp_path)

    result = generate_analysis_output(
        tmp_path,
        publish_directory=publish,
        sample_metadata=_samples(tmp_path),
        job_metadata={
            **JOB,
            "job_metadata": {
                "engine": "nextflow",
                "engine_execution_id": "native-1",
                "nextflow": {"session_id": "abc", "run_name": "happy_turing"},
            },
        },
    )

    records = {item["path"]: item for item in result.document["files"]}
    assert records["multiqc/multiqc_report.html"]["scope"] == "job"
    assert "sample_id" not in records["multiqc/multiqc_report.html"]
    assert records["quant/S2/counts.tsv"]["scope"] == "sample"
    assert records["quant/S2/counts.tsv"]["sample_id"] == "S2"
    assert {
        (item["run_id"], item["sample_id"])
        for item in records.values()
        if item["scope"] == "run"
    } == {("S1_R1", "S1"), ("S1_R2", "S1"), ("S2_R1", "S2")}
    assert records["raw/S1_R1.json"]["sample_id"] == "S1"
    assert result.document["job_metadata"]["nextflow"]["run_name"] == "happy_turing"
    assert dict(result.validation.by_scope) == {"job": 1, "run": 4, "sample": 2}
    assert "platform_run_id" not in result.document
    assert "run_metadata" not in result.document


def test_run_parentage_must_be_resolvable_and_consistent(tmp_path: Path) -> None:
    _publish(tmp_path)
    publish = _job_tree(tmp_path)
    with pytest.raises(AnalysisOutputError, match="unresolved parent sample"):
        generate_analysis_output(tmp_path, publish_directory=publish, job_metadata=JOB)

    conflicting = tmp_path / "conflict.csv"
    conflicting.write_text("sample,run_id\nS2,S1_R1\nS1,S1_R2\n", encoding="utf-8")
    with pytest.raises(AnalysisOutputError, match="belongs to sample 'S2'"):
        generate_analysis_output(
            tmp_path,
            publish_directory=publish,
            sample_metadata=conflicting,
            job_metadata=JOB,
        )
    with pytest.raises(AnalysisOutputError, match="job identity is required"):
        generate_analysis_output(
            tmp_path, publish_directory=publish, sample_metadata=_samples(tmp_path)
        )


def test_corrupt_embedded_catalogue_never_falls_back_to_yaml(tmp_path: Path) -> None:
    _publish(tmp_path)
    schema_path = tmp_path / "splice" / "outputs.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    del schema["x-output-catalog"]["output_types"][0]["path_patterns"]
    schema_path.write_text(json.dumps(schema), encoding="utf-8")
    assert (tmp_path / "splice" / "outputs.yaml").is_file()
    with pytest.raises(AnalysisOutputError, match="no YAML fallback"):
        load_output_catalogue(tmp_path)


def test_generated_contracts_never_publish_library_as_a_scope(tmp_path: Path) -> None:
    _publish(tmp_path)
    schema = json.loads(
        (tmp_path / "splice" / "outputs.schema.json").read_text(encoding="utf-8")
    )
    record = schema["definitions"]["file_record"]["properties"]
    assert record["scope"]["enum"] == ["job", "sample", "run"]
    catalog_scopes = {
        scope
        for item in schema["x-output-catalog"]["output_types"]
        for scope in item["scope"]
    }
    assert "library" not in catalog_scopes
    assert "platform_run_id" not in schema["properties"]
    assert "run_metadata" not in schema["properties"]
    catalogue = yaml.safe_load(
        (tmp_path / "splice" / "outputs.yaml").read_text(encoding="utf-8")
    )
    assert all("library" not in item["scope"] for item in catalogue["outputs"])


def test_two_jobs_produce_separate_documents_without_static_mutation(
    tmp_path: Path,
) -> None:
    _publish(tmp_path)
    static = {path.name: path.read_bytes() for path in (tmp_path / "splice").iterdir()}
    samples = _samples(tmp_path)
    first = generate_analysis_output(
        tmp_path,
        publish_directory=_job_tree(tmp_path, "job1"),
        sample_metadata=samples,
        job_metadata={"job_id_short": "A001"},
    )
    second_tree = _job_tree(tmp_path, "job2")
    (second_tree / "qc" / "S2" / "S2_R1.json").unlink()
    (second_tree / "qc" / "S2").rmdir()
    second = generate_analysis_output(
        tmp_path,
        publish_directory=second_tree,
        sample_metadata=samples,
        job_metadata={"job_id_short": "A002"},
    )
    assert first.document["job_id_short"] == "A001"
    assert second.document["job_id_short"] == "A002"
    assert len(first.document["files"]) == len(second.document["files"]) + 1
    assert {
        path.name: path.read_bytes() for path in (tmp_path / "splice").iterdir()
    } == static


def test_legacy_bundle_keeps_its_original_semantics_byte_for_byte(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    shutil.copytree(LEGACY / "repository", repository)
    job = LEGACY / "completed-job"
    run_metadata = json.loads((job / "run-metadata.json").read_text(encoding="utf-8"))
    expected = json.loads((job / "analysis_output.json").read_text(encoding="utf-8"))

    catalogue = load_output_catalogue(repository)
    assert catalogue.legacy

    via_legacy_flag = generate_analysis_output(
        repository, publish_directory=job / "results", run_metadata=run_metadata
    ).document
    via_job_metadata = generate_analysis_output(
        repository,
        publish_directory=job / "results",
        job_metadata=legacy_run_metadata_to_job_metadata(run_metadata),
    ).document
    for document in (via_legacy_flag, via_job_metadata):
        document.pop("publish_directory")
        assert document == expected
    report = load_and_validate_analysis_output(repository, job / "analysis_output.json")
    assert report.valid


def test_legacy_semantics_are_version_gated(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    shutil.copytree(LEGACY / "repository", repository)
    bundle_path = repository / "splice" / "bundle.json"
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle["schema_version"] = "0.3.0"
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    with pytest.raises(AnalysisOutputError, match="refusing to guess legacy"):
        load_output_catalogue(repository)


def test_legacy_run_metadata_conversion_is_explicit() -> None:
    converted = legacy_run_metadata_to_job_metadata(
        {
            "job_id_short": "A123",
            "workflow_run_id": "native",
            "nextflow_session_id": "session",
            "nextflow_run_name": "name",
            "run_metadata": {"instrument": "NovaSeq"},
            "operator": "lab",
        }
    )
    assert converted == {
        "job_id_short": "A123",
        "job_metadata": {
            "engine_execution_id": "native",
            "nextflow": {"session_id": "session", "run_name": "name"},
            "engine": "nextflow",
            "annotations": {"instrument": "NovaSeq", "operator": "lab"},
        },
    }
    with pytest.raises(AnalysisOutputError, match="platform_run_id is ambiguous"):
        legacy_run_metadata_to_job_metadata({"platform_run_id": "P1"})


def test_cli_prefers_job_metadata_and_deprecates_run_metadata(tmp_path: Path) -> None:
    _publish(tmp_path)
    publish = _job_tree(tmp_path)
    samples = _samples(tmp_path)
    job = tmp_path / "job.json"
    job.write_text(json.dumps(JOB), encoding="utf-8")
    common = [
        "analysis-output",
        "generate",
        "--repository",
        str(tmp_path),
        "--publish-directory",
        str(publish),
        "--sample-metadata",
        str(samples),
        "--output-directory",
        str(tmp_path),
    ]
    modern = runner.invoke(app, [*common, "--job-metadata", str(job)])
    assert modern.exit_code == 0, modern.output
    assert "deprecated" not in modern.output
    legacy = runner.invoke(app, [*common, "--run-metadata", str(job)])
    assert legacy.exit_code == 0, legacy.output
    assert "--run-metadata is deprecated" in legacy.output


def test_discovery_suggests_job_and_reads_legacy_catalogue_by_version(
    tmp_path: Path,
) -> None:
    tree = tmp_path / "tree"
    (tree / "multiqc").mkdir(parents=True)
    (tree / "multiqc" / "report.html").write_text("x", encoding="utf-8")
    discovered = discover_output_candidates(tmp_path, example_output_tree=tree)
    assert [item.candidate.likely_scope for item in discovered] == [OutputScope.JOB]

    splice = tmp_path / "splice"
    splice.mkdir()
    shutil.copy(LEGACY / "repository" / "splice" / "outputs.yaml", splice)
    by_key = {
        item.candidate.suggested_key: item.candidate.likely_scope
        for item in discover_output_candidates(tmp_path)
    }
    assert by_key["multiqc_report"] is OutputScope.JOB
    assert by_key["counts"] is OutputScope.SAMPLE
    assert by_key["library_qc"] is None
