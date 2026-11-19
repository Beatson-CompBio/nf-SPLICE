"""Inputs layer: the SPLICE-owned ``inputs.schema.draft.yaml``.

The draft is a JSON Schema 2020-12 document of submitted runtime parameter
values plus documented SPLICE extensions. Nextflow's ``nextflow_schema.json``
is imported as evidence through an adapter that preserves every standard and
nf-schema keyword; every parameter stays in the contract and receives exactly
one ``x-splice-access`` policy by explicit review.
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from jsonschema.exceptions import SchemaError  # type: ignore[import-untyped]

from nf_splice.contracts import (
    INPUTS_FAMILY,
    contract_extension,
    validate_contract_document,
)
from nf_splice.domain.access import Principal, Visibility
from nf_splice.domain.audit import ChangeOrigin
from nf_splice.drafts import (
    ABSENT,
    PatchOp,
    canonical_json,
    diff,
    merge,
    pointer,
    resolve,
)
from nf_splice.drafts.store import sha256
from nf_splice.inspectors.parameters import parameter_usage
from nf_splice.layers.base import (
    ChangeContext,
    DraftIssue,
    EditResult,
    LayerError,
    LayerValidation,
    ReviewState,
    Severity,
    edit_draft,
    issue,
    load_review_state,
    ops_for,
    read_layer,
    seed_draft,
    strip_marker,
)
from nf_splice.layers.bundle import validate_bundle_draft

LAYER = "inputs"
DIALECT = "https://json-schema.org/draft/2020-12/schema"
SOURCE = "nextflow_schema.json"
_SECRET_NAME = re.compile(r"(?i)(password|passwd|secret|token|credential|api_?key)")


@dataclass(frozen=True, slots=True)
class Parameter:
    """Canonical location and policy of one runnable parameter."""

    name: str
    pointer: str
    group: str | None
    schema: Mapping[str, Any]

    @property
    def editable_by(self) -> tuple[str, ...] | None:
        access = self.schema.get("x-splice-access")
        if not isinstance(access, Mapping):
            return None
        value = access.get("editable_by")
        return tuple(value) if isinstance(value, list) else None


def iter_parameters(document: Mapping[str, Any]) -> Iterator[Parameter]:
    """Yield every top-level runnable parameter in grouped then root order."""
    definitions = document.get("$defs")
    if isinstance(definitions, Mapping):
        for group, definition in definitions.items():
            properties = (
                definition.get("properties")
                if isinstance(definition, Mapping)
                else None
            )
            if isinstance(properties, Mapping):
                for name, schema in properties.items():
                    if isinstance(schema, Mapping):
                        yield Parameter(
                            name,
                            pointer("$defs", group, "properties", name),
                            group,
                            schema,
                        )
    properties = document.get("properties")
    if isinstance(properties, Mapping):
        for name, schema in properties.items():
            if isinstance(schema, Mapping):
                yield Parameter(name, pointer("properties", name), None, schema)


def _rewrite_definitions(value: Any) -> Any:
    """Map nf-schema draft-07 ``definitions``/array ``items`` to 2020-12."""
    if isinstance(value, list):
        return [_rewrite_definitions(item) for item in value]
    if not isinstance(value, dict):
        return value
    result: dict[str, Any] = {}
    for key, item in value.items():
        if key == "$ref" and isinstance(item, str):
            result[key] = item.replace("#/definitions/", "#/$defs/")
        elif key == "definitions" and isinstance(item, dict):
            result["$defs"] = _rewrite_definitions(item)
        elif key == "items" and isinstance(item, list):
            result["prefixItems"] = _rewrite_definitions(item)
        elif (
            key == "additionalItems"
            and "items" in value
            and isinstance(value["items"], list)
        ):
            result["items"] = _rewrite_definitions(item)
        else:
            result[key] = _rewrite_definitions(item)
    return result


def project_nextflow_schema(
    upstream: Mapping[str, Any], identity_reference: Mapping[str, str] | None
) -> tuple[dict[str, Any], list[str]]:
    """Project nf-schema into the SPLICE input contract without loss.

    Returns the projection and the documented mapping notes. Standard and
    nf-schema keywords (``help_text``, ``fa_icon``, ``hidden``,
    ``errorMessage``, ``exists``, ``mimetype``, ``schema``, custom formats and
    unknown extensions) are copied verbatim; only the dialect, ``$id`` and
    SPLICE extensions are added.
    """
    notes: list[str] = []
    converted = _rewrite_definitions(copy.deepcopy(dict(upstream)))
    if "definitions" in upstream:
        notes.append("draft-07 definitions mapped to $defs and $ref rewritten")
    for key in ("$schema", "$id"):
        converted.pop(key, None)
    document: dict[str, Any] = {
        "$schema": DIALECT,
        "$id": None,
        "title": converted.pop("title", None),
        "description": converted.pop("description", None),
        "type": converted.pop("type", "object"),
        "x-splice-contract": contract_extension(INPUTS_FAMILY),
        "x-splice-pipeline": dict(identity_reference) if identity_reference else None,
    }
    document.update(converted)
    for key in ("$id", "title", "description"):
        if document.get(key) is None:
            document.pop(key)
    if "$defs" in document and "allOf" not in document:
        document["allOf"] = [{"$ref": f"#/$defs/{name}"} for name in document["$defs"]]
        notes.append("allOf references generated for documentation groups")
    for parameter in list(iter_parameters(document)):
        target = resolve(document, parameter.pointer)
        assert isinstance(target, dict)
        target["x-splice-source"] = {
            "engine": "nextflow",
            "binding": f"params.{parameter.name}",
            "origin": f"{SOURCE}#{parameter.pointer}",
        }
        # Least privilege until an author decides otherwise (ADR-0057): nobody
        # may override the value at run time, and forms do not show it. An
        # empty list is a valid, deliberate policy, not a missing one.
        target["x-splice-access"] = {"editable_by": []}
        target["x-splice-ui"] = {"visibility": Visibility.HIDDEN.value}
        data_kind = {
            "file-path": "file",
            "directory-path": "directory",
            "path": "path",
            "uri": "uri",
        }.get(str(target.get("format")))
        if data_kind is not None:
            target["x-splice-data"] = {"kind": data_kind} | (
                {"samplesheet": True} if "schema" in target else {}
            )
    return document, notes


def _collisions(document: Mapping[str, Any]) -> list[tuple[str, list[str]]]:
    seen: dict[str, list[Parameter]] = {}
    for parameter in iter_parameters(document):
        seen.setdefault(parameter.name, []).append(parameter)
    return [
        (name, [item.pointer for item in items])
        for name, items in sorted(seen.items())
        if len(items) > 1
    ]


def _identity_reference(root: Path) -> tuple[dict[str, str] | None, str | None]:
    validation = validate_bundle_draft(root)
    if validation.metadata is None:
        return None, None
    metadata = validation.metadata
    reference = metadata.reference()
    identifier = f"{metadata.repository_url.rstrip('/')}/splice/inputs.schema.json"
    return reference, identifier


def _load_upstream(root: Path) -> tuple[dict[str, Any], bytes]:
    path = root / SOURCE
    if path.is_symlink() or not path.is_file():
        raise LayerError(f"{SOURCE} is required to import pipeline parameters")
    payload = path.read_bytes()
    try:
        loaded: object = json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise LayerError(f"invalid {SOURCE}: {error}") from error
    if not isinstance(loaded, dict):
        raise LayerError(f"{SOURCE} must contain a JSON object")
    return loaded, payload


def _provisional_document(root: Path) -> dict[str, Any]:
    """An empty, valid input contract for a pipeline with no nf-schema."""
    reference, identifier = _identity_reference(root)
    document: dict[str, Any] = {
        "$schema": DIALECT,
        "type": "object",
        "x-splice-contract": contract_extension(INPUTS_FAMILY),
        "x-splice-pipeline": dict(reference) if reference else None,
        "properties": {},
    }
    if identifier is not None:
        document = {"$schema": DIALECT, "$id": identifier, **document}
    return document


def import_inputs(repository_root: str | Path) -> bool:
    """Create the input draft from ``nextflow_schema.json`` if absent.

    Every declared parameter is kept, with ``editable_by: []`` and hidden
    presentation. A pipeline without ``nextflow_schema.json`` gets an empty
    contract to author by hand: parameters are never invented from code.
    """
    root = Path(repository_root).resolve()
    if not (root / SOURCE).is_file():
        return seed_draft(
            root,
            LAYER,
            _provisional_document(root),
            header=(
                "nf-SPLICE input contract draft (JSON Schema 2020-12, authoritative).",
                f"No {SOURCE} was found: declare each runnable parameter here, with",
                "x-splice-access.editable_by ([] = nobody may change it at run time).",
            ),
        )
    upstream, payload = _load_upstream(root)
    reference, identifier = _identity_reference(root)
    document, notes = project_nextflow_schema(upstream, reference)
    if identifier is not None:
        document = {"$schema": document.pop("$schema"), "$id": identifier, **document}

    def review(state: ReviewState) -> None:
        state.document["imported"] = {
            "source": SOURCE,
            "sha256": sha256(payload),
            "upstream": upstream,
            "notes": notes,
        }

    return seed_draft(
        root,
        LAYER,
        document,
        header=(
            "nf-SPLICE input contract draft (JSON Schema 2020-12, authoritative).",
            "Every declared parameter is imported with editable_by: [] (nobody may",
            "change it at run time) and hidden; grant user/platform/agent on purpose.",
        ),
        review=review,
    )


@dataclass(frozen=True, slots=True)
class ReimportPlan:
    """Structural difference between the previous and current upstream import."""

    changed: bool
    operations: tuple[PatchOp, ...]
    conflicts: tuple[str, ...]
    upstream_sha256: str


def plan_reimport(repository_root: str | Path) -> ReimportPlan:
    """Compare upstream evidence with the last import (read-only).

    The change between the two upstream projections is applied to the current
    draft as a three-way merge, so manual edits are never reset.
    """
    root = Path(repository_root).resolve()
    upstream, payload = _load_upstream(root)
    review = load_review_state(root, LAYER)
    imported = review.document.get("imported") or {}
    if imported.get("sha256") == sha256(payload):
        return ReimportPlan(False, (), (), sha256(payload))
    previous, _ = project_nextflow_schema(imported.get("upstream") or {}, None)
    current, _ = project_nextflow_schema(upstream, None)
    for key in ("$id", "x-splice-pipeline", "x-splice-contract"):
        previous.pop(key, None)
        current.pop(key, None)
    operations = tuple(diff(previous, current))
    state = read_layer(root, LAYER)
    if state.draft is None:
        raise LayerError("inputs.schema.draft.yaml is missing or malformed")
    _, conflicts = merge(state.draft.data, operations)
    return ReimportPlan(
        True, operations, tuple(item.path for item in conflicts), sha256(payload)
    )


def apply_reimport(repository_root: str | Path, context: ChangeContext) -> EditResult:
    """Apply an approved, conflict-free upstream re-import."""
    root = Path(repository_root).resolve()
    plan = plan_reimport(root)
    if not plan.changed:
        raise LayerError(f"{SOURCE} has not changed since the last import")
    if plan.conflicts:
        raise LayerError(
            "upstream changes overlap manual edits at " + ", ".join(plan.conflicts)
        )
    upstream, _ = _load_upstream(root)

    def record(state: ReviewState) -> None:
        imported = state.document.setdefault("imported", {})
        imported.update({"sha256": plan.upstream_sha256, "upstream": upstream})

    return edit_draft(
        root,
        LAYER,
        plan.operations,
        context,
        action="reimport_nextflow_schema",
        confirm=False,
        review=record,
    )


def _draft(root: Path) -> dict[str, Any]:
    state = read_layer(root, LAYER)
    if state.draft is None or not isinstance(state.draft.data, dict):
        raise LayerError("inputs.schema.draft.yaml is missing or malformed")
    data: dict[str, Any] = state.draft.data
    return data


def set_access(
    repository_root: str | Path,
    names: Sequence[str],
    editable_by: Sequence[str],
    context: ChangeContext,
    *,
    visibility: str | None = None,
    write: bool = True,
) -> EditResult:
    """Set the single access policy of one or more parameters.

    Agents may propose policies but cannot change access without a separate
    human approver; principals are validated, never self-asserted.
    """
    root = Path(repository_root).resolve()
    try:
        principals = sorted({Principal(item).value for item in editable_by})
        selected_visibility = Visibility(visibility).value if visibility else None
    except ValueError as error:
        raise LayerError(str(error)) from error
    if (
        context.origin is ChangeOrigin.AGENT_ASSISTED
        and write
        and context.approved_by is None
    ):
        raise LayerError(
            "an assisting agent cannot change parameter access without the "
            "user's approval of the stage"
        )
    data = _draft(root)
    by_name = {item.name: item for item in iter_parameters(data)}
    unknown = sorted(set(names) - set(by_name))
    if unknown:
        raise LayerError(f"unknown parameter(s): {', '.join(unknown)}")
    changes: dict[str, Any] = {}
    for name in names:
        parameter = by_name[name]
        changes[f"{parameter.pointer}/x-splice-access"] = {"editable_by": principals}
        if selected_visibility is not None:
            ui = dict(parameter.schema.get("x-splice-ui") or {})
            ui["visibility"] = selected_visibility
            changes[f"{parameter.pointer}/x-splice-ui"] = ui
    return edit_draft(
        root, LAYER, ops_for(data, changes), context, action="set_access", write=write
    )


def update_parameter(
    repository_root: str | Path,
    name: str,
    changes: Mapping[str, Any],
    context: ChangeContext,
) -> EditResult:
    """Patch schema keywords of one parameter (not its access policy)."""
    if "x-splice-access" in changes:
        raise LayerError("use set_access to change parameter access")
    root = Path(repository_root).resolve()
    data = _draft(root)
    parameter = next(
        (item for item in iter_parameters(data) if item.name == name), None
    )
    if parameter is None:
        raise LayerError(f"unknown parameter {name!r}")
    return edit_draft(
        root,
        LAYER,
        ops_for(
            data,
            {f"{parameter.pointer}/{key}": value for key, value in changes.items()},
        ),
        context,
        action="update_parameter",
    )


def sync_identity(repository_root: str | Path, context: ChangeContext) -> EditResult:
    """Update only the identity envelope and ``$id`` from bundle.draft.yaml."""
    root = Path(repository_root).resolve()
    reference, identifier = _identity_reference(root)
    if reference is None:
        raise LayerError("bundle.draft.yaml identity is not valid")
    return edit_draft(
        root,
        LAYER,
        ops_for(_draft(root), {"/x-splice-pipeline": reference, "/$id": identifier}),
        context,
        action="sync_identity",
    )


def _ref_issues(document: Mapping[str, Any]) -> list[DraftIssue]:
    found = []

    def walk(value: Any, location: str) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                child = f"{location}/{key}"
                if key == "$ref" and isinstance(item, str) and item.startswith("#"):
                    if resolve(document, item[1:]) is ABSENT:
                        found.append(
                            issue(
                                LAYER,
                                child,
                                "unresolved_ref",
                                f"{item} does not resolve",
                            )
                        )
                walk(item, child)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{location}/{index}")

    walk(document, "")
    return found


def validate_inputs_draft(repository_root: str | Path) -> LayerValidation:
    """Validate the input contract draft and compile it when ready."""
    root = Path(repository_root).resolve()
    state = read_layer(root, LAYER)
    if not state.file.exists:
        return LayerValidation(
            LAYER, (issue(LAYER, "", "missing_draft", "inputs draft does not exist"),)
        )
    if state.draft is None or not isinstance(state.draft.data, dict):
        return LayerValidation(LAYER, (issue(LAYER, "", "syntax", str(state.error)),))
    document = strip_marker(state.draft.data)
    issues: list[DraftIssue] = [
        issue(LAYER, "", "yaml_warning", warning, Severity.WARNING)
        for warning in state.draft.warnings
    ]
    if document.get("$schema") != DIALECT:
        issues.append(issue(LAYER, "/$schema", "dialect", f"$schema must be {DIALECT}"))
    try:
        Draft202012Validator.check_schema(document)
    except SchemaError as error:
        issues.append(
            issue(
                LAYER,
                "".join(f"/{part}" for part in error.absolute_path),
                "invalid_schema",
                error.message,
            )
        )
    issues.extend(_ref_issues(document))
    if document.get("x-splice-contract") != contract_extension(INPUTS_FAMILY):
        issues.append(
            issue(
                LAYER,
                "/x-splice-contract",
                "contract_metadata",
                "x-splice-contract must declare the current inputs contract revision",
            )
        )
    reference, identifier = _identity_reference(root)
    if reference is None:
        issues.append(
            issue(
                LAYER, "/x-splice-pipeline", "identity_not_ready", "identity is invalid"
            )
        )
    elif (
        document.get("x-splice-pipeline") != reference
        or document.get("$id") != identifier
    ):
        issues.append(
            issue(
                LAYER,
                "/x-splice-pipeline",
                "identity_mismatch",
                "pipeline identity differs from bundle.draft.yaml; run "
                "`nf-splice draft sync-identity` to copy it",
            )
        )
    for name, pointers in _collisions(document):
        issues.append(
            issue(
                LAYER,
                pointers[1],
                "parameter_collision",
                f"parameter {name!r} is defined more than once: {', '.join(pointers)}",
            )
        )
    for parameter in iter_parameters(document):
        policy = parameter.editable_by
        if policy is None:
            issues.append(
                issue(
                    LAYER,
                    f"{parameter.pointer}/x-splice-access",
                    "access_unreviewed",
                    f"parameter {parameter.name!r} needs a reviewed access policy",
                )
            )
        if _SECRET_NAME.search(parameter.name) and parameter.schema.get("default"):
            issues.append(
                issue(
                    LAYER,
                    f"{parameter.pointer}/default",
                    "secret_default",
                    "secret-like parameters must not carry default values",
                )
            )
    from nf_splice.services.readiness import indispensable_parameters

    policies = {item.name: item for item in iter_parameters(document)}
    for name, why in indispensable_parameters(document):
        required = policies.get(name)
        if required is not None and not required.editable_by:
            issues.append(
                issue(
                    LAYER,
                    f"{required.pointer}/x-splice-access",
                    "unsupplied_required",
                    f"{name} ({why}) has no default and nobody may supply it; a "
                    "job cannot start unless a principal may set it or the "
                    "default profile's config sets it",
                    Severity.WARNING,
                )
            )
    declared = {item.name for item in iter_parameters(document)}
    for usage in parameter_usage(root).undeclared(declared)[:25]:
        issues.append(
            issue(
                LAYER,
                "/properties",
                "undeclared_parameter",
                f"workflow code reads params.{usage.name} "
                f"({', '.join(usage.code[:3])}) but the contract does not "
                "declare it; declare it if a job may set it, otherwise ignore "
                "this (a value the pipeline sets for itself)",
                Severity.WARNING,
            )
        )
    if any(item.severity is Severity.ERROR for item in issues):
        return LayerValidation(LAYER, tuple(issues))
    payload = canonical_json(document)
    report = validate_contract_document(json.loads(payload), INPUTS_FAMILY)
    issues.extend(
        issue(LAYER, item.json_pointer, "contract", item.message)
        for item in report.issues
    )
    if not report.valid:
        return LayerValidation(LAYER, tuple(issues))
    return LayerValidation(LAYER, tuple(issues), {"inputs.schema.json": payload})
