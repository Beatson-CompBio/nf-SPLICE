"""Command-line entry point for nf-splice (file-first authoring, 0.3.0)."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from functools import partial
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
session_app = typer.Typer(
    help="AI-assisted and autonomous integration sessions (agentic AI).",
    no_args_is_help=True,
)
app.add_typer(session_app, name="session")
skills_app = typer.Typer(
    help="The nf-splice skills that guide AI agents.",
    no_args_is_help=True,
)
app.add_typer(skills_app, name="skills")
workspace_app = typer.Typer(
    help="Check and repair the private .splice-local/ workspace.",
    no_args_is_help=True,
)
app.add_typer(workspace_app, name="workspace")
source_app = typer.Typer(
    help="Isolate the pipeline in its own integration working copy.",
    no_args_is_help=True,
)
app.add_typer(source_app, name="source")
git_app = typer.Typer(
    help="Review and commit the bundle locally; push only when you choose.",
    no_args_is_help=True,
)
app.add_typer(git_app, name="git")
preview_app = typer.Typer(
    help="Show derived, non-authoritative previews of published files.",
    no_args_is_help=True,
)
app.add_typer(preview_app, name="preview")
provider_app = typer.Typer(
    help="Choose, sign in to, diagnose and test AI providers.",
    no_args_is_help=True,
)
app.add_typer(provider_app, name="provider")

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


@app.command("migrate")
def migrate_command(
    repository: RepositoryOption = Path("."),
    check: bool = typer.Option(False, "--check", help="Show what would move."),
    apply: bool = typer.Option(False, "--apply", help="Back up, move and verify."),
    rollback: bool = typer.Option(
        False, "--rollback", help="Restore the most recent migration's originals."
    ),
    json_output: JsonOption = False,
) -> None:
    """Move drafts and sessions of an earlier layout into .splice-local/."""
    from nf_splice.services.migration import (
        MigrationError,
        apply_migration,
        plan_migration,
        rollback_migration,
    )

    if sum([check, apply, rollback]) != 1:
        raise typer.BadParameter("choose exactly one of --check, --apply, --rollback")
    try:
        if check:
            document = plan_migration(repository).to_json()
        elif apply:
            document = apply_migration(repository)
        else:
            document = rollback_migration(repository)
    except (MigrationError, OSError, ValueError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=2) from error
    if json_output:
        typer.echo(dumps(document))
        return
    if check:
        for move in document["moves"]:
            typer.echo(f"move: {move['source']} -> {move['target']}")
        for item in document["conflicts"]:
            typer.echo(f"conflict: {item}", err=True)
        for item in document["skipped"]:
            typer.echo(f"not migrated: {item}")
        typer.echo(
            "Nothing to migrate."
            if not document["needed"]
            else "Run `nf-splice migrate --apply` to migrate (a backup is kept)."
        )
        if document["conflicts"]:
            raise typer.Exit(code=2)
    elif apply:
        typer.echo(
            f"Migrated {len(document['moves'])} file(s); backup and record in "
            f".splice-local/migrations/{document['migration']}/."
            if document.get("migrated")
            else "Nothing to migrate."
        )
    else:
        typer.echo(
            f"Rolled back migration {document['rolled_back']} "
            f"({document['restored']} file(s) restored)."
        )


@workspace_app.command("check")
def workspace_check_command(
    repository: RepositoryOption = Path("."), json_output: JsonOption = False
) -> None:
    """Report problems with the private workspace and published folder (read-only)."""
    from nf_splice import layout

    collisions = layout.case_collisions(repository)
    legacy = layout.legacy_paths(repository)
    tracked = layout.tracked_private_paths(repository)
    ignore = repository / ".gitignore"
    ignored = (
        ignore.is_file()
        and layout.IGNORE_RULE in ignore.read_text(encoding="utf-8").splitlines()
    )
    document: dict[str, Any] = {
        "case_collisions": collisions,
        "legacy_layout": legacy,
        "tracked_private_files": tracked,
        "ignore_rule_present": ignored,
        "git_work_tree": layout.is_git_work_tree(repository),
    }
    problems = bool(collisions or legacy or tracked)
    if json_output:
        typer.echo(dumps(document | {"ok": not problems}))
    else:
        for name in collisions:
            typer.echo(
                f"problem: {name} collides with splice/ or .splice-local/ on "
                "case-insensitive filesystems; rename it"
            )
        for name in legacy:
            typer.echo(
                f"problem: {name} is an earlier layout; run nf-splice migrate --check"
            )
        if tracked:
            typer.echo(
                f"problem: Git tracks {len(tracked)} file(s) "
                "under .splice-local/; run `nf-splice workspace untrack --yes`"
            )
        typer.echo(
            "Ignore rule /.splice-local/ is present."
            if ignored
            else "Ignore rule /.splice-local/ is added when nf-splice first writes."
        )
        typer.echo("Workspace OK." if not problems else "Workspace needs attention.")
    if problems:
        raise typer.Exit(code=2)


@workspace_app.command("untrack")
def workspace_untrack_command(
    repository: RepositoryOption = Path("."),
    yes: bool = typer.Option(
        False, "--yes", help="Confirm: stop tracking .splice-local/."
    ),
) -> None:
    """Stop Git tracking .splice-local/ (files kept; history not rewritten)."""
    from nf_splice import layout

    if not yes:
        typer.echo(
            "This removes .splice-local/ from Git's index (the files stay on disk and "
            "earlier commits are unchanged). Repeat with --yes to confirm.",
            err=True,
        )
        raise typer.Exit(code=2)
    removed = _run(lambda: layout.untrack_private_workspace(repository))
    typer.echo(
        f"Stopped tracking {len(removed)} file(s); commit the change to record it."
        if removed
        else "Nothing under .splice-local/ is tracked."
    )


@source_app.command("prepare")
def source_prepare_command(
    source: Annotated[
        str, typer.Argument(help="Pipeline folder, local Git repository or Git URL.")
    ],
    destination: Annotated[
        Path | None,
        typer.Option(
            "--into",
            help="New directory for the integration copy "
            "(default: <name>-splice-integration next to the source).",
        ),
    ] = None,
    ref: str | None = typer.Option(None, help="Branch, tag or commit to start from."),
    branch: str | None = typer.Option(
        None, help="Local branch for the work (default nf-splice/integration-<name>)."
    ),
    include_uncommitted: bool = typer.Option(
        False, help="Also copy the source repository's uncommitted changes."
    ),
    git_name: str | None = typer.Option(None, help="Git author name for this copy."),
    git_email: str | None = typer.Option(None, help="Git author e-mail for this copy."),
    no_git: bool = typer.Option(
        False, "--no-git", help="Plain folder copy without a local Git repository."
    ),
    in_place: bool = typer.Option(
        False, "--in-place", help="Work on the original instead of a copy (risky)."
    ),
    yes: bool = typer.Option(False, "--yes", help="Confirm working in place."),
    json_output: JsonOption = False,
) -> None:
    """Create the isolated working copy that nf-splice will change."""
    from nf_splice.services.source import SourceError, prepare_integration_copy

    if in_place and not yes:
        typer.echo(
            "Working in place lets nf-splice change your original pipeline folder "
            "(it adds splice/, .splice-local/ and a .gitignore rule). Repeat with "
            "--yes to accept, or omit --in-place to work on a safe copy.",
            err=True,
        )
        raise typer.Exit(code=2)
    try:
        copy = prepare_integration_copy(
            source,
            destination,
            ref=ref,
            branch=branch,
            include_uncommitted=include_uncommitted,
            git_name=git_name,
            git_email=git_email,
            in_place=in_place,
            use_git=not no_git,
        )
    except (SourceError, OSError, ValueError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=2) from error
    if json_output:
        typer.echo(dumps(copy.to_json()))
        return
    typer.echo(f"Integration copy: {copy.path}")
    if copy.branch:
        typer.echo(f"Branch: {copy.branch}")
    if copy.uncommitted_in_source and not copy.imported_uncommitted:
        typer.echo(
            f"note: {len(copy.uncommitted_in_source)} uncommitted change(s) in the "
            "source were not copied (use --include-uncommitted to copy them)"
        )
    for item in copy.skipped[:20]:
        typer.echo(f"not copied: {item}")
    typer.echo(
        "The original pipeline is unchanged. Continue in the copy, for example: "
        f"nf-splice init --repository {copy.path}"
    )


@source_app.command("info")
def source_info_command(
    repository: RepositoryOption = Path("."), json_output: JsonOption = False
) -> None:
    """Show where this integration copy came from (read-only)."""
    from nf_splice.services.source import read_record

    record = read_record(repository)
    if record is None:
        typer.echo("No integration record: this folder was not prepared by nf-splice.")
        raise typer.Exit(code=2)
    if json_output:
        typer.echo(dumps(record))
        return
    for key in ("source_kind", "source", "source_revision", "branch", "created_at"):
        typer.echo(f"{key}: {record.get(key)}")


@git_app.command("status")
def git_status_command(
    repository: RepositoryOption = Path("."), json_output: JsonOption = False
) -> None:
    """Changes to the bundle and other files (read-only)."""
    from nf_splice.services import gitops

    current = gitops.status(repository)
    if json_output:
        typer.echo(dumps(current.to_json()))
        return
    if not current.repository:
        typer.echo(
            "Not a Git repository; create a copy with `nf-splice source prepare`."
        )
        return
    typer.echo(f"Branch: {current.branch or '(detached)'}")
    for path in current.owned:
        typer.echo(f"bundle change: {path}")
    for path in current.other:
        typer.echo(f"other change: {path}")
    if current.private_tracked:
        typer.echo(
            "problem: .splice-local/ is tracked; run nf-splice workspace untrack --yes"
        )
    if not current.owned and not current.other:
        typer.echo("No changes.")


@git_app.command("diff")
def git_diff_command(repository: RepositoryOption = Path(".")) -> None:
    """Diff of splice/ and .gitignore against the last commit (read-only)."""
    from nf_splice.services import gitops

    typer.echo(_git_run(lambda: gitops.diff(repository)) or "No changes.", nl=False)


def _git_run(action: Callable[[], T]) -> T:
    from nf_splice.services.gitops import GitOperationError

    try:
        return action()
    except (GitOperationError, OSError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=2) from error


@git_app.command("commit")
def git_commit_command(
    repository: RepositoryOption = Path("."),
    message: str = typer.Option(
        "Publish the SPLICE workflow bundle", "--message", "-m", help="Commit message."
    ),
    include: Annotated[
        list[str] | None,
        typer.Option("--include", help="Also commit this pipeline path (repeatable)."),
    ] = None,
) -> None:
    """Commit the validated splice/ and .gitignore with your Git identity."""
    from nf_splice.services import gitops

    result = _git_run(
        lambda: gitops.commit(repository, message, extra_paths=list(include or []))
    )
    if result["committed"]:
        typer.echo(
            f"Committed {len(result['paths'])} file(s) as {result['commit'][:12]}."
        )
    else:
        typer.echo("Nothing to commit.")


@git_app.command("push")
def git_push_command(
    repository: RepositoryOption = Path("."),
    remote: str = typer.Option(..., help="Remote to push to, for example origin."),
    branch: str | None = typer.Option(None, help="Remote branch (default: current)."),
    yes: bool = typer.Option(False, "--yes", help="Confirm pushing to the remote."),
) -> None:
    """Push the integration branch to a remote you choose (never automatic)."""
    from nf_splice.services import gitops

    if not yes:
        typer.echo(
            "Pushing publishes the branch on the remote. Repeat with --yes to "
            "confirm. nf-splice never opens pull requests; use your Git host for that.",
            err=True,
        )
        raise typer.Exit(code=2)
    result = _git_run(lambda: gitops.push(repository, remote, branch))
    typer.echo(f"Pushed to {result['remote']} {result['branch']}.")


@app.command("export")
def export_command(
    repository: RepositoryOption = Path("."),
    archive_scope: str = typer.Option(
        "bundle", "--archive-scope", help="bundle (splice/ only) or pipeline."
    ),
    archive_output: Annotated[
        Path | None,
        typer.Option(
            "--archive-output",
            help="ZIP file to write (default .splice-local/exports/<name>-<version>-"
            "splice-<scope>.zip).",
        ),
    ] = None,
    overwrite: bool = typer.Option(False, help="Replace an existing archive."),
    json_output: JsonOption = False,
) -> None:
    """Create and verify a ZIP of the validated bundle or pipeline copy."""
    from nf_splice.services.export import ExportError, ExportScope, export_archive

    try:
        scope = ExportScope(archive_scope)
    except ValueError as error:
        raise typer.BadParameter(
            "--archive-scope must be bundle or pipeline"
        ) from error
    try:
        result = export_archive(repository, scope, archive_output, overwrite=overwrite)
    except (ExportError, OSError, ValueError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=2) from error
    if json_output:
        typer.echo(dumps(result.to_json()))
        return
    typer.echo(f"Wrote {result.path} ({result.size} bytes)")
    typer.echo(f"SHA-256: {result.sha256}")
    for check in result.checks:
        typer.echo(f"verified: {check}")
    for item in result.excluded[:20]:
        typer.echo(f"not included: {item}")


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


# ---------------------------------------------------------------- agentic AI

ProviderOption = Annotated[
    str | None,
    typer.Option(
        "--provider",
        help="AI provider: claude, openai, codex, opencode, or scripted (offline, "
        "needs --script). Defaults to the one saved with "
        "`nf-splice provider select`.",
    ),
]
ScriptOption = Annotated[
    Path | None,
    _existing_path("JSON turn script for the offline scripted provider."),
]
AllowRemoteOption = Annotated[
    bool,
    typer.Option(
        "--allow-remote-model",
        help="Consent to sending repository context to a remote model.",
    ),
]
SessionOption = Annotated[
    str | None,
    typer.Option("--session", help="Session ID; the most recent when omitted."),
]
ExampleOutputOption = Annotated[
    list[Path] | None,
    typer.Option(
        "--example-output",
        exists=True,
        resolve_path=True,
        help="Results of one completed run (directory, saved listing or output "
        "index) the agent may read as evidence. Repeatable.",
    ),
]
AllowOption = Annotated[
    list[str] | None,
    typer.Option(
        "--allow",
        help="Grant an extra permission: overwrite, external_tools, run_nextflow "
        "or network. Repeatable.",
    ),
]


def _agent_errors() -> tuple[type[BaseException], ...]:
    from nf_splice.agents import (
        CapabilityError,
        PolicyViolation,
        ProviderUnavailable,
        SessionError,
    )
    from nf_splice.agents.providers.base import ProviderError

    return (
        SessionError,
        PolicyViolation,
        PermissionError,
        CapabilityError,
        ProviderUnavailable,
        ProviderError,
        *_ERRORS,
    )


def _agent_run(action: Callable[[], T]) -> T:
    try:
        return action()
    except _agent_errors() as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=2) from error


def _human() -> Any:
    actor = resolve_actor(_STATE["actor"])
    if actor.kind is not ActorKind.HUMAN:
        typer.echo(
            "this needs a person's actor label: pass --actor NAME or set "
            "NF_SPLICE_ACTOR",
            err=True,
        )
        raise typer.Exit(code=2)
    return actor


def _make_provider(
    name: str | None,
    script: Path | None,
    progress: Path | None = None,
    model: str | None = None,
) -> Any:
    from nf_splice.agents.providers import provider_for, selected

    if name is None:
        name = "scripted" if script is not None else selected()[0]
    if name is None:
        typer.echo(
            "choose a provider with --provider, or save one with "
            "`nf-splice provider select` (see `nf-splice provider list`)",
            err=True,
        )
        raise typer.Exit(code=2)
    try:
        return provider_for(name, script=script, progress=progress, model=model)
    except (ValueError, OSError) as error:
        raise typer.BadParameter(str(error)) from error


def _open_engine(repository: Path, session: str | None) -> Any:
    from nf_splice.agents import SessionEngine

    engine = _agent_run(lambda: SessionEngine.open(repository, session))
    record = engine.state.provider
    progress = engine.session_directory / "scripted-progress.json"
    engine.provider = _make_provider(
        record.name,
        Path(record.script) if record.script else None,
        progress,
        record.model,
    )
    return engine


def _policy(
    examples: list[Path] | None,
    allow: list[str] | None,
    allow_remote_model: bool,
    *,
    max_tool_calls: int,
    max_stage_attempts: int,
    max_budget_usd: float | None,
    model: str | None,
    turn_timeout: float,
) -> Any:
    from nf_splice.agents import Budgets, ExecutionPolicy, validate_grants

    return ExecutionPolicy(
        grants=_agent_run(lambda: validate_grants(list(allow or []))),
        budgets=Budgets(
            max_tool_calls=max_tool_calls,
            max_stage_attempts=max_stage_attempts,
            max_budget_usd=max_budget_usd,
            model=model,
            turn_timeout_seconds=turn_timeout,
        ),
        examples=[str(item) for item in examples or []],
        allow_remote_model=allow_remote_model,
    )


def _show_session(engine: Any, json_output: bool, *, diff: bool = True) -> None:
    from nf_splice.agents.prompts import proposal_text
    from nf_splice.agents.stages import ORDER, spec

    state = engine.state
    if json_output:
        typer.echo(
            dumps(
                {
                    "session": state.id,
                    "mode": state.mode.value,
                    "status": state.status.value,
                    "current_stage": state.current_stage.value
                    if state.current_stage
                    else None,
                    "stages": {
                        stage.value: state.stages[stage].status.value for stage in ORDER
                    },
                    "pending": state.pending.model_dump(mode="json")
                    if state.pending
                    else None,
                    "blockers": [
                        item.model_dump(mode="json")
                        for item in state.blockers
                        if not item.resolved
                    ],
                    "conversation": [
                        item.model_dump(mode="json")
                        for item in state.conversation[-20:]
                    ],
                    "usage": state.usage.model_dump(mode="json"),
                }
            )
        )
        return
    status = state.status.value.replace("_", " ")
    typer.echo(f"Session {state.id}: {state.mode.value}, {status}")
    typer.echo(
        "Stages: "
        + ", ".join(
            f"{spec(stage).title}={state.stages[stage].status.value}" for stage in ORDER
        )
    )
    for entry in state.conversation[-6:]:
        if entry.role in {"agent", "system"} and entry.kind not in {"proposal"}:
            typer.echo(f"[{entry.role}] {entry.text}")
    if state.pending is not None:
        typer.echo("")
        typer.echo(proposal_text(state.pending))
        if diff and state.pending.diff:
            typer.echo("Diff:")
            typer.echo(state.pending.diff[:20000], nl=False)
    hints = {
        "awaiting_approval": "Next: `nf-splice session approve`, "
        "`nf-splice session object TEXT` or `nf-splice session ask TEXT`.",
        "awaiting_input": "Next: `nf-splice session reply TEXT`, or edit the drafts "
        "and run `nf-splice session continue`.",
        "paused": "Next: `nf-splice session resume`.",
        "blocked": "Next: `nf-splice session report`, then "
        "`nf-splice session resume --mode assisted` to resolve blockers.",
        "completed": "Next: `nf-splice session report`.",
    }
    hint = hints.get(state.status.value)
    if hint:
        typer.echo(hint)


def _interactive_step(engine: Any, choice: str) -> bool:
    """Carry out one terminal choice; False ends the conversation."""
    import asyncio

    actor = _human()
    if choice.startswith("a") and engine.state.pending is not None:
        _agent_run(lambda: asyncio.run(engine.approve(actor)))
    elif choice.startswith("o"):
        objection = typer.prompt("What is wrong with the proposal?")
        _agent_run(lambda: asyncio.run(engine.object(objection, actor)))
    elif choice.startswith("r"):
        answer = typer.prompt("Your answer")
        _agent_run(lambda: asyncio.run(engine.reply(answer, actor)))
    elif choice.startswith("q"):
        question = typer.prompt("Your question")
        typer.echo(_agent_run(lambda: asyncio.run(engine.ask(question, actor))))
    elif choice.startswith("n"):
        _agent_run(lambda: asyncio.run(engine.advance()))
    elif choice.startswith("p"):
        _agent_run(lambda: engine.pause(actor))
        return False
    elif choice.startswith("c"):
        _agent_run(lambda: engine.cancel(actor))
        return False
    return True


def _interactive(engine: Any) -> None:
    """A conversational loop for an assisted session in a terminal."""
    from nf_splice.agents import SessionStatus

    while True:
        _show_session(engine, False)
        status = engine.state.status
        if status is SessionStatus.AWAITING_APPROVAL:
            prompt = "[a]pprove, [o]bject, ask a [q]uestion, [p]ause or [c]ancel"
            default = "q"
        elif status is SessionStatus.AWAITING_INPUT:
            prompt = (
                "[r]eply, ask a [q]uestion, [n] continue after editing, [p]ause or "
                "[c]ancel"
            )
            default = "r"
        else:
            return
        choice = typer.prompt(prompt, default=default).strip().lower()
        if not _interactive_step(engine, choice):
            return


@app.command("ask")
def ask_command(
    question: Annotated[str, typer.Argument(help="What you want to know.")],
    repository: RepositoryOption = Path("."),
    provider: ProviderOption = None,
    script: ScriptOption = None,
    allow_remote_model: AllowRemoteOption = False,
    layer: str | None = typer.Option(None, help="The layer you are looking at."),
    pointer: str | None = typer.Option(None, help="JSON pointer of the field."),
    error: str | None = typer.Option(None, help="An error message to explain."),
    candidate: str | None = typer.Option(None, help="A candidate ID to explain."),
    example_output: ExampleOutputOption = None,
    model: str | None = typer.Option(None, help="Explicit provider model."),
    json_output: JsonOption = False,
) -> None:
    """Ask AI about your pipeline or drafts; read-only, it never changes anything."""
    import asyncio

    from nf_splice.agents import ask_for_help

    context = {
        key: value
        for key, value in {
            "layer": layer,
            "pointer": pointer,
            "error": error,
            "candidate": candidate,
        }.items()
        if value
    }
    agent = _make_provider(provider, script, model=model)
    answer = _agent_run(
        lambda: asyncio.run(
            ask_for_help(
                repository,
                agent,
                question,
                context=context,
                allow_remote_model=allow_remote_model,
                examples=list(example_output or []),
                model=model,
            )
        )
    )
    if json_output:
        typer.echo(
            dumps(
                {
                    "answer": answer.text,
                    "tool_calls": answer.tool_calls,
                    "denied": answer.denied,
                }
            )
        )
        return
    typer.echo(answer.text)


@session_app.command("start")
def session_start_command(
    repository: RepositoryOption = Path("."),
    mode: str = typer.Option(
        "assisted", help="assisted (you approve each stage) or autonomous."
    ),
    provider: ProviderOption = None,
    script: ScriptOption = None,
    allow_remote_model: AllowRemoteOption = False,
    objective: str = typer.Option(
        "Integrate this Nextflow pipeline with SPLICE.", help="What to achieve."
    ),
    example_output: ExampleOutputOption = None,
    allow: AllowOption = None,
    max_tool_calls: int = typer.Option(300, help="Tool calls for the whole session."),
    max_stage_attempts: int = typer.Option(3, help="Attempts per stage."),
    max_budget_usd: float | None = typer.Option(None, help="Provider spending cap."),
    turn_timeout: float = typer.Option(600.0, help="Seconds per provider turn."),
    model: str | None = typer.Option(None, help="Explicit provider model."),
    interactive: bool | None = typer.Option(
        None,
        "--interactive/--no-interactive",
        help="Converse in this terminal (default when it is a terminal).",
    ),
    json_output: JsonOption = False,
) -> None:
    """Start an AI-assisted or autonomous integration session."""
    import asyncio
    import sys

    from nf_splice.agents import InteractionMode, SessionEngine

    if mode not in {"assisted", "autonomous"}:
        raise typer.BadParameter("mode must be assisted or autonomous")
    actor = _human()
    policy = _policy(
        example_output,
        allow,
        allow_remote_model,
        max_tool_calls=max_tool_calls,
        max_stage_attempts=max_stage_attempts,
        max_budget_usd=max_budget_usd,
        model=model,
        turn_timeout=turn_timeout,
    )
    agent = _make_provider(provider, script, model=model)
    engine = _agent_run(
        lambda: SessionEngine.create(
            repository,
            mode=InteractionMode(mode),
            provider=agent,
            objective=objective,
            policy=policy,
            actor=actor,
            script=str(script) if script else None,
        )
    )
    if hasattr(agent, "progress"):
        agent.progress = engine.session_directory / "scripted-progress.json"
    _agent_run(lambda: asyncio.run(engine.advance()))
    use_terminal = sys.stdin.isatty() if interactive is None else interactive
    if mode == "assisted" and use_terminal and not json_output:
        _interactive(engine)
        return
    if mode == "autonomous" and not json_output:
        from nf_splice.agents.report import report_text

        typer.echo(report_text(engine.report()))
        return
    _show_session(engine, json_output)


@session_app.command("status")
def session_status_command(
    repository: RepositoryOption = Path("."),
    session: SessionOption = None,
    diff: bool = typer.Option(True, "--diff/--no-diff", help="Show the proposal diff."),
    json_output: JsonOption = False,
) -> None:
    """Show a session's stages, conversation and pending proposal (read-only)."""
    from nf_splice.agents import SessionEngine

    engine = _agent_run(lambda: SessionEngine.open(repository, session))
    _show_session(engine, json_output, diff=diff)


@session_app.command("list")
def session_list_command(
    repository: RepositoryOption = Path("."), json_output: JsonOption = False
) -> None:
    """List this repository's sessions, most recent first."""
    from nf_splice.agents import SessionStore

    sessions = _agent_run(lambda: SessionStore(repository).sessions())
    if json_output:
        typer.echo(
            dumps(
                [
                    {
                        "id": item.id,
                        "mode": item.mode.value,
                        "status": item.status.value,
                        "updated_at": item.updated_at,
                    }
                    for item in sessions
                ]
            )
        )
        return
    for item in sessions:
        typer.echo(
            f"{item.id}  {item.mode.value:<10} {item.status.value:<18} "
            f"{item.updated_at}"
        )
    if not sessions:
        typer.echo("No sessions.")


@session_app.command("approve")
def session_approve_command(
    repository: RepositoryOption = Path("."),
    session: SessionOption = None,
    json_output: JsonOption = False,
) -> None:
    """Approve the pending proposal; it is applied and validated."""
    import asyncio

    actor = _human()
    engine = _open_engine(repository, session)
    _agent_run(lambda: asyncio.run(engine.approve(actor)))
    _show_session(engine, json_output)


@session_app.command("object")
def session_object_command(
    message: Annotated[str, typer.Argument(help="What is wrong with the proposal.")],
    repository: RepositoryOption = Path("."),
    session: SessionOption = None,
    json_output: JsonOption = False,
) -> None:
    """Object to the pending proposal; the agent investigates and responds."""
    import asyncio

    actor = _human()
    engine = _open_engine(repository, session)
    _agent_run(lambda: asyncio.run(engine.object(message, actor)))
    _show_session(engine, json_output)


@session_app.command("reply")
def session_reply_command(
    message: Annotated[str, typer.Argument(help="Your answer to the agent.")],
    repository: RepositoryOption = Path("."),
    session: SessionOption = None,
    json_output: JsonOption = False,
) -> None:
    """Answer the agent when it asks how to proceed."""
    import asyncio

    actor = _human()
    engine = _open_engine(repository, session)
    _agent_run(lambda: asyncio.run(engine.reply(message, actor)))
    _show_session(engine, json_output)


@session_app.command("ask")
def session_ask_command(
    question: Annotated[str, typer.Argument(help="Your question.")],
    repository: RepositoryOption = Path("."),
    session: SessionOption = None,
) -> None:
    """Ask the session's agent a question; nothing changes."""
    import asyncio

    actor = resolve_actor(_STATE["actor"])
    engine = _open_engine(repository, session)
    typer.echo(_agent_run(lambda: asyncio.run(engine.ask(question, actor))))


@session_app.command("continue")
def session_continue_command(
    repository: RepositoryOption = Path("."),
    session: SessionOption = None,
    json_output: JsonOption = False,
) -> None:
    """Continue after editing drafts yourself; files are checked again first."""
    import asyncio

    engine = _open_engine(repository, session)
    _agent_run(lambda: asyncio.run(engine.advance()))
    _show_session(engine, json_output)


@session_app.command("pause")
def session_pause_command(
    repository: RepositoryOption = Path("."), session: SessionOption = None
) -> None:
    """Pause a session; resume it later in any mode."""
    from nf_splice.agents import SessionEngine

    actor = resolve_actor(_STATE["actor"])
    engine = _agent_run(lambda: SessionEngine.open(repository, session))
    _agent_run(lambda: engine.pause(actor))
    typer.echo(f"Paused {engine.state.id}.")


@session_app.command("cancel")
def session_cancel_command(
    repository: RepositoryOption = Path("."), session: SessionOption = None
) -> None:
    """Cancel a session; drafts and published files are kept as they are."""
    from nf_splice.agents import SessionEngine

    actor = resolve_actor(_STATE["actor"])
    engine = _agent_run(lambda: SessionEngine.open(repository, session))
    _agent_run(lambda: engine.cancel(actor))
    typer.echo(f"Cancelled {engine.state.id}; your drafts are unchanged.")


@session_app.command("resume")
def session_resume_command(
    repository: RepositoryOption = Path("."),
    session: SessionOption = None,
    mode: str | None = typer.Option(
        None, help="Switch to assisted, autonomous or manual before continuing."
    ),
    allow: AllowOption = None,
    provider: str | None = typer.Option(
        None,
        "--provider",
        help="Continue with another provider (the session's record carries the "
        "context; nothing is switched automatically).",
    ),
    model: str | None = typer.Option(None, help="Continue with another model."),
    allow_remote_model: AllowRemoteOption = False,
    interactive: bool | None = typer.Option(
        None,
        "--interactive/--no-interactive",
        help="Converse in this terminal (default when it is a terminal).",
    ),
    json_output: JsonOption = False,
) -> None:
    """Resume a session, optionally in another mode; work so far is kept."""
    import asyncio
    import sys

    from nf_splice.agents import InteractionMode, SessionStatus

    actor = resolve_actor(_STATE["actor"])
    engine = _open_engine(repository, session)
    target = InteractionMode(mode) if mode else engine.state.mode
    if target is not InteractionMode.MANUAL:
        actor = _human()
    policy = None
    if allow:
        from nf_splice.agents import validate_grants

        policy = engine.state.policy.model_copy(deep=True)
        policy.grants = _agent_run(lambda: validate_grants(list(allow)))
    if provider is not None or model is not None:
        from nf_splice.agents.providers import canonical

        name = canonical(provider or engine.state.provider.name)
        replacement = _make_provider(name, None, model=model)
        if allow_remote_model and not engine.state.policy.allow_remote_model:
            engine.state.policy.allow_remote_model = True
        human = _human()
        _agent_run(lambda: engine.switch_provider(replacement, human, model=model))
    if target is not engine.state.mode or policy is not None:
        _agent_run(lambda: engine.switch_mode(target, actor, policy=policy))
    elif engine.state.status is SessionStatus.PAUSED:
        engine.state.status = SessionStatus.ACTIVE
        engine.state.interruption = None
    if target is InteractionMode.MANUAL:
        typer.echo(
            f"{engine.state.id} is paused for manual work. Edit with nf-splice "
            "commands or the wizard, then run "
            "`nf-splice session resume --mode assisted`."
        )
        return
    _agent_run(lambda: asyncio.run(engine.advance()))
    use_terminal = sys.stdin.isatty() if interactive is None else interactive
    if target is InteractionMode.ASSISTED and use_terminal and not json_output:
        _interactive(engine)
        return
    _show_session(engine, json_output)


@session_app.command("report")
def session_report_command(
    repository: RepositoryOption = Path("."),
    session: SessionOption = None,
    json_output: JsonOption = False,
) -> None:
    """Show the session's report: artefacts, results, blockers and audit."""
    from nf_splice.agents import SessionEngine
    from nf_splice.agents.report import report_text

    engine = _agent_run(lambda: SessionEngine.open(repository, session))
    report = engine.report()
    typer.echo(dumps(report) if json_output else report_text(report))


@session_app.command("rollback")
def session_rollback_command(
    checkpoint: Annotated[
        str, typer.Argument(help="Checkpoint ID, e.g. checkpoint-2.")
    ],
    repository: RepositoryOption = Path("."),
    session: SessionOption = None,
) -> None:
    """Restore splice/ to a session checkpoint."""
    from nf_splice.agents import SessionEngine

    actor = _human()
    engine = _agent_run(lambda: SessionEngine.open(repository, session))
    _agent_run(lambda: engine.rollback(checkpoint, actor))
    typer.echo(f"Restored {checkpoint}.")


@session_app.command("tools")
def session_tools_command(
    stage: str | None = typer.Option(None, help="Only the tools of one stage."),
) -> None:
    """Print the structured tool schemas agents can use (offline)."""
    from nf_splice.agents.operations import CONTROL_SCHEMAS, OPERATIONS, READ_OPERATIONS
    from nf_splice.agents.stages import spec

    names = sorted(OPERATIONS)
    if stage is not None:
        try:
            names = sorted(set(READ_OPERATIONS) | set(spec(stage).operations))
        except ValueError as error:
            raise typer.BadParameter(f"unknown stage {stage!r}") from error
    typer.echo(
        dumps(
            [
                OPERATIONS[name].schema()
                | {"permission": OPERATIONS[name].permission.value}
                for name in names
            ]
            + list(CONTROL_SCHEMAS.values())
        )
    )


@skills_app.command("list")
def skills_list_command() -> None:
    """List the packaged skills."""
    from nf_splice.agents import skills

    for name in skills.NAMES:
        typer.echo(f"{name}: {skills.load(name).description}")


@skills_app.command("show")
def skills_show_command(
    name: Annotated[str, typer.Argument(help="Skill name.")],
) -> None:
    """Print one skill's SKILL.md."""
    from nf_splice.agents import skills

    typer.echo(_run(lambda: skills.skill_text(name)), nl=False)


@skills_app.command("export")
def skills_export_command(
    destination: Annotated[
        Path,
        typer.Option(
            "--dest",
            file_okay=False,
            resolve_path=True,
            help="Directory to write <skill>/SKILL.md into, for example "
            ".claude/skills for Claude Code.",
        ),
    ],
) -> None:
    """Copy the skills where an external coding agent discovers them."""
    from nf_splice.agents import skills

    for path in skills.export(destination):
        typer.echo(f"wrote: {path}")


# ---------------------------------------------------------------- providers


def _diagnosis_text(diagnosis: Any) -> str:
    state = "ready" if diagnosis.ready else "not ready"
    lines = [
        f"{diagnosis.provider}: {state}",
        f"  auth:      {diagnosis.auth_method}"
        + (f" ({diagnosis.account})" if diagnosis.account else ""),
        f"  inference: {diagnosis.inference}",
        f"  billing:   {diagnosis.billing}",
    ]
    for check in diagnosis.checks:
        mark = "ok " if check.ok else "-- "
        lines.append(f"  {mark}{check.name}: {check.detail}")
    for item in diagnosis.models[:20]:
        lines.append(f"  model: {item.id}")
    for line in diagnosis.guidance:
        lines.append(f"  next: {line}")
    return "\n".join(lines)


def _provider_name(name: str) -> str:
    from nf_splice.agents.providers import NAMES, canonical

    name = canonical(name)
    if name not in NAMES:
        raise typer.BadParameter(f"choose one of: {', '.join(NAMES)}")
    return name


@provider_app.command("list")
def provider_list_command(json_output: JsonOption = False) -> None:
    """List the providers, how each signs in, where it runs and who pays."""
    from nf_splice.agents.providers import PROVIDERS, selected

    chosen, model = selected()
    rows = [
        {
            "name": info.name,
            "selected": info.name == chosen,
            "model": model if info.name == chosen else None,
            "summary": info.summary,
            "auth": info.auth,
            "inference": info.inference,
            "billing": info.billing,
        }
        for info in PROVIDERS.values()
    ]
    if json_output:
        typer.echo(dumps({"providers": rows}))
        return
    for row in rows:
        marker = "*" if row["selected"] else " "
        typer.echo(f"{marker} {row['name']:<9} {row['summary']}")
        typer.echo(f"    sign-in: {row['auth']}")
        typer.echo(f"    runs:    {row['inference']}; billing: {row['billing']}")
    if chosen is None:
        typer.echo("No provider selected; run `nf-splice provider select`.")


@provider_app.command("doctor")
def provider_doctor_command(
    name: Annotated[
        str | None, typer.Argument(help="One provider; all when omitted.")
    ] = None,
    online: bool = typer.Option(
        False, "--online", help="Contact the provider to verify the credential."
    ),
    json_output: JsonOption = False,
) -> None:
    """Diagnose providers: installed parts, sign-in, routing and billing."""
    from nf_splice.agents.providers import NAMES, diagnose

    names = [_provider_name(name)] if name else list(NAMES)
    found = []
    for item in names:
        found.append(_agent_run(partial(diagnose, item, online=online)))
    if json_output:
        typer.echo(dumps({"providers": [item.to_json() for item in found]}))
        return
    typer.echo("\n\n".join(_diagnosis_text(item) for item in found))


@provider_app.command("models")
def provider_models_command(
    name: Annotated[str, typer.Argument(help="Provider name.")],
    json_output: JsonOption = False,
) -> None:
    """List the models the signed-in account or configuration offers."""
    from nf_splice.agents.providers import models

    found = _agent_run(lambda: models(_provider_name(name)))
    if json_output:
        typer.echo(dumps({"models": [item.to_json() for item in found]}))
        return
    if not found:
        typer.echo(f"{name} reports no models.")
    for item in found:
        tools = {True: "tools", False: "no tools", None: "tools unknown"}
        typer.echo(f"{item.id}  ({item.location}; {tools[item.tool_calling]})")


@provider_app.command("select")
def provider_select_command(
    name: Annotated[str, typer.Argument(help="Provider name.")],
    model: str | None = typer.Option(None, help="The model to use with it."),
) -> None:
    """Save the provider (and model) used when --provider is not given."""
    from nf_splice.agents.providers import select

    try:
        select(_provider_name(name), model)
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(f"selected: {name}" + (f" with model {model}" if model else ""))


@provider_app.command("auth")
def provider_auth_command(
    name: Annotated[str, typer.Argument(help="claude, openai, codex or opencode.")],
    sign_in: bool = typer.Option(
        False, "--sign-in", help="OpenAI: sign in with ChatGPT in your browser."
    ),
    sign_out: bool = typer.Option(
        False, "--sign-out", help="OpenAI: revoke and forget the active sign-in."
    ),
    account: str | None = typer.Option(
        None, "--account", help="OpenAI: the saved account (client ID) to use."
    ),
    api_key: bool = typer.Option(
        False, "--api-key", help="Save an API key, typed at a hidden prompt."
    ),
    forget_key: bool = typer.Option(False, "--forget-key", help="Remove a saved key."),
    use: str | None = typer.Option(
        None,
        "--use",
        help="OpenAI: chatgpt (plan usage) or api-key (metered API billing).",
    ),
    yes: bool = typer.Option(
        False, "--yes", help="Confirm switching to metered API billing."
    ),
) -> None:
    """Sign in, save a key or choose how a provider authenticates."""
    from nf_splice import credentials

    provider = _provider_name(name)
    if forget_key:
        removed = credentials.delete_secret(f"keys/{provider}.json")
        typer.echo("removed the saved key" if removed else "no saved key")
        return
    if api_key:
        if provider not in {"claude", "openai"}:
            raise typer.BadParameter(f"{provider} does not use an nf-splice API key")
        value = typer.prompt("API key", hide_input=True).strip()
        if not value:
            raise typer.BadParameter("no key entered")
        path = credentials.store_api_key(provider, value)
        typer.echo(f"saved the key owner-only in {path.parent}")
        if provider == "openai":
            typer.echo(
                "It is used only after "
                "`nf-splice provider auth openai --use api-key --yes`."
            )
        return
    if provider == "openai":
        _openai_auth(sign_in, sign_out, account, use, yes)
        return
    if provider == "claude":
        from nf_splice.agents.providers.claude import CREDITS_GUIDANCE

        typer.echo(
            "Claude uses a Claude Platform API key, from ANTHROPIC_API_KEY or "
            "`nf-splice provider auth claude --api-key`. " + CREDITS_GUIDANCE
        )
        return
    typer.echo(f"See `nf-splice provider doctor {provider}` for how to set it up.")


def _openai_auth(
    sign_in: bool, sign_out: bool, account: str | None, use: str | None, yes: bool
) -> None:
    from nf_splice import credentials
    from nf_splice.agents.providers import openai_auth

    if use is not None:
        if use not in {"chatgpt", "api-key"}:
            raise typer.BadParameter("--use must be chatgpt or api-key")
        if use == "api-key" and not yes:
            typer.echo(
                "API-key mode bills your OpenAI Platform organisation per request. "
                "Repeat with --yes to choose it.",
                err=True,
            )
            raise typer.Exit(code=2)
        saved = credentials.preferences()
        saved["openai_auth"] = use
        credentials.save_preferences(saved)
        typer.echo(f"OpenAI will authenticate with: {use}")
    try:
        if sign_in:
            record = openai_auth.sign_in(client_id=account, announce=typer.echo)
            typer.echo(
                f"signed in: {openai_auth.account_label(record)}; plan usage "
                + ("granted" if record["plan_usage"] else "NOT granted")
            )
        elif account is not None:
            openai_auth.select_account(account)
            typer.echo(f"active account: {account}")
        if sign_out:
            active = openai_auth.active_account()
            if active is None:
                typer.echo("no ChatGPT account is signed in")
            else:
                revoked = openai_auth.sign_out(active)
                typer.echo(
                    "signed out" + ("" if revoked else " (revocation not confirmed)")
                )
    except openai_auth.SignInError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=2) from error
    if not (sign_in or sign_out or account or use):
        current = openai_auth.active_account()
        for record in openai_auth.accounts():
            marker = "*" if record == current else " "
            typer.echo(
                f"{marker} {openai_auth.account_label(record)} "
                f"(client {record['client_id']}; plan usage "
                f"{'granted' if record.get('plan_usage') else 'not granted'})"
            )
        typer.echo("Sign in with `nf-splice provider auth openai --sign-in`.")


@provider_app.command("test")
def provider_test_command(
    name: Annotated[str, typer.Argument(help="Provider name.")],
    model: str | None = typer.Option(None, help="Model to test."),
    allow_remote_model: AllowRemoteOption = False,
    json_output: JsonOption = False,
) -> None:
    """Run one small real turn and check that the model calls an nf-splice tool."""
    import asyncio

    from nf_splice.agents.protocol import require_consent
    from nf_splice.agents.providers.check import tool_call_check

    provider = _make_provider(_provider_name(name), None, model=model)
    _agent_run(lambda: require_consent(provider, allow_remote_model))
    result = _agent_run(lambda: asyncio.run(tool_call_check(provider, model)))
    if json_output:
        typer.echo(dumps(result))
    else:
        typer.echo(
            f"{name}: {'passed' if result['passed'] else 'FAILED'} - {result['detail']}"
        )
    if not result["passed"]:
        raise typer.Exit(code=1)


@app.command("tui")
def tui_command(
    repository: RepositoryOption = Path("."),
    no_session: bool = typer.Option(
        False, "--no-session", help="Do not read or write wizard sessions."
    ),
    provider: str | None = typer.Option(
        None,
        "--provider",
        help="Enable agentic AI in the wizard: claude, or scripted with --script.",
    ),
    script: ScriptOption = None,
    allow_remote_model: AllowRemoteOption = False,
) -> None:
    """Open the terminal wizard: manual, AI-assisted or autonomous."""
    from nf_splice.interfaces.tui import (
        NfSpliceApp,
        SessionStore,
        default_session_directory,
    )

    sessions = SessionStore(
        None if no_session else default_session_directory(repository)
    )
    agent = None
    if provider is not None:
        agent = _make_provider(provider, script)
        if agent.capabilities.remote and not allow_remote_model:
            typer.echo(
                f"--provider {provider} requires --allow-remote-model consent", err=True
            )
            raise typer.Exit(code=2)
    NfSpliceApp(
        repository,
        sessions=sessions,
        actor=_STATE["actor"],
        agent_provider=agent,
        allow_remote_model=allow_remote_model,
    ).run()


def main() -> None:
    """Run the nf-splice command-line interface."""
    app()
