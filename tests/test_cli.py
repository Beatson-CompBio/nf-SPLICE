"""CLI and package metadata smoke tests."""

from importlib.metadata import metadata, version

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
