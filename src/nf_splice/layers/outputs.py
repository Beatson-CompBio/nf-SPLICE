"""Output layer: the single editable ``.splice-local/drafts/outputs.draft.yaml``.

The draft is the only authoritative output source. Promotion compiles it,
together with the reviewed identity, into both published files:
``outputs.yaml`` (developer-readable) and ``outputs.schema.json`` (runtime
schema with the embedded ``x-output-catalog``). There is no editable JSON
output draft; JSON previews are derived and never written.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]
from pydantic import ValidationError

from nf_splice.contracts import OUTPUTS_FAMILY, validate_contract_document
from nf_splice.domain import (
    ReviewedOutput,
    expand_output_path_pattern,
)
from nf_splice.drafts import ABSENT, PatchOp, resolve
from nf_splice.inspectors.outputs import published_catalogue
from nf_splice.inspectors.routes import CoverageStatus, analyse_routes, example_path
from nf_splice.layers.base import (
    ChangeContext,
    DraftIssue,
    EditResult,
    LayerError,
    LayerValidation,
    Severity,
    edit_draft,
    issue,
    ops_for,
    read_layer,
    seed_draft,
    strip_marker,
)
from nf_splice.layers.bundle import validate_bundle_draft
from nf_splice.renderers.outputs import (
    CategoryDetails,
    OutputContractError,
    OutputContractInput,
    OutputPipeline,
    render_outputs,
)

LAYER = "outputs"


#: Fields of ``outputs.draft.yaml``. ``excluded_routes`` is draft-only: it
#: records published routes the author deliberately leaves out, with why.
DRAFT_FIELDS = ("contract", "categories", "outputs", "excluded_routes")


def _empty_draft(schema_version: str | None) -> dict[str, Any]:
    return {
        "contract": {"schema_version": schema_version},
        "categories": {},
        "outputs": [],
        "excluded_routes": [],
    }


def _contract_version(explicit: str | None, published: str | None) -> str | None:
    """The analysis-output schema version, never the pipeline's release.

    ``analysis_output_schema_version`` versions this workflow's
    ``analysis_output.json`` document; it changes when that document's shape
    changes, independently of the pipeline release. It is taken from an
    explicit value or a previously published catalogue; otherwise it stays
    null for the author to choose (ADR-0068).
    """
    return explicit if explicit is not None else published


def seed_catalogue(
    root: Path, schema_version: str | None
) -> tuple[dict[str, Any], list[str]]:
    """Build the first ``outputs.draft.yaml``.

    Only the catalogue of a bundle already published in this repository
    (``splice/outputs.yaml``, 0.3.0 or an earlier layout) seeds entries, as
    earlier authoring state to edit. Otherwise the
    catalogue starts with no entries; published routes are evidence to browse
    (:func:`route_coverage`), never provisional entries (ADR-0068).
    """
    published = published_catalogue(root)
    draft = _empty_draft(
        _contract_version(
            schema_version, published.schema_version if published else None
        )
    )
    notes: list[str] = []
    if published is not None and published.outputs:
        draft["outputs"] = [dict(item) for item in published.outputs]
        used = {item.get("category") for item in published.outputs}
        draft["categories"] = {
            key: value
            for key, value in sorted(published.categories.items())
            if key in used and value
        }
        notes.append(
            f"seeded {len(published.outputs)} output(s) from "
            f"{published.location} ({published.format} layout)"
        )
        notes.extend(published.notes)
    else:
        notes.append(
            "the output catalogue starts empty: describe the outputs SPLICE should "
            "expose; published routes can be browsed as evidence"
        )
    return draft, notes


@dataclass(frozen=True, slots=True)
class OutputDiscovery:
    """Result of seeding the draft."""

    created_draft: bool
    notes: tuple[str, ...] = ()


def discover_outputs(
    repository_root: str | Path, *, schema_version: str | None = None
) -> OutputDiscovery:
    """Seed ``outputs.draft.yaml`` if it does not exist; never change it after.

    Re-running changes no byte of an existing draft (ADR-0057).
    """
    root = Path(repository_root).resolve()
    seed, notes = seed_catalogue(root, schema_version)
    created = seed_draft(
        root,
        LAYER,
        seed,
        header=(
            "nf-SPLICE output catalogue draft (authoritative, editable).",
            "Describe each output SPLICE should expose; list published routes "
            "you deliberately",
            "leave out under excluded_routes, with a reason.",
        ),
    )
    return OutputDiscovery(created, tuple(notes) if created else ())


def _draft(root: Path) -> dict[str, Any]:
    state = read_layer(root, LAYER)
    if state.draft is None or not isinstance(state.draft.data, dict):
        raise LayerError(
            f"outputs.draft.yaml is missing or malformed: {state.error or 'absent'}"
        )
    data: dict[str, Any] = state.draft.data
    return data


def _reviewed(output: ReviewedOutput | Mapping[str, Any]) -> ReviewedOutput:
    try:
        return (
            output
            if isinstance(output, ReviewedOutput)
            else ReviewedOutput.model_validate(output)
        )
    except ValidationError as error:
        raise LayerError(f"invalid reviewed output: {error}") from error


def _output_document(output: ReviewedOutput) -> dict[str, Any]:
    document = output.model_dump(mode="json", exclude_none=True)
    if not document.get("labels"):
        document.pop("labels", None)
    return document


def _append_ops(
    data: Mapping[str, Any], outputs: Sequence[ReviewedOutput]
) -> list[PatchOp]:
    existing = data.get("outputs")
    if not isinstance(existing, list):
        raise LayerError("outputs.draft.yaml outputs must be a list")
    keys = {item.get("key") for item in existing if isinstance(item, dict)}
    operations = []
    for offset, output in enumerate(outputs):
        if output.key in keys:
            raise LayerError(f"reviewed output key {output.key!r} is already defined")
        keys.add(output.key)
        operations.append(
            PatchOp(
                "add", f"/outputs/{len(existing) + offset}", _output_document(output)
            )
        )
    return operations


def set_contract_version(
    repository_root: str | Path, schema_version: str, context: ChangeContext
) -> EditResult:
    """Set the reviewed per-pipeline analysis-output schema version."""
    root = Path(repository_root).resolve()
    return edit_draft(
        root,
        LAYER,
        ops_for(_draft(root), {"/contract/schema_version": schema_version}),
        context,
        action="set_contract_version",
    )


def add_output(
    repository_root: str | Path,
    output: ReviewedOutput | Mapping[str, Any],
    context: ChangeContext,
) -> EditResult:
    """Append one complete output to the catalogue (no candidate needed)."""
    root = Path(repository_root).resolve()
    return edit_draft(
        root,
        LAYER,
        _append_ops(_draft(root), [_reviewed(output)]),
        context,
        action="add_output",
    )


def remove_output(
    repository_root: str | Path, key: str, context: ChangeContext
) -> EditResult:
    """Remove one output from the catalogue by key."""
    root = Path(repository_root).resolve()
    data = _draft(root)
    for index, item in enumerate(data.get("outputs") or []):
        if isinstance(item, dict) and item.get("key") == key:
            return edit_draft(
                root,
                LAYER,
                [PatchOp("remove", f"/outputs/{index}", expected=item)],
                context,
                action="remove_output",
            )
    raise LayerError(f"unknown output key {key!r}")


def output_keys(repository_root: str | Path) -> tuple[str, ...]:
    """Keys of the outputs currently in the draft."""
    data = _draft(Path(repository_root).resolve())
    return tuple(
        str(item["key"])
        for item in data.get("outputs") or []
        if isinstance(item, dict) and item.get("key")
    )


def update_output(
    repository_root: str | Path,
    key: str,
    changes: Mapping[str, Any],
    context: ChangeContext,
) -> EditResult:
    """Patch fields of one reviewed output by its stable key."""
    root = Path(repository_root).resolve()
    data = _draft(root)
    index = next(
        (
            position
            for position, item in enumerate(data.get("outputs") or [])
            if isinstance(item, dict) and item.get("key") == key
        ),
        None,
    )
    if index is None:
        raise LayerError(f"unknown reviewed output key {key!r}")
    merged = {**data["outputs"][index], **changes}
    if not _unresolved_fields(merged):
        _reviewed(merged)
    return edit_draft(
        root,
        LAYER,
        ops_for(
            data, {f"/outputs/{index}/{name}": value for name, value in changes.items()}
        ),
        context,
        action="update_output",
    )


def _pipeline(root: Path) -> tuple[OutputPipeline | None, list[DraftIssue]]:
    identity = validate_bundle_draft(root)
    if not identity.ready or identity.metadata is None:
        return None, [
            issue(
                LAYER,
                "",
                "identity_not_ready",
                "bundle.draft.yaml identity must be ready before outputs compile",
            )
        ]
    metadata = identity.metadata
    return (
        OutputPipeline(
            id=metadata.id,
            name=metadata.name,
            version=metadata.version,
            engine=metadata.engine,
            repository_url=metadata.repository_url,
            release_url=metadata.release_url,
        ),
        [],
    )


_UNRESOLVED_HELP = {
    "key": "give it a stable snake_case key",
    "title": "give it a short display title",
    "description": "describe what the output contains scientifically",
    "category": "choose a category (any short label, e.g. quantification)",
    "formats": "list its file format(s), e.g. [tsv]",
    "scopes": "say whether it belongs to the job, a sample or a run",
    "entity_types": "say whether it is a file or a directory",
    "path_patterns": "give an anchored pattern of where it is published",
}


def _unresolved_fields(item: Any) -> list[str]:
    """Required fields a seeded entry still leaves empty (null or [])."""
    if not isinstance(item, Mapping):
        return []
    return [
        name
        for name in _UNRESOLVED_HELP
        if name in item and item[name] in (None, "", [])
    ]


def _label(item: Any, index: int) -> str:
    key = item.get("key") if isinstance(item, Mapping) else None
    return f"output {key!r}" if key else f"output {index}"


#: Why a published route is left out of the catalogue (draft-only, optional):
#: an intermediate the platform need not classify, a route static discovery
#: reported although the pipeline does not publish it, or output outside the
#: integration's scope.
EXCLUSION_KINDS = frozenset({"intermediate", "false_positive", "out_of_scope"})

#: How firmly the code establishes that an uncovered route is published.
ESTABLISHED = "established"
CONDITIONAL = "conditional"
UNVERIFIED = "unverified"


def route_class(route: Any) -> str:
    """Established, conditional (or configuration-dependent) or unverified."""
    if route.status is CoverageStatus.UNRESOLVED:
        return UNVERIFIED
    if route.status is CoverageStatus.INFERRED_UNVERIFIED:
        # Published, but by a default rule, a saveAs or run-time path parts.
        return CONDITIONAL
    if route.conditional or (
        route.publication is not None
        and (route.publication.dynamic or route.publication.enabled)
    ):
        return CONDITIONAL
    return ESTABLISHED


def _exclusions(
    data: Mapping[str, Any],
) -> tuple[list[tuple[str, str]], list[DraftIssue]]:
    """Validated ``excluded_routes``: (kind, value) pairs with a reason each."""
    raw = data.get("excluded_routes") or []
    issues: list[DraftIssue] = []
    found: list[tuple[str, str]] = []
    if not isinstance(raw, list):
        return [], [
            issue(
                LAYER, "/excluded_routes", "invalid_value", "excluded_routes is a list"
            )
        ]
    for index, item in enumerate(raw):
        pointer = f"/excluded_routes/{index}"
        if not isinstance(item, Mapping):
            issues.append(issue(LAYER, pointer, "invalid_value", "expected a mapping"))
            continue
        kinds = [name for name in ("glob", "process") if item.get(name)]
        if len(kinds) != 1:
            issues.append(
                issue(
                    LAYER,
                    pointer,
                    "invalid_value",
                    "name exactly one route: glob (the published path glob) or "
                    "process (the process instance)",
                )
            )
            continue
        kind = item.get("kind")
        if kind is not None and kind not in EXCLUSION_KINDS:
            issues.append(
                issue(
                    LAYER,
                    f"{pointer}/kind",
                    "invalid_value",
                    "kind is one of " + ", ".join(sorted(EXCLUSION_KINDS)),
                )
            )
            continue
        if not str(item.get("reason") or "").strip():
            issues.append(
                issue(
                    LAYER,
                    f"{pointer}/reason",
                    "missing_required",
                    "say why this published route is not in the catalogue",
                )
            )
            continue
        found.append((kinds[0], str(item[kinds[0]])))
    return found, issues


#: Overall route coverage of the catalogue (ADR-0068).
COMPLETE = "complete"
INCOMPLETE = "incomplete"
UNVERIFIED_ROUTES = "unverified"
NOT_ASSESSED = "not_assessed"


@dataclass(frozen=True, slots=True)
class UncoveredRoute:
    """Published paths of one process instance that no output pattern matches."""

    kind: str
    instance: str
    globs: tuple[str, ...]
    location: str | None = None
    condition: str | None = None

    def message(self) -> str:
        place = f" ({self.location})" if self.location else ""
        paths = ", ".join(self.globs)
        if self.kind == ESTABLISHED:
            return (
                f"{self.instance} always publishes {len(self.globs)} path(s) no "
                f"output pattern matches{place}: {paths}"
            )
        if self.kind == CONDITIONAL:
            when = f" ({self.condition})" if self.condition else ""
            return (
                f"{self.instance} publishes {len(self.globs)} path(s){when}{place} "
                f"that no output pattern matches: {paths}"
            )
        return (
            f"static analysis could not establish whether {self.instance} "
            f"publishes {paths}{place}"
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "instance": self.instance,
            "globs": list(self.globs),
            "location": self.location,
            "condition": self.condition,
        }


@dataclass(frozen=True, slots=True)
class RouteCoverage:
    """How far the catalogue covers the routes the pipeline publishes.

    Coverage is evidence for ingestion readiness, never a validation error of
    the entries an author declared (ADR-0068):

    - *established* routes (always published, from the code) and
      *conditional* routes (a branch, ``when:``, an ``enabled`` switch or a
      dynamic path) that no pattern matches make coverage ``incomplete``;
    - *unverified* routes (static analysis could not resolve them) leave
      coverage ``unverified``: it cannot be stated complete;
    - ``not_assessed`` when the routes could not be analysed at all.

    A justified ``excluded_routes`` entry removes a route from the count.
    """

    status: str
    routes: int = 0
    covered: int = 0
    excluded: int = 0
    uncovered: tuple[UncoveredRoute, ...] = ()
    reason: str = ""
    #: (process instance, published glob) of every covered and excluded route.
    covered_routes: tuple[tuple[str, str], ...] = ()
    excluded_routes: tuple[tuple[str, str], ...] = ()

    def of_kind(self, kind: str) -> tuple[UncoveredRoute, ...]:
        return tuple(item for item in self.uncovered if item.kind == kind)

    def summary(self) -> str:
        if self.status == NOT_ASSESSED:
            return f"output coverage not assessed ({self.reason})"
        if self.status == COMPLETE:
            return (
                f"every published route is covered ({self.covered} covered, "
                f"{self.excluded} excluded with a reason)"
            )
        counts = ", ".join(
            f"{len(self.of_kind(kind))} {kind}"
            for kind in (ESTABLISHED, CONDITIONAL, UNVERIFIED)
            if self.of_kind(kind)
        )
        if self.status == INCOMPLETE:
            return f"output coverage incomplete: {counts} route(s) not in the catalogue"
        return f"output coverage not established: {counts} route(s) to check"

    def to_json(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "summary": self.summary(),
            "routes": self.routes,
            "covered": self.covered,
            "excluded": self.excluded,
            "uncovered": [item.to_json() for item in self.uncovered],
            "reason": self.reason,
        }


def _draft_patterns(
    data: Mapping[str, Any],
) -> tuple[list[str], list[tuple[str, str]]]:
    raw_outputs = data.get("outputs") if isinstance(data.get("outputs"), list) else []
    patterns = [
        str(pattern)
        for item in raw_outputs or []
        if isinstance(item, Mapping)
        for pattern in item.get("path_patterns") or []
        if isinstance(pattern, str)
    ]
    exclusions, _issues = _exclusions(data)
    return patterns, exclusions


def route_coverage(
    repository_root: str | Path,
    *,
    patterns: Sequence[str] | None = None,
    exclusions: Sequence[tuple[str, str]] | None = None,
) -> RouteCoverage:
    """Classify every published route as covered, excluded or uncovered.

    ``patterns`` and ``exclusions`` default to the draft's; a caller assessing
    a published bundle passes the published patterns. Read-only and offline.
    """
    root = Path(repository_root).resolve()
    if patterns is None or exclusions is None:
        state = read_layer(root, LAYER)
        if state.draft is None or not isinstance(state.draft.data, dict):
            if patterns is None:
                return RouteCoverage(NOT_ASSESSED, reason="no readable output draft")
            data: Mapping[str, Any] = {}
        else:
            data = strip_marker(state.draft.data)
        draft_patterns, draft_exclusions = _draft_patterns(data)
        patterns = draft_patterns if patterns is None else patterns
        exclusions = draft_exclusions if exclusions is None else exclusions
    try:
        analysis = analyse_routes(root)
    except (OSError, ValueError) as error:
        return RouteCoverage(
            NOT_ASSESSED, reason=f"routes could not be analysed: {error}"
        )
    compiled = []
    for pattern in patterns:
        try:
            compiled.append(re.compile(expand_output_path_pattern(pattern)))
        except (re.error, ValueError):
            continue
    excluded_globs = {value for kind, value in exclusions if kind == "glob"}
    excluded_processes = {value for kind, value in exclusions if kind == "process"}
    # A leading ``*`` directory is usually a run-time choice (the aligner);
    # try it as each first directory the catalogue itself names.
    first_directories = sorted(
        {
            match.group(1)
            for pattern in patterns
            if (match := re.match(r"^\^([A-Za-z0-9_.-]+)/", pattern))
        }
    )
    uncovered: dict[tuple[str, str], list[str]] = {}
    where: dict[str, str] = {}
    conditions: dict[str, str] = {}
    seen: set[str] = set()
    covered_routes: list[tuple[str, str]] = []
    excluded_routes: list[tuple[str, str]] = []
    for route in analysis.published:
        glob = route.published_glob
        if (
            glob is None
            or glob in seen
            or route.status is CoverageStatus.NOT_REACHABLE
            or glob.endswith("versions.yml")
        ):
            continue
        seen.add(glob)
        if (
            glob in excluded_globs
            or route.instance in excluded_processes
            or route.process in excluded_processes
        ):
            excluded_routes.append((route.instance, glob))
            continue
        examples = [example_path(glob)]
        if glob.startswith("*/"):
            examples.extend(
                example_path(f"{name}/{glob[2:]}") for name in first_directories
            )
        if any(
            expression.match(sample) for expression in compiled for sample in examples
        ):
            covered_routes.append((route.instance, glob))
            continue
        kind = route_class(route)
        uncovered.setdefault((kind, route.instance), []).append(glob)
        if route.publication is not None:
            where.setdefault(route.instance, route.publication.location)
        path = next((item for item in route.conditions if item), None)
        if path:
            conditions.setdefault(route.instance, "when " + " and ".join(path)[:160])
        elif route.notes:
            conditions.setdefault(route.instance, route.notes[0])
    found = tuple(
        UncoveredRoute(
            kind,
            instance,
            tuple(sorted(globs)),
            where.get(instance),
            conditions.get(instance) if kind == CONDITIONAL else None,
        )
        for (kind, instance), globs in sorted(uncovered.items())
    )
    kinds = {item.kind for item in found}
    status = (
        INCOMPLETE
        if kinds & {ESTABLISHED, CONDITIONAL}
        else UNVERIFIED_ROUTES
        if kinds
        else COMPLETE
    )
    return RouteCoverage(
        status,
        len(seen),
        len(covered_routes),
        len(excluded_routes),
        found,
        covered_routes=tuple(covered_routes),
        excluded_routes=tuple(excluded_routes),
    )


def _contract_input(
    root: Path, data: Mapping[str, Any]
) -> tuple[OutputContractInput | None, list[DraftIssue]]:
    issues: list[DraftIssue] = []
    unknown = sorted(set(data) - set(DRAFT_FIELDS))
    issues.extend(
        issue(LAYER, f"/{name}", "unknown_field", f"unknown field {name!r}")
        for name in unknown
    )
    version = resolve(data, "/contract/schema_version")
    if version in (ABSENT, None):
        issues.append(
            issue(
                LAYER,
                "/contract/schema_version",
                "missing_required",
                "the analysis-output schema version (X.Y.Z) must be reviewed",
            )
        )
    outputs: list[ReviewedOutput] = []
    raw_outputs = data.get("outputs")
    if not isinstance(raw_outputs, list):
        issues.append(
            issue(LAYER, "/outputs", "invalid_value", "outputs must be a list")
        )
        raw_outputs = []
    if not raw_outputs:
        issues.append(
            issue(
                LAYER,
                "/outputs",
                "missing_required",
                "describe at least one output SPLICE should expose",
            )
        )
    seen: dict[str, int] = {}
    for index, item in enumerate(raw_outputs):
        unresolved = _unresolved_fields(item)
        if unresolved:
            issues.extend(
                issue(
                    LAYER,
                    f"/outputs/{index}/{name}",
                    "unresolved",
                    f"{_label(item, index)}: {name} is not known yet; "
                    f"{_UNRESOLVED_HELP[name]}",
                )
                for name in unresolved
            )
            continue
        try:
            reviewed = ReviewedOutput.model_validate(item)
        except ValidationError as error:
            for detail in error.errors():
                pointer = f"/outputs/{index}" + "".join(
                    f"/{part}" for part in detail["loc"]
                )
                issues.append(issue(LAYER, pointer, "invalid_value", detail["msg"]))
            continue
        if reviewed.key in seen:
            issues.append(
                issue(
                    LAYER,
                    f"/outputs/{index}/key",
                    "duplicate_key",
                    f"output key {reviewed.key!r} is already used at "
                    f"/outputs/{seen[reviewed.key]}",
                )
            )
            continue
        seen[reviewed.key] = index
        outputs.append(reviewed)
    categories: dict[str, CategoryDetails] = {}
    raw_categories = data.get("categories") or {}
    if not isinstance(raw_categories, dict):
        issues.append(
            issue(LAYER, "/categories", "invalid_value", "categories must be a mapping")
        )
        raw_categories = {}
    used = {item.category for item in outputs}
    for label, details in raw_categories.items():
        if label not in used:
            issues.append(
                issue(
                    LAYER,
                    f"/categories/{label}",
                    "unused_category",
                    f"category metadata {label!r} is not used by any output; it "
                    "is left out of the published catalogue",
                    Severity.WARNING,
                )
            )
            continue
        details = details if isinstance(details, dict) else {}
        categories[label] = CategoryDetails(
            title=details.get("title"), description=details.get("description")
        )
    # Route coverage is ingestion-readiness evidence (route_coverage), not a
    # validation error of the declared entries (ADR-0068).
    _exclusions_found, exclusion_issues = _exclusions(data)
    issues.extend(exclusion_issues)
    pipeline, identity_issues = _pipeline(root)
    issues.extend(identity_issues)
    if pipeline is None or any(item.severity is Severity.ERROR for item in issues):
        return None, issues
    return (
        OutputContractInput(
            pipeline=pipeline,
            schema_version=str(version),
            outputs=tuple(outputs),
            categories=categories,
        ),
        issues,
    )


def validate_outputs_draft(repository_root: str | Path) -> LayerValidation:
    """Validate the draft and, if ready, its complete two-file projection."""
    root = Path(repository_root).resolve()
    state = read_layer(root, LAYER)
    if not state.file.exists:
        return LayerValidation(
            LAYER,
            (issue(LAYER, "", "missing_draft", "outputs.draft.yaml does not exist"),),
        )
    if state.draft is None or not isinstance(state.draft.data, dict):
        return LayerValidation(LAYER, (issue(LAYER, "", "syntax", str(state.error)),))
    issues: list[DraftIssue] = [
        issue(LAYER, "", "yaml_warning", warning, Severity.WARNING)
        for warning in state.draft.warnings
    ]
    contract, contract_issues = _contract_input(root, strip_marker(state.draft.data))
    issues.extend(contract_issues)
    if contract is None or any(item.severity is Severity.ERROR for item in issues):
        return LayerValidation(LAYER, tuple(issues))
    try:
        rendered = render_outputs(contract)
    except (OutputContractError, ValueError) as error:
        return LayerValidation(
            LAYER, (*issues, issue(LAYER, "", "compile", str(error)))
        )
    report = validate_contract_document(rendered.schema_document, OUTPUTS_FAMILY)
    for item in report.issues:
        issues.append(
            issue(
                LAYER,
                item.json_pointer,
                "contract",
                item.message,
                path="splice/outputs.schema.json",
            )
        )
    catalogue = yaml.safe_load(rendered.catalogue)
    embedded = rendered.schema_document["x-output-catalog"]
    if not isinstance(embedded, dict) or catalogue["outputs"] != embedded.get(
        "output_types"
    ):
        issues.append(
            issue(LAYER, "", "projection_mismatch", "YAML and JSON catalogues differ")
        )
    if any(item.severity is Severity.ERROR for item in issues):
        return LayerValidation(LAYER, tuple(issues))
    return LayerValidation(
        LAYER,
        tuple(issues),
        {
            "outputs.yaml": rendered.catalogue.encode("utf-8"),
            "outputs.schema.json": rendered.schema.encode("utf-8"),
        },
    )


def preview_outputs(repository_root: str | Path, output_format: str = "json") -> str:
    """Return the derived, non-authoritative prospective published file."""
    validation = validate_outputs_draft(repository_root)
    if not validation.ready:
        blocking = "; ".join(
            f"{item.pointer or '/'}: {item.message}" for item in validation.errors
        )
        raise LayerError(f"outputs draft is not ready: {blocking}")
    name = {"json": "outputs.schema.json", "yaml": "outputs.yaml"}.get(output_format)
    if name is None:
        raise LayerError("preview format must be json or yaml")
    return validation.files[name].decode("utf-8")
