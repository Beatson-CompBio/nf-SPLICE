"""Command-line entry point for nf-splice."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Annotated, Protocol

import typer

from nf_splice import __version__
from nf_splice.contracts import (
    ContractRegistryError,
    breaking_changes,
    families,
    family,
    meta_schema,
    release,
    validate_contract_document,
)
from nf_splice.domain import (
    InputCandidate,
    OutputCandidate,
    ProvenanceCandidate,
)
from nf_splice.interfaces.tui import NfSpliceApp
from nf_splice.runtime import (
    AnalysisOutputError,
    generate_analysis_output,
    load_and_validate_analysis_output,
)
from nf_splice.services import (
    ApplicationService,
    AuthoringOperationError,
    ChangeKind,
    ComponentReviewError,
    ExecutionProfileError,
    InputReviewError,
    Operation,
    OutputReviewError,
    ProvenanceReviewError,
    StateMigrationError,
    StaticChangeKind,
    WorkspaceSnapshot,
    apply_output_decision_file,
    plan_document,
    unresolved_component_candidates,
    unresolved_execution_profiles,
    unresolved_input_candidates,
    unresolved_output_candidates,
    unresolved_provenance_candidates,
)

app = typer.Typer(
    name="nf-splice",
    help="Author and maintain a SPLICE integration layer.",
    add_completion=False,
    no_args_is_help=True,
)
analysis_output_app = typer.Typer(
    help="Generate or validate the per-run analysis_output.json file.",
    no_args_is_help=True,
)
app.add_typer(analysis_output_app, name="analysis-output")
schema_app = typer.Typer(
    help="List, show and validate the five workflow-bundle contract families.",
    no_args_is_help=True,
)
app.add_typer(schema_app, name="schema")

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
OutputDirectoryOption = Annotated[
    Path,
    typer.Option(
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Directory in which to write analysis_output.json.",
    ),
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
        help=(
            "Repeat PARAMETER=CLASSIFICATION or CANDIDATE_ID.FIELD=VALUE for "
            "explicit non-interactive review."
        ),
    ),
]


class _BuildChange(Protocol):
    @property
    def path(self) -> Path: ...

    @property
    def kind(self) -> ChangeKind | StaticChangeKind: ...

    @property
    def diff(self) -> str: ...


def _layer_build_document(
    target: str,
    changes: Iterable[_BuildChange],
    *,
    wrote: bool,
    check: bool,
    non_interactive: bool,
) -> dict[str, object]:
    """Return one stable JSON envelope for every layer build target."""
    return {
        "target": target,
        "changes": [
            {
                "path": item.path.as_posix().split("/splice/", 1)[-1],
                "kind": item.kind.value,
                "diff": item.diff,
            }
            for item in changes
        ],
        "wrote": wrote,
        "check": check,
        "non_interactive": non_interactive,
    }


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
    """Initialise splice/nf-splice.yaml with reviewed pipeline identity."""
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
        f"Initialised {repository / 'splice' / 'nf-splice.yaml'} for "
        f"{document.pipeline.name} {document.pipeline.version}."
    )


@app.command("migrate-state")
def migrate_state_command(
    repository: RepositoryOption = Path("."),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Apply the displayed migration while preserving legacy source files.",
    ),
) -> None:
    """Preview or explicitly apply legacy root-state reconciliation."""
    try:
        result = (
            _service.apply_state_migration(repository)
            if apply
            else _service.plan_state_migration(repository)
        )
    except (OSError, StateMigrationError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=2) from error
    if not result.changes:
        typer.echo("No repository-root legacy state was detected.")
        return
    for change in result.changes:
        typer.echo(
            f"{change.kind.value}: {change.source.relative_to(repository)} -> "
            f"{change.destination.relative_to(repository)}"
        )
    if apply:
        if result.wrote:
            typer.echo(
                "Migration applied atomically; legacy source files were preserved."
            )
        else:
            typer.echo("Canonical state is already byte-identical; no files changed.")
    else:
        typer.echo(
            "Preview complete; repository was not changed. Pass --apply to migrate."
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


def _export_unresolved(path: Path | None, candidates: tuple[object, ...]) -> None:
    if path is None:
        return
    content = (
        json.dumps(
            [
                item.model_dump(mode="json")
                for item in candidates
                if hasattr(item, "model_dump")
            ],
            indent=2,
        )
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
    contract_version: str | None = typer.Option(
        None,
        help=(
            "Reviewed output-contract schema version (X.Y.Z), independent of "
            "pipeline version."
        ),
    ),
    accept_detected: bool = typer.Option(
        False,
        help="Explicitly accept every detected component without conflicts.",
    ),
) -> None:
    """Discover and explicitly review one integration layer."""
    if layer not in {
        "inputs",
        "outputs",
        "components",
        "execution-profiles",
        "provenance",
    }:
        _unavailable(Operation.CONFIGURE)
    try:
        if layer == "inputs":
            document = _service.discover_inputs(repository)
            input_candidates = unresolved_input_candidates(document)
            input_reviews: list[dict[str, object]] = []
            if decision_file is not None:
                loaded: object = json.loads(decision_file.read_text(encoding="utf-8"))
                if not isinstance(loaded, list) or not all(
                    isinstance(item, dict) for item in loaded
                ):
                    raise InputReviewError(
                        "input decision file must contain a JSON array"
                    )
                input_reviews.extend(loaded)
            input_reviews.extend(
                _parse_input_reviews(input_candidates, set_field or [])
            )
            for review in input_reviews:
                name = str(review.get("parameter", ""))
                candidate_id = name if name.startswith("input:") else f"input:{name}"
                document = _service.review_input(
                    repository,
                    candidate_id,
                    str(review.get("classification", "")),
                    type_override=(
                        str(review["type"]) if review.get("type") is not None else None
                    ),
                    description_override=(
                        str(review["description"])
                        if review.get("description") is not None
                        else None
                    ),
                )
            input_candidates = unresolved_input_candidates(document)
            _export_unresolved(export_unresolved, input_candidates)
            if input_candidates:
                typer.echo(
                    f"{len(input_candidates)} input parameter(s) still require review.",
                    err=True,
                )
                raise typer.Exit(code=2)
            typer.echo("Input review is complete; canonical authoring state saved.")
            return

        if layer == "components":
            document = _service.discover_components(repository)
            if accept_detected:
                document = _service.accept_unambiguous_components(repository)
            component_candidates = unresolved_component_candidates(document)
            component_reviews: list[dict[str, object]] = []
            if decision_file is not None:
                loaded = json.loads(decision_file.read_text(encoding="utf-8"))
                if not isinstance(loaded, list) or not all(
                    isinstance(item, dict) for item in loaded
                ):
                    raise ComponentReviewError(
                        "component decision file must contain a JSON array"
                    )
                component_reviews.extend(loaded)
            component_reviews.extend(
                _parse_component_reviews(component_candidates, set_field or [])
            )
            for review in component_reviews:
                candidate_id = str(review.get("component", ""))
                document = _service.review_component(
                    repository,
                    candidate_id,
                    version=(
                        str(review["version"])
                        if review.get("version") is not None
                        else None
                    ),
                    container_uri=(
                        str(review["container_uri"])
                        if review.get("container_uri") is not None
                        else None
                    ),
                )
            component_candidates = unresolved_component_candidates(document)
            _export_unresolved(export_unresolved, component_candidates)
            if component_candidates:
                typer.echo(
                    f"{len(component_candidates)} component(s) still require review.",
                    err=True,
                )
                raise typer.Exit(code=2)
            typer.echo("Component review is complete; canonical authoring state saved.")
            return

        if layer == "execution-profiles":
            document = _service.discover_execution_profiles(repository)
            profile_candidates = unresolved_execution_profiles(document)
            profile_reviews: list[dict[str, object]] = []
            if decision_file is not None:
                loaded = json.loads(decision_file.read_text(encoding="utf-8"))
                if not isinstance(loaded, list) or not all(
                    isinstance(item, dict) for item in loaded
                ):
                    raise ExecutionProfileError(
                        "execution-profile decision file must contain a JSON array"
                    )
                profile_reviews.extend(loaded)
            profile_reviews.extend(
                _parse_profile_reviews(profile_candidates, set_field or [])
            )
            for review in profile_reviews:
                candidate_id = str(review.get("profile", ""))
                if review.get("action") == "reject":
                    document = _service.reject_execution_profile(
                        repository,
                        candidate_id,
                        str(review.get("reason", "")),
                    )
                    continue
                document = _service.review_execution_profile(
                    repository,
                    candidate_id,
                    profile_type=str(review.get("type", "")),
                    description=str(review.get("description", "")),
                    executor=(
                        str(review["executor"])
                        if review.get("executor") is not None
                        else None
                    ),
                    container_engine=(
                        str(review["container_engine"])
                        if review.get("container_engine") is not None
                        else None
                    ),
                    config_source=(
                        str(review["config_source"])
                        if review.get("config_source") is not None
                        else None
                    ),
                )
            profile_candidates = unresolved_execution_profiles(document)
            _export_unresolved(export_unresolved, profile_candidates)
            if profile_candidates:
                typer.echo(
                    f"{len(profile_candidates)} execution profile(s) still require "
                    "review.",
                    err=True,
                )
                raise typer.Exit(code=2)
            typer.echo(
                "Execution-profile review is complete; canonical authoring state saved."
            )
            return

        if layer == "provenance":
            document = _service.discover_provenance(repository)
            provenance_candidates = unresolved_provenance_candidates(document)
            provenance_review_data = _provenance_review(decision_file, set_field or [])
            if provenance_review_data is not None:
                candidate_id = _select_provenance_candidate(
                    provenance_candidates, provenance_review_data
                )
                document = _service.review_provenance(repository, candidate_id)
            provenance_candidates = unresolved_provenance_candidates(document)
            _export_unresolved(export_unresolved, provenance_candidates)
            if provenance_candidates:
                typer.echo(
                    f"{len(provenance_candidates)} provenance strategy candidate(s) "
                    "still require review.",
                    err=True,
                )
                raise typer.Exit(code=2)
            typer.echo(
                "Provenance review is complete; canonical authoring state saved."
            )
            return

        result = _service.discover_outputs(
            repository,
            example_output_tree=example_output_tree,
            publish_directory=publish_directory,
            contract_version=contract_version,
        )
        document = result.document
        if decision_file is not None:
            document = apply_output_decision_file(repository, decision_file)
        output_candidates = unresolved_output_candidates(document)
        for candidate_id, review in _parse_field_reviews(
            output_candidates, set_field or []
        ):
            if review.get("action") == "reject":
                document = _service.reject_output(
                    repository, candidate_id, str(review.get("reason", ""))
                )
            else:
                document = _service.accept_output(repository, candidate_id, review)
        output_candidates = unresolved_output_candidates(document)
        _export_unresolved(export_unresolved, output_candidates)
    except (OSError, ValueError, AuthoringOperationError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=2) from error
    if output_candidates:
        typer.echo(
            f"{len(output_candidates)} output candidate(s) still require review.",
            err=True,
        )
        raise typer.Exit(code=2)
    typer.echo("Output review is complete; canonical authoring state saved.")


def _parse_input_reviews(
    candidates: tuple[InputCandidate, ...], assignments: list[str]
) -> list[dict[str, object]]:
    """Parse repeatable input classifications without interface-side semantics."""
    by_id = {item.id: item for item in candidates}
    by_name = {item.name: item.id for item in candidates}
    grouped: dict[str, dict[str, object]] = {}
    for assignment in assignments:
        left, separator, value = assignment.partition("=")
        if not separator:
            raise InputReviewError("input --set must contain '='")
        matched = next(
            (
                candidate_id
                for candidate_id in sorted(by_id, key=len, reverse=True)
                if left == candidate_id or left.startswith(candidate_id + ".")
            ),
            None,
        )
        if matched is None:
            name, dot, field = left.partition(".")
            matched = by_name.get(name)
            if matched is None:
                raise InputReviewError(f"unknown input parameter {name!r}")
            selected_field = field if dot else "classification"
        else:
            selected_field = (
                left[len(matched) + 1 :] if left != matched else "classification"
            )
        grouped.setdefault(matched, {"parameter": matched})[selected_field] = value
    return list(grouped.values())


def _parse_component_reviews(
    candidates: tuple[object, ...], assignments: list[str]
) -> list[dict[str, object]]:
    """Parse explicit component selections against currently unresolved IDs."""
    identifiers = {str(item.id) for item in candidates if hasattr(item, "id")}
    grouped: dict[str, dict[str, object]] = {}
    for assignment in assignments:
        left, separator, value = assignment.partition("=")
        if not separator:
            raise ComponentReviewError("component --set must contain '='")
        candidate_id = next(
            (
                item
                for item in sorted(identifiers, key=len, reverse=True)
                if left == item or left.startswith(item + ".")
            ),
            None,
        )
        if candidate_id is None:
            raise ComponentReviewError(f"unknown component candidate in {left!r}")
        field = left[len(candidate_id) + 1 :] if left != candidate_id else "accept"
        review = grouped.setdefault(candidate_id, {"component": candidate_id})
        if field != "accept":
            review[field] = value
    return list(grouped.values())


def _parse_profile_reviews(
    candidates: tuple[object, ...], assignments: list[str]
) -> list[dict[str, object]]:
    """Parse repeatable profile selections against unresolved candidate IDs."""
    identifiers = {str(item.id) for item in candidates if hasattr(item, "id")}
    grouped: dict[str, dict[str, object]] = {}
    for assignment in assignments:
        left, separator, value = assignment.partition("=")
        if not separator:
            raise ExecutionProfileError("execution-profile --set must contain '='")
        candidate_id = next(
            (
                item
                for item in sorted(identifiers, key=len, reverse=True)
                if left == item or left.startswith(item + ".")
            ),
            None,
        )
        if candidate_id is None:
            raise ExecutionProfileError(
                f"unknown execution profile candidate in {left!r}"
            )
        field = left[len(candidate_id) + 1 :] if left != candidate_id else "action"
        grouped.setdefault(candidate_id, {"profile": candidate_id})[field] = value
    return list(grouped.values())


def _provenance_review(
    decision_file: Path | None, assignments: list[str]
) -> dict[str, object] | None:
    """Load one explicit provenance decision from JSON and/or repeatable fields."""
    review: dict[str, object] = {}
    if decision_file is not None:
        loaded: object = json.loads(decision_file.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ProvenanceReviewError(
                "provenance decision file must contain a JSON object"
            )
        review.update(loaded)
    for assignment in assignments:
        left, separator, value = assignment.partition("=")
        if not separator or not left.startswith("provenance."):
            raise ProvenanceReviewError(
                "provenance --set must use provenance.FIELD=VALUE"
            )
        field = left.removeprefix("provenance.")
        review[field] = value
    return review or None


def _select_provenance_candidate(
    candidates: tuple[ProvenanceCandidate, ...], review: dict[str, object]
) -> str:
    """Resolve explicit approval of the sole repository-root source."""
    if str(review.get("include", "")).lower() not in {"true", "yes", "1"}:
        raise ProvenanceReviewError(
            'approve inclusion with provenance.include=true or JSON {"include": true}'
        )
    candidate_id = review.get("candidate")
    if candidate_id is not None:
        selected = str(candidate_id)
        if not any(item.id == selected for item in candidates):
            raise ProvenanceReviewError(f"unknown provenance candidate {selected!r}")
        return selected
    if len(candidates) != 1:
        raise ProvenanceReviewError(
            "repository-root RO-Crate candidate is missing or ambiguous"
        )
    return str(candidates[0].id)


@app.command("plan")
def plan_command(
    target: str = typer.Argument("all", help="Complete integration target."),
    repository: RepositoryOption = Path("."),
    json_output: bool = typer.Option(
        False, "--json", help="Emit a stable machine-readable plan."
    ),
) -> None:
    """Preview complete reviewed integration changes and blockers."""
    try:
        plan = _service.plan_integration(repository, target=target)
    except (OSError, ValueError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=2) from error
    if json_output:
        typer.echo(json.dumps(plan_document(plan), indent=2))
    else:
        for blocker in plan.blockers:
            typer.echo(f"blocked: {blocker}", err=True)
        for change in plan.changes:
            typer.echo(f"{change.kind.value}: {change.path}")
            if change.diff:
                typer.echo(change.diff, nl=not change.diff.endswith("\n"))
        typer.echo("Plan complete; repository was not changed.")
    if not plan.ready:
        raise typer.Exit(code=2)


@app.command("build")
def build_command(
    target: str = typer.Argument(help="Integration layer name or 'all'."),
    repository: RepositoryOption = Path("."),
    check: bool = typer.Option(
        False, help="Show deterministic generated-file changes without writing."
    ),
    replace_existing: bool = typer.Option(
        False,
        help=(
            "Replace a differing recognized generated artefact after reviewing "
            "its diff."
        ),
    ),
    non_interactive: bool = typer.Option(
        False,
        "--non-interactive",
        help="Fail on every unresolved decision or required review.",
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Emit a stable machine-readable build result."
    ),
) -> None:
    """Build one reviewed static layer or the complete integration."""
    if target not in {
        "all",
        "bundle",
        "outputs",
        "inputs",
        "components",
        "execution-profiles",
        "provenance",
    }:
        _unavailable(Operation.BUILD)
    try:
        if target in {"all", "bundle"}:
            result = _service.build_integration(
                repository,
                target=target,
                replace_existing=replace_existing,
                check=check,
            )
            if json_output:
                payload = plan_document(result.plan)
                payload["wrote"] = result.wrote
                payload["check"] = check
                payload["non_interactive"] = non_interactive
                typer.echo(json.dumps(payload, indent=2))
            else:
                for integration_change in result.plan.changes:
                    typer.echo(
                        f"{integration_change.kind.value}: {integration_change.path}"
                    )
                    if integration_change.diff:
                        typer.echo(
                            integration_change.diff,
                            nl=not integration_change.diff.endswith("\n"),
                        )
                if check:
                    typer.echo("Check complete; repository was not changed.")
                elif result.wrote:
                    typer.echo(f"Built reviewed {target} integration artefacts.")
                else:
                    typer.echo(
                        "Integration artefacts are byte-identical; no files changed."
                    )
            return
        if target == "execution-profiles":
            execution_plan = _service.plan_execution_profiles(repository)
            if check:
                if json_output:
                    typer.echo(
                        json.dumps(
                            _layer_build_document(
                                target,
                                execution_plan.changes,
                                wrote=False,
                                check=True,
                                non_interactive=non_interactive,
                            ),
                            indent=2,
                        )
                    )
                else:
                    for change in execution_plan.changes:
                        typer.echo(f"{change.kind.value}: {change.path}")
                        if change.diff:
                            typer.echo(change.diff, nl=not change.diff.endswith("\n"))
                    typer.echo("Check complete; repository was not changed.")
                return
            execution_result = _service.build_execution_profiles(
                repository, replace_existing=replace_existing
            )
            if json_output:
                typer.echo(
                    json.dumps(
                        _layer_build_document(
                            target,
                            execution_result.changes,
                            wrote=execution_result.wrote,
                            check=False,
                            non_interactive=non_interactive,
                        ),
                        indent=2,
                    )
                )
                return
            for change in execution_result.changes:
                typer.echo(f"{change.kind.value}: {change.path}")
                if change.diff:
                    typer.echo(change.diff, nl=not change.diff.endswith("\n"))
            if execution_result.wrote:
                changed = sum(
                    item.kind is not StaticChangeKind.UNCHANGED
                    for item in execution_result.changes
                )
                typer.echo(f"Built {changed} reviewed execution artefact(s).")
            else:
                typer.echo("Execution artefacts are byte-identical; no files changed.")
            return
        if target == "provenance":
            provenance_plan = _service.plan_provenance(repository)
            if check:
                if json_output:
                    typer.echo(
                        json.dumps(
                            _layer_build_document(
                                target,
                                (provenance_plan.change,),
                                wrote=False,
                                check=True,
                                non_interactive=non_interactive,
                            ),
                            indent=2,
                        )
                    )
                else:
                    typer.echo(
                        f"{provenance_plan.change.kind.value}: "
                        f"{provenance_plan.change.path}"
                    )
                    if provenance_plan.change.diff:
                        typer.echo(
                            provenance_plan.change.diff,
                            nl=not provenance_plan.change.diff.endswith("\n"),
                        )
                    typer.echo("Check complete; repository was not changed.")
                return
            provenance_result = _service.build_provenance(
                repository, replace_existing=replace_existing
            )
            if json_output:
                typer.echo(
                    json.dumps(
                        _layer_build_document(
                            target,
                            (provenance_result.change,),
                            wrote=provenance_result.wrote,
                            check=False,
                            non_interactive=non_interactive,
                        ),
                        indent=2,
                    )
                )
                return
            typer.echo(
                f"{provenance_result.change.kind.value}: "
                f"{provenance_result.change.path}"
            )
            if provenance_result.change.diff:
                typer.echo(
                    provenance_result.change.diff,
                    nl=not provenance_result.change.diff.endswith("\n"),
                )
            if provenance_result.wrote:
                typer.echo("Built reviewed provenance artefact.")
            else:
                typer.echo("Provenance artefact is byte-identical; no files changed.")
            return
        if target in {"inputs", "components"}:
            static_plan = _service.plan_static_layer(repository, target)
            if check:
                if json_output:
                    typer.echo(
                        json.dumps(
                            _layer_build_document(
                                target,
                                (static_plan.change,),
                                wrote=False,
                                check=True,
                                non_interactive=non_interactive,
                            ),
                            indent=2,
                        )
                    )
                else:
                    typer.echo(
                        f"{static_plan.change.kind.value}: {static_plan.change.path}"
                    )
                    if static_plan.change.diff:
                        typer.echo(
                            static_plan.change.diff,
                            nl=not static_plan.change.diff.endswith("\n"),
                        )
                    typer.echo("Check complete; repository was not changed.")
                return
            static_result = _service.build_static_layer(
                repository, target, replace_existing=replace_existing
            )
            if json_output:
                typer.echo(
                    json.dumps(
                        _layer_build_document(
                            target,
                            (static_result.change,),
                            wrote=static_result.wrote,
                            check=False,
                            non_interactive=non_interactive,
                        ),
                        indent=2,
                    )
                )
                return
            typer.echo(
                f"{static_result.change.kind.value}: {static_result.change.path}"
            )
            if static_result.change.diff:
                typer.echo(
                    static_result.change.diff,
                    nl=not static_result.change.diff.endswith("\n"),
                )
            if static_result.wrote:
                typer.echo(f"Built reviewed {target} artefact.")
            elif static_result.change.kind is StaticChangeKind.UNCHANGED:
                typer.echo(
                    f"Reviewed {target} artefact is byte-identical; no files changed."
                )
            return
        output_plan = _service.plan_output_contracts(repository)
        if check:
            if json_output:
                typer.echo(
                    json.dumps(
                        _layer_build_document(
                            target,
                            output_plan.changes,
                            wrote=False,
                            check=True,
                            non_interactive=non_interactive,
                        ),
                        indent=2,
                    )
                )
            else:
                for output_change in output_plan.changes:
                    typer.echo(f"{output_change.kind.value}: {output_change.path}")
                    if output_change.diff:
                        typer.echo(
                            output_change.diff,
                            nl=not output_change.diff.endswith("\n"),
                        )
                typer.echo("Check complete; repository was not changed.")
            return
        output_result = _service.build_output_contracts(
            repository, replace_existing=replace_existing
        )
        if json_output:
            typer.echo(
                json.dumps(
                    _layer_build_document(
                        target,
                        output_result.changes,
                        wrote=output_result.wrote,
                        check=False,
                        non_interactive=non_interactive,
                    ),
                    indent=2,
                )
            )
            return
        for output_change in output_result.changes:
            typer.echo(f"{output_change.kind.value}: {output_change.path}")
            if output_change.diff:
                typer.echo(
                    output_change.diff,
                    nl=not output_change.diff.endswith("\n"),
                )
    except (OSError, ValueError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=2) from error
    changed = sum(
        item.kind is not ChangeKind.UNCHANGED for item in output_result.changes
    )
    if output_result.wrote:
        typer.echo(f"Built {changed} reviewed output-contract artefact(s).")
    else:
        typer.echo("Output contracts are already byte-identical; no files changed.")


@app.command("validate")
def validate_command(
    repository: RepositoryOption = Path("."),
    json_output: bool = typer.Option(
        False, "--json", help="Emit a stable machine-readable validation report."
    ),
) -> None:
    """Validate canonical readiness and the complete static bundle."""
    report = _service.validate_integration(repository)
    if json_output:
        typer.echo(
            json.dumps(
                {
                    "valid": report.valid,
                    "checked_files": report.checked_files,
                    "issues": [
                        {
                            "path": item.path,
                            "rule": item.rule,
                            "message": item.message,
                        }
                        for item in report.issues
                    ],
                },
                indent=2,
            )
        )
    elif report.valid:
        typer.echo(
            f"Valid SPLICE integration with {report.checked_files} managed files."
        )
    else:
        for issue in report.issues:
            typer.echo(f"{issue.path} [{issue.rule}]: {issue.message}", err=True)
    if not report.valid:
        raise typer.Exit(code=2)


@analysis_output_app.command("generate")
def generate_analysis_output_command(
    repository: RepositoryOption = Path("."),
    publish_directory: OptionalExistingPath = None,
    native_output_index: OptionalExistingPath = None,
    output_tree: OptionalExistingPath = None,
    run_metadata: OptionalExistingPath = None,
    sample_metadata: OptionalExistingPath = None,
    output_directory: OutputDirectoryOption = Path("."),
    checksum: str | None = typer.Option(
        None, help="Optional hashlib algorithm for completed published files."
    ),
    allow_unclassified: bool = typer.Option(
        False,
        help="Omit produced paths outside the reviewed contract instead of failing.",
    ),
) -> None:
    """Generate and schema-validate analysis_output.json for one completed run."""
    try:
        metadata = None
        if run_metadata is not None:
            loaded: object = json.loads(run_metadata.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise AnalysisOutputError("run metadata must contain a JSON object")
            metadata = loaded
        result = generate_analysis_output(
            repository,
            publish_directory=publish_directory,
            native_output_index=native_output_index,
            output_tree=output_tree,
            run_metadata=metadata,
            sample_metadata=sample_metadata,
            checksum_algorithm=checksum,
            allow_unclassified=allow_unclassified,
            output_directory=output_directory,
        )
    except (OSError, UnicodeError, ValueError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=2) from error
    typer.echo(
        f"Wrote valid {result.path} with {result.validation.record_count} "
        "output record(s)."
    )
    if result.unclassified:
        typer.echo(
            f"Omitted {len(result.unclassified)} explicitly allowed unclassified "
            "path(s)."
        )


@analysis_output_app.command("validate")
def validate_analysis_output_command(
    analysis_output: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=True,
            dir_okay=False,
            resolve_path=True,
            help="Existing analysis_output.json to validate.",
        ),
    ],
    repository: RepositoryOption = Path("."),
) -> None:
    """Validate an existing analysis_output.json against the static contract."""
    try:
        report = load_and_validate_analysis_output(repository, analysis_output)
    except (OSError, UnicodeError, ValueError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=2) from error
    if not report.valid:
        for issue in report.issues:
            typer.echo(
                f"{issue.json_pointer or '/'} [{issue.rule}]: {issue.message}",
                err=True,
            )
        raise typer.Exit(code=2)
    typer.echo(
        f"Valid analysis_output.json with {report.record_count} output record(s)."
    )


def _registry_document() -> dict[str, object]:
    mapping = dict(release().contracts)
    return {
        "tool": "nf-splice",
        "tool_version": __version__,
        "families": [
            {
                "id": item.id,
                "key": item.key,
                "title": item.title,
                "path": item.path,
                "kind": item.kind,
                "version": mapping[item.id],
                "known_revisions": list(item.revisions),
            }
            for item in families()
        ],
    }


@schema_app.command("list")
def schema_list_command(
    json_output: bool = typer.Option(
        False, "--json", help="Emit the stable machine-readable registry view."
    ),
) -> None:
    """List the contract families and revisions emitted by this release."""
    document = _registry_document()
    if json_output:
        typer.echo(json.dumps(document, indent=2))
        return
    entries = document["families"]
    assert isinstance(entries, list)
    for item in entries:
        typer.echo(f"{item['path']}: {item['id']} {item['version']}")


@schema_app.command("show")
def schema_show_command(
    contract: str = typer.Argument(help="Family URI, key or final file name."),
    revision: str | None = typer.Option(None, help="Contract revision to show."),
) -> None:
    """Print the packaged formal definition of one family revision."""
    try:
        typer.echo(json.dumps(meta_schema(family(contract).id, revision), indent=2))
    except ContractRegistryError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=2) from error


def _report_payload(path: Path, report: object) -> dict[str, object]:
    issues = getattr(report, "issues", ())
    return {
        "path": path.as_posix(),
        "family": getattr(report, "family_id", None),
        "revision": getattr(report, "revision", None),
        "valid": getattr(report, "valid", False),
        "issues": [
            {"pointer": item.json_pointer, "rule": item.rule, "message": item.message}
            for item in issues
        ],
    }


def _validate_contract_file(path: Path, contract: str | None) -> dict[str, object]:
    try:
        loaded: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return {
            "path": path.as_posix(),
            "family": None,
            "revision": None,
            "valid": False,
            "issues": [{"pointer": "", "rule": "json", "message": str(error)}],
        }
    report = validate_contract_document(
        loaded, family(contract).id if contract else None, filename=path.name
    )
    return _report_payload(path, report)


def _echo_contract_reports(reports: list[dict[str, object]], json_output: bool) -> None:
    if json_output:
        typer.echo(json.dumps({"reports": reports}, indent=2))
    else:
        for report in reports:
            state = "valid" if report["valid"] else "invalid"
            label = f"{report['family'] or 'unknown family'} {report['revision'] or ''}"
            typer.echo(f"{report['path']}: {state} ({label.rstrip()})")
            issues = report["issues"]
            assert isinstance(issues, list)
            for issue in issues:
                typer.echo(
                    f"  {issue['pointer'] or '/'} [{issue['rule']}]: "
                    f"{issue['message']}",
                    err=True,
                )
    if not all(report["valid"] for report in reports):
        raise typer.Exit(code=2)


@schema_app.command("validate")
def schema_validate_command(
    document: Annotated[
        Path,
        typer.Argument(
            exists=True, dir_okay=False, resolve_path=True, help="JSON document."
        ),
    ],
    contract: str | None = typer.Option(
        None,
        "--family",
        help="Family URI, key or file name; detected from the document by default.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit a JSON report."),
) -> None:
    """Validate one document offline against its packaged contract definition."""
    try:
        reports = [_validate_contract_file(document, contract)]
    except ContractRegistryError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=2) from error
    _echo_contract_reports(reports, json_output)


@schema_app.command("check")
def schema_check_command(
    repository: RepositoryOption = Path("."),
    against: Annotated[
        Path | None,
        typer.Option(
            exists=True,
            dir_okay=False,
            resolve_path=True,
            help="Earlier formal definition to compare with --family for breaks.",
        ),
    ] = None,
    contract: str | None = typer.Option(None, "--family", help="Family to compare."),
    json_output: bool = typer.Option(False, "--json", help="Emit a JSON report."),
) -> None:
    """Check every published contract file in splice/, or compare revisions."""
    if against is not None:
        if contract is None:
            typer.echo("--against requires --family", err=True)
            raise typer.Exit(code=2)
        old = json.loads(against.read_text(encoding="utf-8"))
        findings = breaking_changes(old, meta_schema(family(contract).id))
        payload = {
            "family": family(contract).id,
            "breaking": [
                {
                    "pointer": item.json_pointer,
                    "kind": item.kind,
                    "message": item.message,
                }
                for item in findings
            ],
        }
        if json_output:
            typer.echo(json.dumps(payload, indent=2))
        else:
            for item in findings:
                typer.echo(f"{item.json_pointer or '/'} [{item.kind}]: {item.message}")
            typer.echo(f"{len(findings)} breaking change(s).")
        if findings:
            raise typer.Exit(code=2)
        return
    splice = repository / "splice"
    reports: list[dict[str, object]] = [
        _validate_contract_file(splice / item.path, item.id)
        if (splice / item.path).is_file()
        else {
            "path": (splice / item.path).as_posix(),
            "family": item.id,
            "revision": None,
            "valid": False,
            "issues": [{"pointer": "", "rule": "missing", "message": "not published"}],
        }
        for item in families()
    ]
    _echo_contract_reports(reports, json_output)


@app.command("tui")
def tui_command(repository: RepositoryOption = Path(".")) -> None:
    """Open the terminal workspace and guided layer-review forms."""
    NfSpliceApp(_service.inspect(repository), repository, _service).run()


def main() -> None:
    """Run the nf-splice command-line interface."""
    app()
