"""Command-line entry point for nf-splice."""

from pathlib import Path
from typing import Annotated

import typer

from nf_splice import __version__
from nf_splice.interfaces.tui import NfSpliceApp
from nf_splice.services import ApplicationService, Operation, WorkspaceSnapshot

app = typer.Typer(
    name="nf-splice",
    help="Author and maintain a SPLICE integration layer.",
    add_completion=False,
    no_args_is_help=True,
)

_service = ApplicationService()
RepositoryOption = Annotated[
    Path,
    typer.Option(
        "--repository",
        "-r",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Nextflow pipeline repository to inspect.",
    ),
]


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"nf-splice {__version__}")
        raise typer.Exit


@app.callback()
def cli(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the nf-splice version and exit.",
    ),
) -> None:
    """Author and maintain a SPLICE integration layer."""


def _inspection_lines(snapshot: WorkspaceSnapshot) -> list[str]:
    inspection = snapshot.inspection
    revision = inspection.repository_revision or "not detected"
    lines = [
        f"Repository: {inspection.root}",
        f"Revision: {revision}",
        f"SPLICE tree: {inspection.splice_tree.state.value}",
        f"Evidence: {len(inspection.evidence)}",
    ]
    lines.extend(
        f"  {item.kind.value}: {item.count}" for item in snapshot.evidence_counts
    )
    if snapshot.warnings:
        lines.append("Warnings:")
        lines.extend(f"  - {warning}" for warning in snapshot.warnings)
    return lines


def _status_lines(snapshot: WorkspaceSnapshot) -> list[str]:
    unresolved = snapshot.authoring.unresolved_decisions
    unresolved_text = "not available" if unresolved is None else str(unresolved)
    lines = _inspection_lines(snapshot)
    lines.extend(
        [
            f"Authoring state: {snapshot.authoring.state.value}",
            f"Unresolved decisions: {unresolved_text}",
            f"Build: {snapshot.build_status}",
            f"Validation: {snapshot.validation_status}",
            "Layers:",
        ]
    )
    for layer in snapshot.layers:
        layer_unresolved = (
            "not available"
            if layer.unresolved_decisions is None
            else str(layer.unresolved_decisions)
        )
        lines.append(
            f"  {layer.name}: {layer.status.value}; unresolved={layer_unresolved}"
        )
    return lines


def _echo_lines(lines: list[str]) -> None:
    typer.echo("\n".join(lines))


def _unavailable(operation: Operation) -> None:
    result = _service.unavailable(operation)
    typer.echo(result.message, err=True)
    raise typer.Exit(code=2)


@app.command("inspect")
def inspect_command(repository: RepositoryOption = Path(".")) -> None:
    """Inspect pipeline evidence and the existing repository-root splice/ tree."""
    _echo_lines(_inspection_lines(_service.inspect(repository)))


@app.command("status")
def status_command(repository: RepositoryOption = Path(".")) -> None:
    """Show the shared read-only integration workspace status."""
    _echo_lines(_status_lines(_service.inspect(repository)))


@app.command("init")
def init_command() -> None:
    """Initialise reviewed authoring state when that workflow becomes available."""
    _unavailable(Operation.INIT)


@app.command("configure")
def configure_command(
    layer: str = typer.Argument(help="Integration layer name."),
) -> None:
    """Configure an integration layer when authoring support becomes available."""
    del layer
    _unavailable(Operation.CONFIGURE)


@app.command("plan")
def plan_command() -> None:
    """Preview proposed changes when planning support becomes available."""
    _unavailable(Operation.PLAN)


@app.command("build")
def build_command(
    target: str = typer.Argument(help="Integration layer name or 'all'."),
) -> None:
    """Build reviewed integration files when build support becomes available."""
    del target
    _unavailable(Operation.BUILD)


@app.command("validate")
def validate_command() -> None:
    """Validate integration files when validation support becomes available."""
    _unavailable(Operation.VALIDATE)


@app.command("tui")
def tui_command(repository: RepositoryOption = Path(".")) -> None:
    """Open the read-only terminal workspace over the shared inspection result."""
    NfSpliceApp(_service.inspect(repository)).run()


def main() -> None:
    """Run the nf-splice command-line interface."""
    app()
