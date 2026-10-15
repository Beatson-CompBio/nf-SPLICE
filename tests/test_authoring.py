"""Acceptance tests for identity initialisation and guided output review."""

from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError
from textual.widgets import Button, Input, Select, Static
from typer.testing import CliRunner

from nf_splice.cli import app
from nf_splice.domain import (
    DEFAULT_JOB_CATEGORY,
    DecisionStatus,
    OutputEntityType,
    OutputFormat,
    OutputScope,
    ReviewedOutput,
    dump_authoring_document,
)
from nf_splice.interfaces.tui import NfSpliceApp
from nf_splice.services import (
    ApplicationService,
    IdentityResolutionError,
    accept_output,
    discover_outputs,
    initialise_authoring_document,
    load_repository_document,
    merge_outputs,
    reject_output,
    split_output,
    unresolved_output_candidates,
)

runner = CliRunner()


def _initialise(root: Path) -> None:
    initialise_authoring_document(
        root,
        name="pipeline",
        version="2.3.4",
        repository_url="https://github.com/org/pipeline",
    )


def _git(root: Path, *arguments: str) -> None:
    subprocess.run(
        ("git", "-C", str(root), *arguments), check=True, capture_output=True
    )


def _one_candidate(root: Path) -> str:
    (root / "main.nf").write_text(
        """process REPORT {
    publishDir "${params.outdir}/reports"
    output:
    path "*.html", emit: report
}
""",
        encoding="utf-8",
    )
    return next(
        item.id
        for item in discover_outputs(root).unresolved
        if item.suggested_key == "report"
    )


def _review(key: str = "report") -> ReviewedOutput:
    return ReviewedOutput(
        key=key,
        title="Analysis report",
        description="Reviewed HTML report produced by the pipeline.",
        category=DEFAULT_JOB_CATEGORY,
        formats=(OutputFormat.HTML,),
        scopes=(OutputScope.JOB,),
        entity_types=(OutputEntityType.FILE,),
        path_patterns=(r"^reports/[^/]+\.html$",),
    )


def test_initialise_uses_explicitly_accepted_complete_config_metadata(
    tmp_path: Path,
) -> None:
    (tmp_path / "nextflow.config").write_text(
        """manifest {
    name = 'pipeline'
    version = '2.3.4'
    homePage = 'https://github.com/org/pipeline'
}
""",
        encoding="utf-8",
    )

    document = initialise_authoring_document(tmp_path, accept_detected=True)

    assert document.schema_version == "1.0"
    assert document.pipeline.version == "2.3.4"
    assert document.pipeline.release_url is None
    assert {item.status for item in document.decisions} == {DecisionStatus.REVIEWED}
    assert (tmp_path / "splice" / "nf-splice.yaml").is_file()


def test_initialise_requires_missing_values_and_rejects_placeholders(
    tmp_path: Path,
) -> None:
    (tmp_path / "nextflow.config").write_text(
        "manifest.name = 'pipeline'\n", encoding="utf-8"
    )

    with pytest.raises(IdentityResolutionError, match="pipeline version is required"):
        initialise_authoring_document(tmp_path, accept_detected=True)
    with pytest.raises(IdentityResolutionError, match="placeholder"):
        initialise_authoring_document(
            tmp_path,
            name="TODO",
            version="1.0.0",
            repository_url="https://github.com/org/pipeline",
        )


def test_initialise_reports_config_and_git_conflicts(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "remote", "add", "origin", "https://github.com/org/git-name.git")
    (tmp_path / "nextflow.config").write_text(
        """manifest {
    name = 'config-name'
    version = '1.0.0'
    homePage = 'https://github.com/org/config-name'
}
""",
        encoding="utf-8",
    )

    with pytest.raises(
        IdentityResolutionError, match="conflicting detected pipeline name"
    ):
        initialise_authoring_document(tmp_path, accept_detected=True)

    document = initialise_authoring_document(
        tmp_path,
        name="config-name",
        version="1.0.0",
        repository_url="https://github.com/org/config-name",
    )
    assert document.pipeline.name == "config-name"


def test_repository_without_git_metadata_accepts_complete_explicit_identity(
    tmp_path: Path,
) -> None:
    _initialise(tmp_path)

    document = load_repository_document(tmp_path)

    assert document.pipeline.repository_url == "https://github.com/org/pipeline"
    assert document.evidence == ()


def test_cli_initialises_reviewed_identity(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "init",
            "--repository",
            str(tmp_path),
            "--name",
            "pipeline",
            "--pipeline-version",
            "2.3.4",
            "--repository-url",
            "https://github.com/org/pipeline",
        ],
    )

    assert result.exit_code == 0
    assert "Initialised" in result.output
    assert load_repository_document(tmp_path).pipeline.name == "pipeline"


def test_static_and_tree_discovery_merge_duplicates_and_generalise_samples(
    tmp_path: Path,
) -> None:
    _initialise(tmp_path)
    (tmp_path / "main.nf").write_text(
        """process FASTP {
    publishDir "${params.outdir}/fastp"
    output:
    path "*.html", emit: report, optional: true
    path "*.html", emit: report, optional: true
}
workflow {
    output {
        reports = FASTP.out
    }
}
""",
        encoding="utf-8",
    )
    publish = tmp_path / "publish" / "fastp"
    publish.mkdir(parents=True)
    (publish / "sample_a.fastp.html").write_text("a", encoding="utf-8")
    (publish / "sample_b.fastp.html").write_text("b", encoding="utf-8")

    first = discover_outputs(tmp_path, publish_directory=publish.parent)
    second = discover_outputs(tmp_path, publish_directory=publish.parent)

    assert first.document == second.document
    assert any(
        candidate.path_pattern == r"^fastp/(?P<sample_id>[^/]+)\.fastp\.html$"
        for candidate in first.unresolved
    )
    report_candidates = [
        item for item in first.unresolved if item.suggested_key == "report"
    ]
    assert len(report_candidates) == 1
    assert report_candidates[0].processes == ("FASTP",)
    assert report_candidates[0].conditional is True


def test_example_tree_and_existing_output_catalogue_are_discovery_evidence(
    tmp_path: Path,
) -> None:
    _initialise(tmp_path)
    tree = tmp_path / "example-tree.txt"
    tree.write_text(
        ".:\nfastp\n\n./fastp:\nsample_a.fastp.html\nsample_b.fastp.html\n",
        encoding="utf-8",
    )
    splice = tmp_path / "splice"
    splice.mkdir(exist_ok=True)
    (splice / "outputs.yaml").write_text(
        """schema_version: '1.0'
pipeline: {}
outputs:
  - key: multiqc_report
    title: MultiQC report
    description: Aggregate quality-control report.
    category: quality_control
    scope: [run]
    entity_type: [file]
    format: [html]
    path_patterns: ['^multiqc/multiqc_report\\.html$']
""",
        encoding="utf-8",
    )

    result = discover_outputs(tmp_path, example_output_tree=tree)
    by_key = {item.suggested_key: item for item in result.unresolved}

    assert by_key["fastp_fastp_html"].path_pattern == (
        r"^fastp/(?P<sample_id>[^/]+)\.fastp\.html$"
    )
    assert by_key["multiqc_report"].suggested_description == (
        "Aggregate quality-control report."
    )
    evidence_sources = {item.provenance.source for item in result.document.evidence}
    assert {"example_output_tree", "existing_integration"}.issubset(evidence_sources)


def test_reviewed_and_rejected_outputs_survive_rediscovery(tmp_path: Path) -> None:
    _initialise(tmp_path)
    candidate_id = _one_candidate(tmp_path)
    accept_output(tmp_path, candidate_id, _review())

    discover_outputs(tmp_path)
    reviewed = next(
        item
        for item in load_repository_document(tmp_path).decisions
        if item.id == candidate_id
    )
    assert reviewed.status is DecisionStatus.REVIEWED

    reject_output(tmp_path, candidate_id, "Not part of the public result set")
    discover_outputs(tmp_path)
    rejected = next(
        item
        for item in load_repository_document(tmp_path).decisions
        if item.id == candidate_id
    )
    assert rejected.status is DecisionStatus.REJECTED
    assert rejected.reason == "Not part of the public result set"


def test_review_vocabulary_merge_and_split_transitions(tmp_path: Path) -> None:
    # 0.3.0: scientific categories are developer-chosen free text (ADR-0027).
    free = ReviewedOutput.model_validate(
        {**_review().model_dump(), "category": "Spatial transcriptomics QC"}
    )
    assert free.category == "Spatial transcriptomics QC"
    for unsafe in ("", "   ", "bad\nlabel"):
        with pytest.raises(ValidationError, match="category"):
            ReviewedOutput.model_validate(
                {**_review().model_dump(), "category": unsafe}
            )

    _initialise(tmp_path)
    (tmp_path / "main.nf").write_text(
        """workflow {
    output {
        first = ONE.out
        second = TWO.out
        broad = THREE.out
    }
}
""",
        encoding="utf-8",
    )
    candidates = discover_outputs(tmp_path).unresolved
    by_key = {item.suggested_key: item.id for item in candidates}

    merge_outputs(tmp_path, [by_key["first"], by_key["second"]], _review("merged"))
    split_output(
        tmp_path,
        by_key["broad"],
        [
            _review("broad_html"),
            _review("broad_json").model_copy(
                update={
                    "formats": (OutputFormat.JSON,),
                    "path_patterns": (r"^reports/[^/]+\.json$",),
                }
            ),
        ],
    )

    document = load_repository_document(tmp_path)
    statuses = {item.id: item.status for item in document.decisions}
    assert statuses[by_key["first"]] is DecisionStatus.REVIEWED
    assert statuses[by_key["second"]] is DecisionStatus.REJECTED
    assert statuses[by_key["broad"]] is DecisionStatus.REJECTED
    assert unresolved_output_candidates(document) == ()


def test_cli_exports_unresolved_and_applies_explicit_decision_file(
    tmp_path: Path,
) -> None:
    _initialise(tmp_path)
    candidate_id = _one_candidate(tmp_path)
    export = tmp_path / "unresolved.json"

    unresolved_result = runner.invoke(
        app,
        [
            "configure",
            "outputs",
            "--repository",
            str(tmp_path),
            "--export-unresolved",
            str(export),
        ],
    )

    assert unresolved_result.exit_code == 2
    exported = json.loads(export.read_text(encoding="utf-8"))
    assert exported[0]["id"]
    other_ids = [item["id"] for item in exported if item["id"] != candidate_id]
    decision_file = tmp_path / "decisions.yaml"
    decision_file.write_text(
        "actions:\n"
        "  - action: accept\n"
        f"    candidate_id: {candidate_id}\n"
        "    output:\n"
        "      key: report\n"
        "      title: Analysis report\n"
        "      description: Reviewed HTML report produced by the pipeline.\n"
        "      category: job_report\n"
        "      formats: [html]\n"
        "      scopes: [job]\n"
        "      entity_types: [file]\n"
        "      path_patterns: ['^reports/[^/]+\\.html$']\n"
        + "".join(
            "  - action: reject\n"
            f"    candidate_id: {other_id}\n"
            "    reason: Covered by the reviewed file-level output.\n"
            for other_id in other_ids
        ),
        encoding="utf-8",
    )

    reviewed_result = runner.invoke(
        app,
        [
            "configure",
            "outputs",
            "--repository",
            str(tmp_path),
            "--decision-file",
            str(decision_file),
        ],
    )

    assert reviewed_result.exit_code == 0
    assert "Output review is complete" in reviewed_result.output


def test_cli_repeatable_field_options_complete_non_interactive_review(
    tmp_path: Path,
) -> None:
    _initialise(tmp_path)
    _one_candidate(tmp_path)
    candidates = unresolved_output_candidates(load_repository_document(tmp_path))
    report = next(item for item in candidates if item.suggested_key == "report")
    other = next(item for item in candidates if item.id != report.id)

    result = runner.invoke(
        app,
        [
            "configure",
            "outputs",
            "--repository",
            str(tmp_path),
            "--set",
            f"{report.id}.description=Reviewed HTML report.",
            "--set",
            f"{report.id}.category=job_report",
            "--set",
            f"{report.id}.scopes=job",
            "--set",
            f"{other.id}.action=reject",
            "--set",
            f"{other.id}.reason=Covered by the reviewed file output.",
        ],
    )

    assert result.exit_code == 0
    assert unresolved_output_candidates(load_repository_document(tmp_path)) == ()


def test_cli_and_tui_save_byte_identical_authoring_state(tmp_path: Path) -> None:
    cli_root = tmp_path / "cli"
    tui_root = tmp_path / "tui"
    cli_root.mkdir()
    tui_root.mkdir()
    for root in (cli_root, tui_root):
        _initialise(root)
        _one_candidate(root)
    cli_candidate = unresolved_output_candidates(load_repository_document(cli_root))[0]
    tui_candidate = unresolved_output_candidates(load_repository_document(tui_root))[0]
    accept_output(cli_root, cli_candidate.id, _review())

    service = ApplicationService()
    tui = NfSpliceApp(service.inspect(tui_root), tui_root, service)

    async def exercise() -> None:
        async with tui.run_test() as pilot:
            tui.query_one("#output-key", Input).value = "report"
            tui.query_one("#output-title", Input).value = "Analysis report"
            tui.query_one(
                "#output-description", Input
            ).value = "Reviewed HTML report produced by the pipeline."
            tui.query_one("#output-category", Input).value = "job_report"
            tui.query_one("#output-format", Select).value = "html"
            tui.query_one("#output-scope", Select).value = "job"
            tui.query_one("#output-entity", Select).value = "file"
            tui.query_one("#output-pattern", Input).value = r"^reports/[^/]+\.html$"
            tui.query_one("#preview-output", Button).press()
            await pilot.pause()
            assert "Ready to save report" in str(
                tui.query_one("#review-summary", Static).content
            )
            tui.query_one("#accept-output", Button).press()
            await pilot.pause()

    asyncio.run(exercise())

    cli_document = load_repository_document(cli_root)
    tui_document = load_repository_document(tui_root)
    assert tui_candidate.id == cli_candidate.id
    assert dump_authoring_document(tui_document) == dump_authoring_document(
        cli_document
    )
