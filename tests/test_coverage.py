"""Contract validity, observed outputs and route coverage stay independent."""

from __future__ import annotations

import json
import os
import shutil
import stat
from pathlib import Path

import pytest
from typer.testing import CliRunner

from multi_route import EXAMPLE, author_all, build, copy_fixture
from nf_splice.cli import app
from nf_splice.layers import LayerError
from nf_splice.services.checks import CheckStatus, nf_core_lint
from nf_splice.services.coverage import (
    Catalogue,
    assess,
    enumerate_example,
    reconcile_example,
)

runner = CliRunner()


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = copy_fixture(tmp_path_factory.mktemp("built"))
    author_all(root)
    build(root)
    return root


def test_one_route_example_validates_without_the_other_routes(
    built: Path, tmp_path: Path
) -> None:
    result = assess(built, examples=[EXAMPLE], analysis_output_directory=tmp_path)
    document = result.to_json()

    assert document["contract_validity"]["status"] == "valid"
    observed = document["observed_output_compatibility"]
    assert observed["status"] == "compatible"
    reconciliation = observed["examples"][0]["reconciliation"]
    assert reconciliation["unclassified"] == []
    assert reconciliation["not_observed"] == [
        "hisat2_alignment",
        "salmon_quantification",
    ]
    # The inventory lists only what the STAR run produced.
    inventory = json.loads(
        (tmp_path / "example-1" / "analysis_output.json").read_text("utf-8")
    )
    types = {item["output_type"] for item in inventory["files"]}
    assert types == {
        "fastqc_report",
        "fastqc_archive",
        "star_alignment",
        "star_log",
        "multiqc_report",
    }
    assert len(inventory["files"]) == 9
    # The catalogue still covers every route, including unobserved ones.
    coverage = document["coverage_assessment"]
    assert coverage["summary"]["published_routes"] == 7
    assert coverage["summary"]["in_catalogue"] == 7
    assert coverage["summary"]["observed_in_example"] == 5
    statuses = {route["instance"]: route["status"] for route in coverage["routes"]}
    assert statuses["HISAT2_ALIGN"] == "confirmed_from_code"
    assert statuses["STAR_ALIGN"] == "observed_in_example"
    assert "Static analysis cannot prove completeness" in coverage["statement"]
    unpublished = {item["instance"] for item in coverage["unpublished"]}
    assert "SAMTOOLS_SORT" in unpublished
    published_patterns = json.loads(
        (built / "splice" / "outputs.schema.json").read_text("utf-8")
    )["x-output-catalog"]["output_types"]
    assert not any(
        r"\.sorted\.bam" in str(item["path_patterns"]) for item in published_patterns
    )


def test_unknown_observed_files_fail_by_default(built: Path, tmp_path: Path) -> None:
    example = tmp_path / "example"
    shutil.copytree(EXAMPLE, example)
    (example / "extra").mkdir()
    (example / "extra" / "unexpected.txt").write_text("x", encoding="utf-8")

    result = assess(built, examples=[example])
    observed = result.to_json()["observed_output_compatibility"]
    assert observed["status"] == "incompatible"
    assert observed["examples"][0]["reconciliation"]["unclassified"] == [
        "extra/unexpected.txt"
    ]
    assert observed["examples"][0]["analysis_output"]["status"] == "invalid"

    cli = runner.invoke(
        app, ["assess", "--repository", str(built), "--example-output", str(example)]
    )
    assert cli.exit_code == 2
    assert "unclassified: extra/unexpected.txt" in cli.output
    permissive = runner.invoke(
        app,
        [
            "analysis-output",
            "generate",
            "--repository",
            str(built),
            "--publish-directory",
            str(example),
            "--job-metadata",
            str(_job(tmp_path)),
            "--output-directory",
            str(tmp_path),
            "--allow-unclassified",
        ],
    )
    assert permissive.exit_code == 0, permissive.output
    assert "Omitted 1 explicitly allowed unclassified path(s)." in permissive.output


def _job(tmp_path: Path) -> Path:
    path = tmp_path / "job.json"
    path.write_text(json.dumps({"job_id_short": "A123"}), encoding="utf-8")
    return path


def test_no_example_still_assesses_contract_and_routes(built: Path) -> None:
    document = assess(built).to_json()
    assert document["contract_validity"]["status"] == "valid"
    observed = document["observed_output_compatibility"]
    assert observed["status"] == "not_assessed"
    assert "not a failure" in observed["note"]
    assert document["coverage_assessment"]["all_identified_routes_covered"] is True


def test_draft_only_repository_is_not_built(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path)
    author_all(root)
    document = assess(root, examples=[EXAMPLE]).to_json()
    assert document["contract_validity"]["status"] == "not_built"
    assert document["contract_validity"]["ready_to_build"] is True
    example = document["observed_output_compatibility"]["examples"][0]
    assert example["reconciliation"]["compatible"] is True
    assert example["analysis_output"]["status"] == "not_run"


def test_ambiguous_and_identifier_problems_are_actionable(tmp_path: Path) -> None:
    example = tmp_path / "results"
    (example / "star").mkdir(parents=True)
    (example / "star" / "S1.bam").write_text("x", encoding="utf-8")
    catalogue = Catalogue(
        "test",
        (
            {
                "key": "any_star",
                "scope": ["job"],
                "entity_type": ["file"],
                "path_patterns": [r"^star/.+$"],
            },
            {
                "key": "star_bam",
                "scope": ["sample"],
                "entity_type": ["file"],
                "path_patterns": [r"^star/[^/]+\.bam$"],
            },
        ),
    )
    reconciliation = reconcile_example(catalogue, enumerate_example(example))
    assert reconciliation.ambiguous == (
        {
            "path": "star/S1.bam",
            "output_types": ["star_bam", "any_star"],
            "runtime_choice": "star_bam",
        },
    )
    assert reconciliation.identifier_issues
    assert "captures no sample or run identifier" in reconciliation.identifier_issues[0]
    assert not reconciliation.compatible


def test_example_enumeration_is_safe(tmp_path: Path) -> None:
    example = tmp_path / "results"
    example.mkdir()
    (example / "a.txt").write_text("", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("s", encoding="utf-8")
    (example / "link").symlink_to(outside, target_is_directory=True)

    enumeration = enumerate_example(example)
    assert [item.path for item in enumeration.entries] == ["a.txt"]
    assert any("never followed" in item for item in enumeration.limitations)
    assert any("empty file" in item for item in enumeration.limitations)

    listing = tmp_path / "listing.txt"
    listing.write_text(".:\n../escape.txt\n", encoding="utf-8")
    with pytest.raises(LayerError, match="safely relative"):
        enumerate_example(listing)


# ------------------------------------------------------------ optional checks


def _fake_nf_core(directory: Path, *, version: str, report: dict[str, object]) -> None:
    script = directory / "nf-core"
    script.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "--version" ]; then\n'
        f'  echo "nf-core, version {version}"; exit 0\n'
        "fi\n"
        'while [ "$#" -gt 0 ]; do\n'
        '  if [ "$1" = "--json" ]; then shift; '
        f"printf '%s' '{json.dumps(report)}' > \"$1\"; fi\n"
        "  shift\n"
        "done\n"
        'echo "linted"\n',
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)


ALL = ("external_tools", "run_nextflow", "network")


def test_optional_nf_core_check_is_explicit_about_why_it_did_not_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = copy_fixture(tmp_path)
    assert nf_core_lint(root, permitted=ALL).status is CheckStatus.NOT_APPLICABLE

    (root / ".nf-core.yml").write_text("repository_type: pipeline\n", encoding="utf-8")
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    missing = nf_core_lint(root, permitted=ALL)
    assert missing.status is CheckStatus.NOT_RUN
    assert "not installed" in missing.reason

    tools = tmp_path / "bin"
    tools.mkdir()
    monkeypatch.setenv("PATH", f"{tools}{os.pathsep}/usr/bin{os.pathsep}/bin")
    _fake_nf_core(
        tools,
        version="4.0.2",
        report={"num_tests_pass": 10, "num_tests_warned": 1, "num_tests_failed": 0},
    )
    without_nextflow = nf_core_lint(root, permitted=ALL)
    assert without_nextflow.status is CheckStatus.NOT_RUN
    assert "Nextflow is not installed" in without_nextflow.reason
    nextflow = tools / "nextflow"
    nextflow.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    nextflow.chmod(nextflow.stat().st_mode | stat.S_IXUSR)
    refused = nf_core_lint(root, permitted=("external_tools",))
    assert refused.status is CheckStatus.NOT_RUN
    assert "run_nextflow, network" in refused.reason

    warned = nf_core_lint(root, permitted=ALL)
    assert warned.status is CheckStatus.PASSED_WITH_WARNINGS
    assert warned.version == "4.0.2"
    assert warned.counts["warned"] == 1

    _fake_nf_core(
        tools,
        version="4.0.2",
        report={
            "num_tests_pass": 3,
            "num_tests_failed": 1,
            "tests_failed": [["files_exist", "missing CHANGELOG.md"]],
        },
    )
    failed = nf_core_lint(root, permitted=ALL)
    assert failed.status is CheckStatus.FAILED
    assert failed.failures == ("files_exist: missing CHANGELOG.md",)

    _fake_nf_core(tools, version="2.14.1", report={})
    old = nf_core_lint(root, permitted=ALL)
    assert old.status is CheckStatus.NOT_RUN
    assert "not a supported version" in old.reason


def test_assess_cli_reports_three_results(built: Path) -> None:
    result = runner.invoke(
        app, ["assess", "--repository", str(built), "--example-output", str(EXAMPLE)]
    )
    assert result.exit_code == 0, result.output
    assert "Contract validity: valid" in result.output
    assert "Observed-output compatibility: compatible" in result.output
    assert "not observed (allowed): hisat2_alignment, salmon_quantification" in (
        result.output
    )
    assert "Coverage assessment:" in result.output
    assert "nf-core pipelines lint: not_applicable" in result.output
    bad = runner.invoke(app, ["assess", "--repository", str(built), "--allow", "x"])
    assert bad.exit_code != 0
