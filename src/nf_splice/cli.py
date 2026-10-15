"""Command-line entry point for nf-splice (file-first authoring, 0.3.0)."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Annotated, Any, ParamSpec, TypeVar

import typer
import yaml  # type: ignore[import-untyped]

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
from nf_splice.domain.audit import ActorKind, ChangeOrigin
from nf_splice.drafts import DraftConflictError, DraftStoreError
from nf_splice.inspectors.containers import classify_reference, nextflow_cache_filename
from nf_splice.layers import ChangeContext, LayerError, confirm_values
from nf_splice.layers import components as component_layer
from nf_splice.layers import execution as execution_layer
from nf_splice.layers import inputs as input_layer
from nf_splice.layers import outputs as output_layer
from nf_splice.layers import provenance as provenance_layer
from nf_splice.layers.base import LAYERS, layer_spec
from nf_splice.layers.bundle import set_identity_fields, validate_bundle_draft
from nf_splice.runtime import (
    AnalysisOutputError,
    generate_analysis_output,
    load_and_validate_analysis_output,
)
from nf_splice.services.audit import (
    audit_directory,
    read_private,
    resolve_actor,
    suggest_git_identity,
)
from nf_splice.services.containers import ContainerServiceError
from nf_splice.services.lifecycle import (
    LifecycleError,
    plan_promotion,
    promote,
    recover,
    validate_bundle,
    validate_layer,
)
from nf_splice.services.workspace import (
    dumps,
    initialise,
    inspect_layer,
    workspace_status,
)

app = typer.Typer(
    name="nf-splice",
    help="Author and maintain a SPLICE workflow bundle from editable drafts.",
    add_completion=False,
    no_args_is_help=True,
)
analysis_output_app = typer.Typer(
    help="Generate or validate the per-job analysis_output.json file.",
    no_args_is_help=True,
)
app.add_typer(analysis_output_app, name="analysis-output")
schema_app = typer.Typer(
    help="List, show and validate the five workflow-bundle contract families.",
    no_args_is_help=True,
)
app.add_typer(schema_app, name="schema")
audit_app = typer.Typer(
    help="Inspect actor attribution and the private local audit store.",
    no_args_is_help=True,
)
app.add_typer(audit_app, name="audit")
draft_app = typer.Typer(
    help="List, inspect, validate, edit, confirm and promote draft files.",
    no_args_is_help=True,
)
app.add_typer(draft_app, name="draft")
containers_app = typer.Typer(
    help="Classify container references and verify downloadable images.",
    no_args_is_help=True,
)
app.add_typer(containers_app, name="containers")
agent_app = typer.Typer(
    help="Optional AI assistance: tools, runs, proposals and human approval.",
    no_args_is_help=True,
)
app.add_typer(agent_app, name="agent")
preview_app = typer.Typer(
    help="Show derived, non-authoritative previews of published files.",
    no_args_is_help=True,
)
app.add_typer(preview_app, name="preview")

RepositoryOption = Annotated[
    Path,
    typer.Option(
        "--repository",
        "-r",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Pipeline repository root.",
    ),
]


def _existing_path(help_text: str) -> Any:
    """An optional existing-path option with help text."""
    return typer.Option(exists=True, resolve_path=True, help=help_text)


ExampleOutputTreeOption = Annotated[
    Path | None,
    _existing_path(
        "Outputs: example results directory, or a saved 'ls -R'/'tree' listing "
        "of one, to discover output candidates from."
    ),
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
SetOption = Annotated[
    list[str] | None,
    typer.Option("--set", help="Repeatable explicit review value KEY=VALUE."),
]
JsonOption = Annotated[bool, typer.Option("--json", help="Emit stable JSON.")]
LayerArgument = Annotated[
    str,
    typer.Argument(
        help="Layer: bundle, inputs, outputs, components, execution-profiles, "
        "provenance."
    ),
]
_ERRORS = (
    OSError,
    UnicodeError,
    ValueError,
    LayerError,
    LifecycleError,
    DraftStoreError,
    DraftConflictError,
)
_STATE: dict[str, str | None] = {"actor": None}
T = TypeVar("T")
P = ParamSpec("P")


def _context(origin: ChangeOrigin = ChangeOrigin.MANUAL_CLI) -> ChangeContext:
    actor = resolve_actor(_STATE["actor"])
    return ChangeContext(actor=actor, origin=origin)


def _run(action: Callable[[], T]) -> T:
    try:
        return action()
    except DraftConflictError as error:
        typer.echo(f"conflict: {error}", err=True)
        for conflict in error.conflicts:
            typer.echo(
                f"  {conflict.path or '/'}: planned against {conflict.expected!r}, "
                f"now {conflict.actual!r}",
                err=True,
            )
        raise typer.Exit(code=2) from error
    except _ERRORS as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=2) from error


def _call(func: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    return _run(lambda: func(*args, **kwargs))


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
    actor: str | None = typer.Option(
        None,
        "--actor",
        help="Public actor label recorded with review events (never an e-mail).",
        envvar="NF_SPLICE_ACTOR",
    ),
) -> None:
    """Author and maintain a SPLICE workflow bundle from editable drafts."""
    _STATE["actor"] = actor


def _value(text: str) -> Any:
    stripped = text.strip()
    if stripped[:1] in {"[", "{"} or stripped in {"true", "false", "null"}:
        return json.loads(stripped)
    return text


def _assignments(values: list[str] | None) -> list[tuple[str, str]]:
    result = []
    for item in values or []:
        left, separator, right = item.partition("=")
        if not separator or not left:
            raise LayerError(f"--set expects KEY=VALUE, got {item!r}")
        result.append((left.strip(), right))
    return result


def _issues_report(layer: str) -> Callable[[Path], int]:
    def report(repository: Path) -> int:
        validation = validate_layer(repository, layer)
        for item in validation.issues:
            typer.echo(
                f"{item.severity.value}: {item.path}#{item.pointer or '/'} "
                f"[{item.code}] {item.message}",
                err=True,
            )
        return len(validation.errors)

    return report


def _finish(repository: Path, layer: str, saved: str) -> None:
    errors = _issues_report(layer)(repository)
    if errors:
        typer.echo(f"{saved}; {errors} blocking issue(s) remain.", err=True)
        raise typer.Exit(code=2)
    typer.echo(f"{saved}; the {layer} draft is ready to promote.")


# ---------------------------------------------------------------- inspection


@app.command("inspect")
def inspect_command(
    repository: RepositoryOption = Path("."), json_output: JsonOption = False
) -> None:
    """Inspect pipeline evidence and the splice/ tree (read-only)."""
    status = workspace_status(repository)
    if json_output:
        typer.echo(dumps(status.to_json()))
        return
    inspection = status.inspection
    typer.echo(f"Repository: {inspection.root}")
    typer.echo(f"Revision: {inspection.repository_revision or 'not detected'}")
    typer.echo(f"SPLICE tree: {inspection.splice_tree.state.value}")
    typer.echo(f"Evidence: {len(inspection.evidence)}")
    for item in status.evidence_counts:
        typer.echo(f"  {item.kind.value}: {item.count}")
    if status.warnings:
        typer.echo("Warnings:")
        for warning in status.warnings:
            typer.echo(f"  - {warning}")


@app.command("status")
def status_command(
    repository: RepositoryOption = Path("."), json_output: JsonOption = False
) -> None:
    """Show each layer's draft-derived status (read-only)."""
    status = workspace_status(repository)
    if json_output:
        typer.echo(dumps(status.to_json()))
        return
    typer.echo(f"Repository: {status.inspection.root}")
    typer.echo(f"SPLICE tree: {status.inspection.splice_tree.state.value}")
    typer.echo("Layers:")
    for item in status.artifacts:
        finals = ", ".join(f"{final.path}={final.state.value}" for final in item.finals)
        typer.echo(
            f"  {item.layer}: {item.state.value}; errors={item.errors}; "
            f"warnings={item.warnings}; finals: {finals}"
        )
    for warning in status.warnings:
        typer.echo(f"warning: {warning}")
    typer.echo(f"Bundle ready to publish: {'yes' if status.ready else 'no'}")


# ---------------------------------------------------------------- init


@app.command("init")
def init_command(
    repository: RepositoryOption = Path("."),
    name: str | None = typer.Option(None, help="Reviewed pipeline name."),
    pipeline_version: str | None = typer.Option(
        None, "--pipeline-version", help="Reviewed pipeline version."
    ),
    repository_url: str | None = typer.Option(None, help="Reviewed repository URL."),
    release_url: str | None = typer.Option(None, help="Optional release URL."),
    description: str | None = typer.Option(None, help="Concise description."),
    title: str | None = typer.Option(None, help="Display title."),
    licence: str | None = typer.Option(None, help="Licence identifier."),
    example_output_tree: ExampleOutputTreeOption = None,
    contract_version: str | None = typer.Option(
        None, help="Reviewed analysis-output schema version (X.Y.Z)."
    ),
    accept_detected: bool = typer.Option(
        False,
        help="Explicitly confirm every unanimous detected identity value.",
    ),
    json_output: JsonOption = False,
) -> None:
    """Create absent drafts from evidence; existing drafts are never replaced."""
    explicit = {
        key: value
        for key, value in {
            "name": name,
            "version": pipeline_version,
            "repository_url": repository_url,
            "release_url": release_url,
            "description": description,
            "title": title,
            "licence": licence,
        }.items()
        if value is not None
    }
    report = _run(
        lambda: initialise(
            repository,
            _context(),
            identity=explicit,
            accept_detected=accept_detected,
            example_output_tree=example_output_tree,
            contract_version=contract_version,
        )
    )
    if json_output:
        typer.echo(
            dumps(
                {
                    "created": list(report.created),
                    "preserved": list(report.preserved),
                    "identity_conflicts": list(report.identity.conflicts),
                    "confirmed": list(report.confirmed),
                    "notes": list(report.notes),
                }
            )
        )
        return
    for layer in report.created:
        typer.echo(f"created: {layer_spec(layer).draft}")
    for layer in report.preserved:
        typer.echo(f"preserved existing draft: {layer_spec(layer).draft}")
    for pointer in report.identity.conflicts:
        typer.echo(f"conflicting evidence for {pointer}; choose a value", err=True)
    for note in report.notes:
        typer.echo(f"note: {note}")
    typer.echo("Drafts are the editable source; run `nf-splice status` next.")


# ---------------------------------------------------------------- configure


def _configure_identity(
    repository: Path,
    assignments: list[tuple[str, str]],
    confirm: bool,
    approve_publication: bool,
) -> None:
    changes: dict[str, Any] = {key: _value(value) for key, value in assignments}
    if approve_publication:
        changes["maintainers_publication_approved"] = True
    if changes:
        _run(lambda: set_identity_fields(repository, changes, _context()))
    if confirm:
        pending = [
            item.pointer
            for item in validate_bundle_draft(repository).issues
            if item.code == "unconfirmed_detected_value"
        ]
        if pending:
            _run(lambda: confirm_values(repository, "bundle", pending, _context()))
    _finish(repository, "bundle", "Identity draft saved")


def _access_for(value: str) -> list[str]:
    return [
        item.strip()
        for item in value.split(",")
        if item.strip() and item.strip() != "none"
    ]


def _configure_inputs(
    repository: Path,
    assignments: list[tuple[str, str]],
    visibility: list[tuple[str, str]],
    decision_file: Path | None,
    reimport: bool,
) -> None:
    if not read_layer_exists(repository, "inputs"):
        _run(lambda: input_layer.import_inputs(repository))
    if reimport:
        _run(lambda: input_layer.apply_reimport(repository, _context()))
    reviews: list[dict[str, Any]] = []
    if decision_file is not None:
        loaded = json.loads(decision_file.read_text(encoding="utf-8"))
        if not isinstance(loaded, list):
            raise typer.BadParameter("input decision file must be a JSON array")
        reviews.extend(loaded)
    reviews.extend(
        {"parameter": name, "editable_by": value} for name, value in assignments
    )
    hidden = dict(visibility)
    for review in reviews:
        name = str(review["parameter"]).removeprefix("input:")
        value = review.get("editable_by", "")
        principals = value if isinstance(value, list) else _access_for(str(value))
        selected = hidden.pop(name, review.get("visibility"))
        _call(
            input_layer.set_access,
            repository,
            [name],
            principals,
            _context(),
            visibility=selected,
        )
    for name, value in hidden.items():
        current = _parameter_access(repository, name)
        _call(
            input_layer.set_access,
            repository,
            [name],
            current,
            _context(),
            visibility=value,
        )
    _finish(repository, "inputs", "Inputs draft saved")


def read_layer_exists(repository: Path, layer: str) -> bool:
    return (repository / layer_spec(layer).draft).exists()


def _parameter_access(repository: Path, name: str) -> list[str]:
    from nf_splice.layers.base import read_layer

    state = read_layer(repository, "inputs")
    if state.draft is None:
        return []
    for parameter in input_layer.iter_parameters(state.draft.data):
        if parameter.name == name:
            return list(parameter.editable_by or ())
    raise LayerError(f"unknown parameter {name!r}")


def _output_reviews(repository: Path, assignments: list[tuple[str, str]]) -> None:
    candidates = {item.id: item for item in output_layer.pending_candidates(repository)}
    fields: dict[str, dict[str, str]] = {}
    for left, value in assignments:
        candidate_id, dot, field = left.rpartition(".")
        if not dot or candidate_id not in candidates:
            raise LayerError("--set must use PENDING_CANDIDATE_ID.FIELD=VALUE")
        fields.setdefault(candidate_id, {})[field] = value
    for candidate_id, assigned in fields.items():
        candidate = candidates[candidate_id]
        if assigned.pop("action", "accept") == "reject":
            _call(
                output_layer.reject_output,
                repository,
                candidate_id,
                assigned.get("reason", ""),
                _context(),
            )
            continue
        output: dict[str, Any] = {
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
            if field in {"formats", "scopes", "entity_types", "path_patterns"}:
                output[field] = [part for part in value.split(",") if part]
            elif field != "reason":
                output[field] = value
        _call(output_layer.accept_output, repository, candidate_id, output, _context())


def _export(path: Path | None, items: Iterable[Any]) -> None:
    if path is None:
        return
    content = (
        dumps(
            [
                item.model_dump(mode="json") if hasattr(item, "model_dump") else item
                for item in items
            ]
        )
        + "\n"
    )
    if str(path) == "-":
        typer.echo(content, nl=False)
    else:
        path.write_text(content, encoding="utf-8")


def _component_reviews(repository: Path, assignments: list[tuple[str, str]]) -> None:
    grouped: dict[str, dict[str, str]] = {}
    pending = {item.id for item in component_layer.pending_components(repository)}
    for left, value in assignments:
        candidate_id = next(
            (
                item
                for item in sorted(pending, key=len, reverse=True)
                if left == item or left.startswith(item + ".")
            ),
            None,
        )
        if candidate_id is None:
            raise LayerError(f"unknown pending component in {left!r}")
        field = left[len(candidate_id) + 1 :] if left != candidate_id else "action"
        grouped.setdefault(candidate_id, {})[field] = value
    for candidate_id, fields in grouped.items():
        if fields.get("action") == "reject":
            _call(
                component_layer.reject_component,
                repository,
                candidate_id,
                fields.get("reason", "rejected"),
                _context(),
            )
            continue
        sources: dict[str, str] = {
            key: fields[key]
            for key in ("docker", "singularity", "apptainer")
            if key in fields
        }
        _call(
            component_layer.accept_component,
            repository,
            candidate_id,
            _context(),
            version=fields.get("version"),
            sources=sources or None,
        )


def _profile_reviews(repository: Path, assignments: list[tuple[str, str]]) -> None:
    grouped: dict[str, dict[str, str]] = {}
    pending = {item.id for item in execution_layer.pending_profiles(repository)}
    for left, value in assignments:
        candidate_id = next(
            (
                item
                for item in sorted(pending, key=len, reverse=True)
                if left.startswith(item + ".")
            ),
            None,
        )
        if candidate_id is None:
            raise LayerError(f"unknown pending profile in {left!r}")
        grouped.setdefault(candidate_id, {})[left[len(candidate_id) + 1 :]] = value
    for candidate_id, fields in grouped.items():
        if fields.get("action") == "reject":
            _call(
                execution_layer.reject_profile,
                repository,
                candidate_id,
                fields.get("reason", ""),
                _context(),
            )
            continue
        generate: dict[str, dict[str, Any]] | None = (
            {"process": {}, "user_params": {}, "platform_params": {}}
            if fields.get("generate") == "true"
            else None
        )
        _call(
            execution_layer.review_profile,
            repository,
            candidate_id,
            _context(),
            profile_type=fields.get("type", ""),
            description=fields.get("description", ""),
            executor=fields.get("executor", ""),
            container_engine=fields.get("container_engine", ""),
            config_source=fields.get("config_source"),
            generate=generate,
        )


@app.command("configure")
def configure_command(
    layer: LayerArgument,
    repository: RepositoryOption = Path("."),
    set_field: SetOption = None,
    visibility: Annotated[
        list[str] | None,
        typer.Option("--visibility", help="Inputs: NAME=standard|advanced|hidden."),
    ] = None,
    decision_file: Annotated[
        Path | None,
        _existing_path(
            "Batch review file: a YAML 'actions' list for outputs, or a JSON "
            "array of parameter policies for inputs."
        ),
    ] = None,
    example_output_tree: ExampleOutputTreeOption = None,
    publish_directory: Annotated[
        Path | None,
        _existing_path(
            "Outputs: publish directory of a completed job to discover output "
            "candidates from."
        ),
    ] = None,
    contract_version: str | None = typer.Option(
        None, help="Outputs: reviewed analysis-output schema version X.Y.Z."
    ),
    export_unresolved: Annotated[
        Path | None,
        typer.Option(help="Write pending candidates as JSON ('-' for stdout)."),
    ] = None,
    accept_detected: bool = typer.Option(
        False, help="Identity/components: explicitly accept unambiguous evidence."
    ),
    approve_maintainer_publication: bool = typer.Option(
        False, help="Identity: approve publishing maintainer contacts."
    ),
    require_downloadable: Annotated[
        str | None,
        typer.Option(
            help="Components: true/false whether images must be downloadable."
        ),
    ] = None,
    default_profile: str | None = typer.Option(
        None, "--default", help="Execution profiles: the reviewed default profile ID."
    ),
    slurm_default: bool = typer.Option(
        False, help="Execution profiles: add the generated SPLICE Slurm candidate."
    ),
    strategy: str | None = typer.Option(
        None, help="Provenance: include, enriched or generated."
    ),
    reimport: bool = typer.Option(
        False, help="Inputs: apply a conflict-free nextflow_schema.json re-import."
    ),
) -> None:
    """Review one layer by targeted, attributed edits to its draft."""
    name = _run(lambda: layer_spec("bundle" if layer == "identity" else layer).name)
    assignments = _assignments(set_field)
    if name == "bundle":
        _configure_identity(
            repository, assignments, accept_detected, approve_maintainer_publication
        )
        return
    if name == "inputs":
        _configure_inputs(
            repository, assignments, _assignments(visibility), decision_file, reimport
        )
        return
    if name == "outputs":
        _run(
            lambda: output_layer.discover_outputs(
                repository,
                example_output_tree=example_output_tree,
                publish_directory=publish_directory,
            )
        )
        if contract_version is not None:
            _run(
                lambda: output_layer.set_contract_version(
                    repository, contract_version, _context()
                )
            )
        if decision_file is not None:
            loaded = yaml.safe_load(decision_file.read_text(encoding="utf-8"))
            _run(
                lambda: output_layer.apply_decision_file(repository, loaded, _context())
            )
        _output_reviews(repository, assignments)
        _export(export_unresolved, output_layer.pending_candidates(repository))
        _finish(repository, "outputs", "Outputs draft saved")
        return
    if name == "components":
        _run(lambda: component_layer.discover_components(repository))
        if accept_detected:
            _run(
                lambda: component_layer.accept_unambiguous_components(
                    repository, _context()
                )
            )
        _component_reviews(repository, assignments)
        if require_downloadable is not None:
            _run(
                lambda: component_layer.set_image_policy(
                    repository, require_downloadable.lower() == "true", _context()
                )
            )
        _export(
            export_unresolved,
            [
                {
                    "id": item.id,
                    "problems": list(item.problems),
                    "proposed_sources": dict(item.proposed_sources),
                }
                for item in component_layer.pending_components(repository)
            ],
        )
        _finish(repository, "components", "Components draft saved")
        return
    if name == "execution-profiles":
        _run(lambda: execution_layer.discover_execution(repository))
        _profile_reviews(repository, assignments)
        if slurm_default:
            _run(
                lambda: execution_layer.add_slurm_default_candidate(
                    repository, _context()
                )
            )
        if default_profile is not None:
            _run(
                lambda: execution_layer.set_default_profile(
                    repository, default_profile, _context()
                )
            )
        _export(export_unresolved, execution_layer.pending_profiles(repository))
        _finish(repository, "execution-profiles", "Execution-profile draft saved")
        return
    if strategy == "include":
        _run(lambda: provenance_layer.choose_include(repository, _context()))
    elif strategy == "enriched":
        _run(lambda: provenance_layer.prepare_enrichment(repository, _context()))
    elif strategy == "generated":
        _run(lambda: provenance_layer.generate_minimal(repository, _context()))
    elif strategy is not None:
        raise typer.BadParameter("strategy must be include, enriched or generated")
    analysis = provenance_layer.analyse_ro_crate(repository)
    for finding in analysis.findings:
        typer.echo(
            f"{finding.severity.value}: ro-crate {finding.pointer} "
            f"[{finding.code}] {finding.message}"
        )
    _finish(repository, "provenance", "Provenance draft saved")


# ---------------------------------------------------------------- drafts


@draft_app.command("list")
def draft_list_command(
    repository: RepositoryOption = Path("."), json_output: JsonOption = False
) -> None:
    """List every draft with its derived state (read-only)."""
    status = workspace_status(repository)
    if json_output:
        typer.echo(dumps([item.to_json() for item in status.artifacts]))
        return
    for item in status.artifacts:
        typer.echo(
            f"{item.draft}: {item.state.value} "
            f"(errors={item.errors}, warnings={item.warnings})"
        )


@draft_app.command("inspect")
def draft_inspect_command(
    layer: LayerArgument,
    repository: RepositoryOption = Path("."),
    json_output: JsonOption = False,
) -> None:
    """Show per-field issues for one draft (read-only)."""
    report = _run(lambda: inspect_layer(repository, layer))
    if json_output:
        typer.echo(dumps(report))
    else:
        typer.echo(f"{report['draft']}: {'ready' if report['ready'] else 'not ready'}")
        for item in report["issues"]:
            typer.echo(_issue_line(item))
    if not report["ready"]:
        raise typer.Exit(code=2)


@draft_app.command("validate")
def draft_validate_command(
    layer: Annotated[
        str | None, typer.Argument(help="Layer; all when omitted.")
    ] = None,
    repository: RepositoryOption = Path("."),
    json_output: JsonOption = False,
) -> None:
    """Validate one or all drafts (read-only)."""
    names = [layer_spec(layer).name] if layer else [spec.name for spec in LAYERS]
    reports = [_call(inspect_layer, repository, name) for name in names]
    if json_output:
        typer.echo(
            dumps({"valid": all(item["ready"] for item in reports), "layers": reports})
        )
    else:
        for report in reports:
            typer.echo(
                f"{report['draft']}: {'ready' if report['ready'] else 'not ready'}"
            )
            for item in report["issues"]:
                typer.echo(_issue_line(item))
    if not all(item["ready"] for item in reports):
        raise typer.Exit(code=2)


@draft_app.command("diff")
def draft_diff_command(
    layer: Annotated[
        str | None, typer.Argument(help="Layer; whole bundle when omitted.")
    ] = None,
    repository: RepositoryOption = Path("."),
    json_output: JsonOption = False,
) -> None:
    """Show the final-file diff promotion would produce (read-only)."""
    plan = _run(lambda: plan_promotion(repository, layer))
    _echo_plan(plan.to_json(), json_output)


def _issue_line(item: dict[str, Any]) -> str:
    return (
        f"  {item['severity']}: {item['pointer'] or '/'} "
        f"[{item['code']}] {item['message']}"
    )


def _echo_plan(document: dict[str, Any], json_output: bool) -> None:
    if json_output:
        typer.echo(dumps(document))
    else:
        for item in document["blockers"]:
            typer.echo(
                f"blocked: {item['layer']}{item['pointer']}: {item['message']}",
                err=True,
            )
        for item in document["changes"]:
            typer.echo(f"{item['kind']}: splice/{item['path']} ({item['state']})")
            if item["diff"]:
                typer.echo(item["diff"], nl=not item["diff"].endswith("\n"))
    if not document["ready"]:
        raise typer.Exit(code=2)


@draft_app.command("confirm")
def draft_confirm_command(
    layer: LayerArgument,
    pointers: Annotated[list[str], typer.Argument(help="JSON pointers to confirm.")],
    repository: RepositoryOption = Path("."),
) -> None:
    """Record deliberate confirmation of current (detected) draft values."""
    event = _run(
        lambda: confirm_values(repository, layer_spec(layer).name, pointers, _context())
    )
    typer.echo(f"Confirmed {len(pointers)} value(s) ({event.id}).")


@draft_app.command("edit")
def draft_edit_command(
    layer: LayerArgument,
    patch: Annotated[
        Path,
        typer.Option(
            exists=True,
            dir_okay=False,
            resolve_path=True,
            help="JSON list of patch operations with expected values.",
        ),
    ],
    repository: RepositoryOption = Path("."),
    apply: bool = typer.Option(False, "--apply", help="Write the approved edit."),
) -> None:
    """Plan (default) or apply a JSON-pointer patch to one draft."""
    from nf_splice.services.workspace import apply_patch, plan_patch

    operations = json.loads(patch.read_text(encoding="utf-8"))
    result = _run(
        lambda: (apply_patch if apply else plan_patch)(
            repository, layer_spec(layer).name, operations, _context()
        )
    )
    typer.echo(result.diff or "No change.", nl=not result.diff.endswith("\n"))
    typer.echo("Applied." if result.wrote else "Preview only; pass --apply to write.")


@draft_app.command("sync-identity")
def draft_sync_identity_command(repository: RepositoryOption = Path(".")) -> None:
    """Update the inputs draft's identity envelope from bundle.draft.yaml."""
    result = _run(lambda: input_layer.sync_identity(repository, _context()))
    typer.echo(result.diff or "Identity envelope already current.")


@draft_app.command("promote")
def draft_promote_command(
    layer: Annotated[
        str | None, typer.Argument(help="Layer; whole bundle when omitted.")
    ] = None,
    repository: RepositoryOption = Path("."),
    replace_existing: bool = typer.Option(
        False, help="Replace differing published files after review."
    ),
    overwrite_edited: Annotated[
        list[str] | None,
        typer.Option(help="Published path whose external edit may be overwritten."),
    ] = None,
    json_output: JsonOption = False,
) -> None:
    """Promote one ready layer, or publish the whole ready bundle."""
    result = _run(
        lambda: promote(
            repository,
            layer,
            _context(),
            replace_existing=replace_existing,
            overwrite_edited=overwrite_edited or (),
        )
    )
    if json_output:
        typer.echo(dumps(result.plan.to_json() | {"wrote": list(result.wrote)}))
        return
    for path in result.wrote:
        typer.echo(f"wrote: splice/{path}")
    typer.echo(
        "Published files are up to date." if not result.wrote else "Promotion complete."
    )


@draft_app.command("recover")
def draft_recover_command(repository: RepositoryOption = Path(".")) -> None:
    """Restore the previous release after an interrupted publication."""
    result = _run(lambda: recover(repository))
    typer.echo(
        f"Restored {len(result.restored)} file(s)."
        if result.recovered
        else "Nothing to recover."
    )


# ---------------------------------------------------------------- plan/build/validate


@app.command("plan")
def plan_command(
    target: Annotated[str, typer.Argument(help="'all' or a layer name.")] = "all",
    repository: RepositoryOption = Path("."),
    json_output: JsonOption = False,
) -> None:
    """Preview promotion/publication changes and blockers (read-only)."""
    plan = _run(
        lambda: plan_promotion(
            repository, None if target in {"all", "bundle"} else target
        )
    )
    _echo_plan(plan.to_json(), json_output)
    if not json_output:
        typer.echo("Plan complete; repository was not changed.")


@app.command("build")
def build_command(
    target: Annotated[str, typer.Argument(help="'all', 'bundle' or a layer name.")],
    repository: RepositoryOption = Path("."),
    check: bool = typer.Option(False, help="Show changes without writing."),
    replace_existing: bool = typer.Option(
        False, help="Replace differing published files after review."
    ),
    overwrite_edited: Annotated[
        list[str] | None,
        typer.Option(help="Published path whose external edit may be overwritten."),
    ] = None,
    non_interactive: bool = typer.Option(
        False, "--non-interactive", help="Never prompt; fail on blockers."
    ),
    json_output: JsonOption = False,
) -> None:
    """Promote validated drafts to published files (whole bundle for 'all')."""
    layer = None if target in {"all", "bundle"} else target
    if check:
        plan = _run(lambda: plan_promotion(repository, layer))
        document = plan.to_json() | {
            "wrote": [],
            "check": True,
            "non_interactive": non_interactive,
        }
        _echo_plan(document, json_output)
        if not json_output:
            typer.echo("Check complete; repository was not changed.")
        return
    result = _run(
        lambda: promote(
            repository,
            layer,
            _context(),
            replace_existing=replace_existing,
            overwrite_edited=overwrite_edited or (),
        )
    )
    if json_output:
        typer.echo(
            dumps(
                result.plan.to_json()
                | {
                    "wrote": list(result.wrote),
                    "check": False,
                    "non_interactive": non_interactive,
                }
            )
        )
        return
    for change in result.plan.changes:
        typer.echo(f"{change.kind}: splice/{change.path}")
    typer.echo(
        f"Built {len(result.wrote)} file(s)."
        if result.wrote
        else "Published files are byte-identical; no files changed."
    )


@app.command("validate")
def validate_command(
    repository: RepositoryOption = Path("."), json_output: JsonOption = False
) -> None:
    """Validate the published bundle, cross-file identity and lock (read-only)."""
    report = validate_bundle(repository)
    if json_output:
        typer.echo(
            dumps(
                {
                    "valid": report.valid,
                    "checked_files": report.checked_files,
                    "issues": [item.to_json() for item in report.issues],
                }
            )
        )
    elif report.valid:
        typer.echo(
            f"Valid SPLICE bundle ({report.checked_files} contract files checked)."
        )
        for item in report.issues:
            typer.echo(f"warning: {item.path} [{item.rule}] {item.message}")
    else:
        for item in report.issues:
            typer.echo(
                f"{item.severity.value}: {item.path} [{item.rule}] {item.message}",
                err=True,
            )
    if not report.valid:
        raise typer.Exit(code=2)


@app.command("assess")
def assess_command(
    repository: RepositoryOption = Path("."),
    example_output: Annotated[
        list[Path] | None,
        typer.Option(
            "--example-output",
            exists=True,
            resolve_path=True,
            help="Results of one completed run: a directory, a saved 'ls -R'/'tree' "
            "listing or an output index. Repeatable; read-only evidence.",
        ),
    ] = None,
    allow: Annotated[
        list[str] | None,
        typer.Option(
            "--allow",
            help="Permit an optional check's side effects: external_tools, "
            "run_nextflow or network. Repeatable.",
        ),
    ] = None,
    write_analysis_output: Annotated[
        Path | None,
        typer.Option(
            file_okay=False,
            resolve_path=True,
            help="Directory for the analysis_output.json generated from each example.",
        ),
    ] = None,
    json_output: JsonOption = False,
) -> None:
    """Report contract validity, observed outputs and route coverage separately."""
    from nf_splice.services.coverage import assess
    from nf_splice.services.coverage import dumps as dump_assessment

    permitted = set(allow or [])
    unknown = permitted - {"external_tools", "run_nextflow", "network"}
    if unknown:
        raise typer.BadParameter(f"unknown permission(s): {', '.join(sorted(unknown))}")
    if write_analysis_output is not None:
        write_analysis_output.mkdir(parents=True, exist_ok=True)
    result = _run(
        lambda: assess(
            repository,
            examples=example_output or [],
            permitted=permitted,
            analysis_output_directory=write_analysis_output,
        )
    )
    document = result.to_json()
    observed = document["observed_output_compatibility"]
    failed = result.contract.get("status") == "invalid" or observed["status"] == (
        "incompatible"
    )
    if json_output:
        typer.echo(dump_assessment(result), nl=False)
        if failed:
            raise typer.Exit(code=2)
        return
    contract = document["contract_validity"]
    typer.echo(f"Contract validity: {contract['status']}")
    for item in contract.get("issues", [])[:20]:
        typer.echo(f"  {item if isinstance(item, str) else item['message']}")
    typer.echo(f"Observed-output compatibility: {observed['status']}")
    for example in observed["examples"]:
        reconciliation = example["reconciliation"]
        typer.echo(
            f"  {reconciliation['example']}: {reconciliation['entries']} entries, "
            f"{sum(reconciliation['classified'].values())} classified, "
            f"{len(reconciliation['unclassified'])} unclassified, "
            f"{len(reconciliation['ambiguous'])} ambiguous; "
            f"analysis_output.json {example['analysis_output']['status']}"
        )
        for path in reconciliation["unclassified"][:20]:
            typer.echo(f"    unclassified: {path}")
        for item in reconciliation["ambiguous"][:20]:
            typer.echo(
                f"    ambiguous: {item['path']} -> {', '.join(item['output_types'])}"
            )
        for item in reconciliation["identifier_issues"][:20]:
            typer.echo(f"    identifier: {item}")
        if reconciliation["not_observed"]:
            typer.echo(
                "    not observed (allowed): "
                + ", ".join(reconciliation["not_observed"])
            )
        for item in reconciliation["limitations"]:
            typer.echo(f"    limitation: {item}")
    if not observed["examples"]:
        typer.echo(f"  {observed['note']}")
    coverage = document["coverage_assessment"]
    typer.echo("Coverage assessment:")
    typer.echo(f"  {coverage['statement']}")
    for route in coverage["routes"]:
        if route["catalogue"] != "covered" or route["status"] in {
            "unresolved",
            "not_reachable",
        }:
            typer.echo(
                f"  {route['instance']}.{route['emit'] or '-'} "
                f"{route['published_glob'] or '?'}: {route['status']}, "
                f"{route['catalogue'].replace('_', ' ')}"
            )
    typer.echo("Optional checks:")
    for check in document["optional_checks"]:
        typer.echo(f"  {check['name']}: {check['status']} ({check['reason']})")
    if failed:
        raise typer.Exit(code=2)


@preview_app.command("outputs")
def preview_outputs_command(
    repository: RepositoryOption = Path("."),
    output_format: str = typer.Option("json", "--format", help="json or yaml."),
) -> None:
    """Print the derived outputs.schema.json/outputs.yaml (never written)."""
    typer.echo(
        _run(lambda: output_layer.preview_outputs(repository, output_format)), nl=False
    )


# ---------------------------------------------------------------- containers


@containers_app.command("classify")
def containers_classify_command(reference: str) -> None:
    """Classify a container reference without network access."""
    typer.echo(classify_reference(reference).value)


@containers_app.command("cache-name")
def containers_cache_name_command(
    reference: str,
    registry: str | None = typer.Option(None, help="Configured registry."),
) -> None:
    """Print the Nextflow Singularity/Apptainer cache file name."""
    typer.echo(nextflow_cache_filename(reference, registry=registry))


@containers_app.command("verify")
def containers_verify_command(
    container: Annotated[
        str, typer.Argument(help="Container ID from the components draft.")
    ],
    url: Annotated[str, typer.Argument(help="HTTPS URL of the static image.")],
    repository: RepositoryOption = Path("."),
    registry: str | None = typer.Option(None, help="Configured Nextflow registry."),
) -> None:
    """Download and verify an image, then record its distribution (network)."""
    try:
        result = component_layer.verify_distribution(
            repository, container, url, _context(), registry=registry
        )
    except ContainerServiceError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=2) from error
    except _ERRORS as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=2) from error
    typer.echo(result.diff)
    typer.echo("Verified distribution recorded.")


# ---------------------------------------------------------------- analysis output


def _metadata_file(path: Path | None, label: str) -> dict[str, object] | None:
    if path is None:
        return None
    loaded: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise AnalysisOutputError(f"{label} must contain a JSON object")
    return loaded


@analysis_output_app.command("generate")
def generate_analysis_output_command(
    repository: RepositoryOption = Path("."),
    publish_directory: Annotated[
        Path | None,
        _existing_path("Publish directory of the completed job (walked on disk)."),
    ] = None,
    native_output_index: Annotated[
        Path | None,
        _existing_path(
            "Output index written by the pipeline (.json, .yaml, .csv or .tsv), "
            "instead of walking a directory."
        ),
    ] = None,
    output_tree: Annotated[
        Path | None,
        _existing_path(
            "Saved 'ls -R' or 'tree' listing of the publish directory. Supply "
            "exactly one of the three sources."
        ),
    ] = None,
    job_metadata: Annotated[
        Path | None,
        typer.Option(
            exists=True,
            resolve_path=True,
            help=(
                "JSON job identity and job-wide metadata (job_id_short/job_id_long, "
                "config_profile, execution_timestamp, job_metadata.*)."
            ),
        ),
    ] = None,
    sample_metadata: Annotated[
        Path | None,
        typer.Option(
            exists=True,
            resolve_path=True,
            help="CSV of known samples; optional run_id column maps runs to samples.",
        ),
    ] = None,
    output_directory: OutputDirectoryOption = Path("."),
    checksum: str | None = typer.Option(
        None, help="Optional hashlib algorithm for completed published files."
    ),
    allow_unclassified: bool = typer.Option(
        False,
        help="Omit produced paths outside the reviewed contract instead of failing.",
    ),
) -> None:
    """Generate and schema-validate analysis_output.json for one completed job."""
    try:
        result = generate_analysis_output(
            repository,
            publish_directory=publish_directory,
            native_output_index=native_output_index,
            output_tree=output_tree,
            job_metadata=_metadata_file(job_metadata, "job metadata"),
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


@audit_app.command("identity")
def audit_identity_command(
    repository: RepositoryOption = Path("."),
    actor: str | None = typer.Option(None, help="Explicit public actor label."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Show the actor label that would be recorded and the Git suggestion."""
    resolved = resolve_actor(actor)
    suggestion = suggest_git_identity(repository)
    payload = {
        "actor": resolved.model_dump(mode="json"),
        "git_suggestion": None
        if suggestion is None
        else {
            "name": suggestion.name,
            "email_configured": suggestion.email is not None,
        },
        "private_audit_directory": str(audit_directory()),
    }
    if json_output:
        typer.echo(json.dumps(payload, indent=2))
        return
    typer.echo(f"Public actor label: {resolved.label} ({resolved.kind.value})")
    if suggestion is not None and suggestion.name:
        typer.echo(
            f"Git suggests {suggestion.name!r} (unconfirmed); pass --actor or set "
            "NF_SPLICE_ACTOR to use a public label."
        )
    typer.echo(f"Private audit store: {audit_directory()}")


@audit_app.command("show")
def audit_show_command(
    repository: RepositoryOption = Path("."),
    no_redact: bool = typer.Option(
        False, "--no-redact", help="Include private contact details (local only)."
    ),
) -> None:
    """Export this repository's private audit records, redacted by default."""
    records = read_private(repository, redacted=not no_redact)
    typer.echo(json.dumps({"records": records}, indent=2))


def _agent_book(repository: Path) -> Any:
    from nf_splice.agents import ProposalBook
    from nf_splice.agents.orchestration import proposal_book_path
    from nf_splice.interfaces.tui.state import default_session_directory

    return ProposalBook.load(
        proposal_book_path(default_session_directory(), repository)
    )


@agent_app.command("tools")
def agent_tools_command(
    repository: RepositoryOption = Path("."),
    mode: str = typer.Option("suggest", help="ask, suggest, draft or apply."),
) -> None:
    """Print the structured tool schemas available to an agent (offline)."""
    from nf_splice.agents import AgentMode, AgentPolicy, AgentToolbox

    policy = AgentPolicy(repository=repository, mode=AgentMode(mode))
    typer.echo(dumps(AgentToolbox(repository, policy).schemas()))


@agent_app.command("run")
def agent_run_command(
    prompt: Annotated[str, typer.Argument(help="What the assistant should help with.")],
    repository: RepositoryOption = Path("."),
    provider: str = typer.Option(..., help="claude, or scripted (requires --script)."),
    mode: str = typer.Option("suggest", help="ask, suggest or draft."),
    script: Annotated[
        Path | None,
        _existing_path("JSON script of steps for the offline scripted provider."),
    ] = None,
    allow_remote_model: bool = typer.Option(
        False, help="Consent to sending bounded repository context to a remote model."
    ),
    model: str | None = typer.Option(None, help="Explicit provider model name."),
    max_turns: int = typer.Option(12, help="Maximum agent turns."),
    max_budget_usd: float | None = typer.Option(None, help="Spending cap (provider)."),
) -> None:
    """Run an assistant session; it can only propose, never apply."""
    import asyncio

    from nf_splice.agents import AgentMode, SessionLimits, run_agent
    from nf_splice.agents.orchestration import dumps as dump_run

    selected = AgentMode(mode)
    if selected in {AgentMode.OFF, AgentMode.APPLY}:
        raise typer.BadParameter("use ask, suggest or draft; approvals are human-only")
    agent_provider: Any
    if provider == "claude":
        from nf_splice.agents.providers.claude import ClaudeProvider

        agent_provider = ClaudeProvider()
    elif provider == "scripted":
        if script is None:
            raise typer.BadParameter("--provider scripted requires --script")
        from nf_splice.agents.providers.mock import ScriptedProvider

        agent_provider = ScriptedProvider(
            json.loads(script.read_text(encoding="utf-8"))
        )
    else:
        raise typer.BadParameter("provider must be claude or scripted")
    book = _agent_book(repository)
    try:
        result = asyncio.run(
            run_agent(
                repository,
                agent_provider,
                prompt,
                mode=selected,
                book=book,
                allow_remote=allow_remote_model,
                limits=SessionLimits(
                    max_turns=max_turns, max_budget_usd=max_budget_usd, model=model
                ),
            )
        )
    except (PermissionError, RuntimeError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=2) from error
    typer.echo(dump_run(result))


@agent_app.command("proposals")
def agent_proposals_command(repository: RepositoryOption = Path(".")) -> None:
    """List agent proposals and their status."""
    book = _agent_book(repository)
    typer.echo(dumps([item.to_json() for item in book.proposals.values()]))


@agent_app.command("approve")
def agent_approve_command(
    proposal: str,
    repository: RepositoryOption = Path("."),
) -> None:
    """Approve (and apply) one proposal as the human actor (--actor)."""
    from nf_splice.agents import approve

    actor = resolve_actor(_STATE["actor"])
    if actor.kind is not ActorKind.HUMAN:
        typer.echo("approval needs a human actor label (--actor)", err=True)
        raise typer.Exit(code=2)
    book = _agent_book(repository)
    result = _run(lambda: approve(repository, book, proposal, actor))
    typer.echo(dumps(result.to_json()))
    if result.status.value != "applied":
        raise typer.Exit(code=2)


@agent_app.command("reject")
def agent_reject_command(
    proposal: str,
    reason: str = typer.Option(..., help="Why the proposal is rejected."),
    repository: RepositoryOption = Path("."),
) -> None:
    """Reject one proposal."""
    from nf_splice.agents import reject

    book = _agent_book(repository)
    typer.echo(dumps(_run(lambda: reject(book, proposal, reason)).to_json()))


@app.command("tui")
def tui_command(
    repository: RepositoryOption = Path("."),
    no_session: bool = typer.Option(
        False, "--no-session", help="Do not read or write wizard sessions."
    ),
    agent: str | None = typer.Option(
        None, help="Enable the optional assistant: claude."
    ),
    allow_remote_model: bool = typer.Option(
        False, help="Consent to bounded context being sent to the remote model."
    ),
) -> None:
    """Open the guided terminal wizard (works fully without AI)."""
    from nf_splice.interfaces.tui import (
        NfSpliceApp,
        SessionStore,
        default_session_directory,
    )

    sessions = SessionStore(None if no_session else default_session_directory())
    provider = None
    if agent == "claude":
        if not allow_remote_model:
            typer.echo("--agent claude requires --allow-remote-model consent", err=True)
            raise typer.Exit(code=2)
        from nf_splice.agents.providers.claude import ClaudeProvider

        provider = ClaudeProvider()
    elif agent is not None:
        raise typer.BadParameter("agent must be claude")
    NfSpliceApp(
        repository, sessions=sessions, actor=_STATE["actor"], agent_provider=provider
    ).run()


def main() -> None:
    """Run the nf-splice command-line interface."""
    app()
