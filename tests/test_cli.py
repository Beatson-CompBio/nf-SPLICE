"""CLI and package metadata smoke tests."""

from importlib.metadata import metadata, version
from pathlib import Path

import pytest
from typer.testing import CliRunner

from nf_splice import __version__
from nf_splice.cli import app
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

runner = CliRunner()


def test_package_version_matches_installed_metadata() -> None:
    assert __version__ == version("nf-splice")


def test_supported_python_range_is_published() -> None:
    requires_python = metadata("nf-splice")["Requires-Python"]

    assert requires_python is not None
    assert ">=3.10" in requires_python
    assert "<3.15" in requires_python


def test_version_option() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.output.strip() == f"nf-splice {__version__}"


def test_help_option() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "Author and maintain a SPLICE integration layer." in result.output
    for command in (
        "inspect",
        "init",
        "status",
        "configure",
        "plan",
        "build",
        "validate",
        "tui",
        "analysis-output",
    ):
        assert command in result.output


def test_inspect_and_status_use_repository_service_results(tmp_path: Path) -> None:
    (tmp_path / "main.nf").write_text("workflow {}\n", encoding="utf-8")

    inspect_result = runner.invoke(app, ["inspect", "--repository", str(tmp_path)])
    status_result = runner.invoke(app, ["status", "--repository", str(tmp_path)])

    assert inspect_result.exit_code == 0
    assert f"Repository: {tmp_path.resolve()}" in inspect_result.output
    assert "SPLICE tree: absent" in inspect_result.output
    assert "nextflow_source: 1" in inspect_result.output
    assert status_result.exit_code == 0
    assert "Authoring state: not initialized" in status_result.output
    assert "identity: not_configured; unresolved=not available" in status_result.output
    assert "Build: output contracts available" in status_result.output
    assert (
        "Validation: runtime outputs available; bundle not available"
        in status_result.output
    )


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (["configure", "inputs"], "Integration-layer configuration"),
        (["plan"], "Change planning"),
        (["build", "all"], "Integration building"),
        (["validate"], "Integration validation"),
    ],
)
def test_planned_command_shells_fail_truthfully(
    arguments: list[str], message: str
) -> None:
    result = runner.invoke(app, arguments)

    assert result.exit_code == 2
    assert f"{message} is not available yet." in result.output


def test_output_contract_and_analysis_output_help_are_available() -> None:
    build = runner.invoke(app, ["build", "--help"])
    analysis = runner.invoke(app, ["analysis-output", "--help"])

    assert build.exit_code == 0
    assert "only outputs is currently available" in build.output
    assert "--check" in build.output
    assert analysis.exit_code == 0
    assert "generate" in analysis.output
    assert "validate" in analysis.output


def test_cli_builds_contract_then_generates_and_validates_analysis_output(
    tmp_path: Path,
) -> None:
    reviewed = ReviewedOutput(
        key="report",
        title="Report",
        description="Completed run report.",
        category=OutputCategory.RUN_REPORT,
        formats=(OutputFormat.HTML,),
        scopes=(OutputScope.RUN,),
        entity_types=(OutputEntityType.FILE,),
        path_patterns=(r"^reports/report\.html$",),
    )
    decision = Decision(
        id="output:report",
        status=DecisionStatus.REVIEWED,
        value=reviewed.model_dump(mode="json"),
    )
    document = AuthoringDocument(
        pipeline=PipelineIdentity(
            name="pipeline",
            version="1.0.0",
            repository_url="https://github.com/org/pipeline",
        ),
        output_contract=OutputContractSettings(schema_version="1.1.0"),
        decisions=(decision,),
        layers=(
            LayerState(
                name="outputs",
                configured=True,
                decision_ids=(decision.id,),
            ),
        ),
    )
    (tmp_path / "nf-splice.yaml").write_text(
        dump_authoring_document(document), encoding="utf-8"
    )
    publish = tmp_path / "published"
    (publish / "reports").mkdir(parents=True)
    (publish / "reports" / "report.html").write_text("ok\n", encoding="utf-8")

    check = runner.invoke(
        app,
        ["build", "outputs", "--repository", str(tmp_path), "--check"],
    )
    build = runner.invoke(app, ["build", "outputs", "--repository", str(tmp_path)])
    generate = runner.invoke(
        app,
        [
            "analysis-output",
            "generate",
            "--repository",
            str(tmp_path),
            "--publish-directory",
            str(publish),
            "--output-directory",
            str(publish),
        ],
    )
    validate = runner.invoke(
        app,
        [
            "analysis-output",
            "validate",
            str(publish / "analysis_output.json"),
            "--repository",
            str(tmp_path),
        ],
    )

    assert check.exit_code == 0
    assert "repository was not changed" in check.output
    assert build.exit_code == 0
    assert "Built 2 reviewed output-contract artefact(s)" in build.output
    assert generate.exit_code == 0
    assert "with 1 output record(s)" in generate.output
    assert validate.exit_code == 0
    assert "Valid analysis_output.json" in validate.output
