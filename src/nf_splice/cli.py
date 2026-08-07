"""Command-line entry point for nf-splice."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from nf_splice import __version__
from nf_splice.domain import OutputCandidate
from nf_splice.interfaces.tui import NfSpliceApp
from nf_splice.services import (
    ApplicationService,
    AuthoringOperationError,
    Operation,
    OutputReviewError,
    WorkspaceSnapshot,
    apply_output_decision_file,
    unresolved_output_candidates,
)

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
OptionalExistingPath = Annotated[
    Path | None,
    typer.Option(exists=True, resolve_path=True),
]
ExportUnresolvedOption = Annotated[
    Path | None,
    typer.Option(
        help="Write unresolved candidates as JSON; use '-' for standard output."
    ),
]
SetFieldOption = Annotated[
    list[str] | None,
    typer.Option(
        "--set",
        help="Repeat CANDIDATE_ID.FIELD=VALUE for explicit non-interactive review.",
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
def init_command(
    repository: RepositoryOption = Path("."),
    name: str | None = typer.Option(None, help="Reviewed pipeline name."),
    pipeline_version: str | None = typer.Option(
        None, "--pipeline-version", help="Reviewed pipeline version."
    ),
    repository_url: str | None = typer.Option(
        None, help="Reviewed pipeline repository URL."
    ),
    release_url: str | None = typer.Option(None, help="Optional release URL."),
    accept_detected: bool = typer.Option(
        False,
        help="Explicitly accept unambiguous identity evidence detected in config/Git.",
    ),
) -> None:
    """Initialise nf-splice.yaml with reviewed pipeline identity."""
    try:
        document = _service.initialise(
            repository,
            name=name,
            version=pipeline_version,
            repository_url=repository_url,
            release_url=release_url,
            accept_detected=accept_detected,
        )
    except (OSError, AuthoringOperationError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=2) from error
    typer.echo(
        f"Initialised {repository / 'nf-splice.yaml'} for "
        f"{document.pipeline.name} {document.pipeline.version}."
    )


def _parse_field_reviews(
    candidates: tuple[OutputCandidate, ...], assignments: list[str]
) -> list[tuple[str, dict[str, object]]]:
    by_id = {item.id: item for item in candidates}
    fields: dict[str, dict[str, str]] = {}
    for assignment in assignments:
        left, separator, value = assignment.partition("=")
        candidate_field, dot, field = left.rpartition(".")
        if not separator or not dot or candidate_field not in by_id or not field:
            raise OutputReviewError("--set must use EXISTING_CANDIDATE_ID.FIELD=VALUE")
        fields.setdefault(candidate_field, {})[field] = value

    reviews: list[tuple[str, dict[str, object]]] = []
    for candidate_id, assigned in fields.items():
        candidate = by_id[candidate_id]
        action = assigned.pop("action", "accept")
        if action == "reject":
            reviews.append(
                (
                    candidate_id,
                    {"action": "reject", "reason": assigned.get("reason", "")},
                )
            )
            continue
        if action != "accept":
            raise OutputReviewError("repeatable --set action must be accept or reject")
        sequence_fields = {"formats", "scopes", "entity_types", "path_patterns"}
        output: dict[str, object] = {
            "key": candidate.suggested_key,
            "title": candidate.suggested_title or candidate.suggested_key,
            "description": candidate.suggested_description or "",
            "formats": [candidate.suggested_format.value]
            if candidate.suggested_format
            else [],
            "scopes": [candidate.likely_scope.value] if candidate.likely_scope else [],
            "entity_types": [candidate.likely_entity_type.value]
            if candidate.likely_entity_type
            else [],
            "path_patterns": [candidate.path_pattern] if candidate.path_pattern else [],
        }
        for field, value in assigned.items():
            if field in sequence_fields:
                output[field] = [part for part in value.split(",") if part]
            elif field != "reason":
                output[field] = value
        reviews.append((candidate_id, output))
    return reviews


def _export_unresolved(
    path: Path | None, candidates: tuple[OutputCandidate, ...]
) -> None:
    if path is None:
        return
    content = (
        json.dumps([item.model_dump(mode="json") for item in candidates], indent=2)
        + "\n"
    )
    if str(path) == "-":
        typer.echo(content, nl=False)
    else:
        path.write_text(content, encoding="utf-8")


@app.command("configure")
def configure_command(
    layer: str = typer.Argument(help="Integration layer name."),
    repository: RepositoryOption = Path("."),
    example_output_tree: OptionalExistingPath = None,
    publish_directory: OptionalExistingPath = None,
    decision_file: OptionalExistingPath = None,
    export_unresolved: ExportUnresolvedOption = None,
    set_field: SetFieldOption = None,
) -> None:
    """Discover and explicitly review one integration layer."""
    if layer != "outputs":
        _unavailable(Operation.CONFIGURE)
    try:
        result = _service.discover_outputs(
            repository,
            example_output_tree=example_output_tree,
            publish_directory=publish_directory,
        )
        document = result.document
        if decision_file is not None:
            document = apply_output_decision_file(repository, decision_file)
        candidates = unresolved_output_candidates(document)
        for candidate_id, review in _parse_field_reviews(candidates, set_field or []):
            if review.get("action") == "reject":
                document = _service.reject_output(
                    repository, candidate_id, str(review.get("reason", ""))
                )
            else:
                document = _service.accept_output(repository, candidate_id, review)
        candidates = unresolved_output_candidates(document)
        _export_unresolved(export_unresolved, candidates)
    except (OSError, ValueError, AuthoringOperationError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=2) from error
    if candidates:
        typer.echo(
            f"{len(candidates)} output candidate(s) still require review.", err=True
        )
        raise typer.Exit(code=2)
    typer.echo("Output review is complete; canonical authoring state saved.")


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
    """Open the terminal workspace and guided output-review form."""
    NfSpliceApp(_service.inspect(repository), repository, _service).run()


def main() -> None:
    """Run the nf-splice command-line interface."""
    app()
