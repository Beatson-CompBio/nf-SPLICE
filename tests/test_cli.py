"""CLI and package metadata smoke tests."""

from importlib.metadata import metadata, version
from pathlib import Path

import pytest
from typer.testing import CliRunner

from nf_splice import __version__
from nf_splice.cli import app

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
    assert "Build: not available" in status_result.output
    assert "Validation: not available" in status_result.output


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (["init"], "Authoring-state initialisation"),
        (["configure", "outputs"], "Integration-layer configuration"),
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
