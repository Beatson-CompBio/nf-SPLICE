"""Three independent assessments of a bundle and its output evidence.

1. **Contract validity**: the deterministic validators accept the published
   bundle and its cross-file relationships.
2. **Observed-output compatibility**: one completed job's results (an example
   directory, saved listing or output index) can be classified against the
   catalogue, and a real ``analysis_output.json`` validates.
3. **Coverage assessment**: which statically identified publication routes
   the catalogue covers, which an example observed, and what stays
   unresolved.

None implies another. A valid bundle does not prove every route is covered;
a valid example inventory proves only that one run's outputs are classified.
An example is observational evidence of the routes one run took; catalogue
types it does not contain are expected for alternative or optional routes.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any

from nf_splice.domain import expand_output_path_pattern
from nf_splice.inspectors.routes import (
    CoverageStatus,
    RouteAnalysis,
    analyse_routes,
    example_path,
    glob_to_regex,
)
from nf_splice.layers import LayerError
from nf_splice.layers.base import load_review_state, read_layer
from nf_splice.runtime import (
    ANALYSIS_OUTPUT_FILENAME,
    AnalysisOutputError,
    generate_analysis_output,
    load_output_catalogue,
    output_type_order,
    read_output_listing,
)
from nf_splice.services.checks import CheckResult, detect_tools, run_optional_checks
from nf_splice.services.lifecycle import plan_promotion, validate_bundle

_MAX_EXAMPLE_ENTRIES = 50_000
#: Job identity used only to validate an example inventory during assessment.
PLACEHOLDER_JOB_ID = "00000000-0000-0000-0000-000000000000"
_PARTIAL_SUFFIXES = (".tmp", ".part", ".partial", ".incomplete")


class ExampleKind(str, Enum):
    """How example output evidence was supplied."""

    DIRECTORY = "directory"
    LISTING = "listing"
    INDEX = "index"


@dataclass(frozen=True, slots=True)
class ExampleEntry:
    """One observed path, relative to the example root."""

    path: str
    is_directory: bool
    size: int | None = None


@dataclass(frozen=True, slots=True)
class ExampleEnumeration:
    """Safely enumerated example entries and what limits their value."""

    source: str
    kind: ExampleKind
    entries: tuple[ExampleEntry, ...]
    limitations: tuple[str, ...]


def example_kind(path: Path) -> ExampleKind:
    """A directory, an output index (.json/.yaml/.csv/.tsv) or a listing."""
    if path.is_dir():
        return ExampleKind.DIRECTORY
    if path.suffix.lower() in {".json", ".yaml", ".yml", ".csv", ".tsv"}:
        return ExampleKind.INDEX
    return ExampleKind.LISTING


def enumerate_example(
    path: str | Path, *, limit: int = _MAX_EXAMPLE_ENTRIES
) -> ExampleEnumeration:
    """List an example without leaving its root or following symlinks."""
    source = Path(path).resolve()
    if not source.exists():
        raise LayerError(f"example output does not exist: {path}")
    kind = example_kind(source)
    limitations: list[str] = []
    entries: list[ExampleEntry] = []
    if kind is ExampleKind.DIRECTORY:
        symlinks = 0
        for current, directory_names, file_names in os.walk(source, followlinks=False):
            current_path = Path(current)
            kept = []
            for name in sorted(directory_names):
                child = current_path / name
                if child.is_symlink():
                    symlinks += 1
                    continue
                kept.append(name)
                entries.append(ExampleEntry(child.relative_to(source).as_posix(), True))
            directory_names[:] = kept
            for name in sorted(file_names):
                child = current_path / name
                if child.is_symlink():
                    symlinks += 1
                    continue
                relative = child.relative_to(source).as_posix()
                if relative == ANALYSIS_OUTPUT_FILENAME:
                    continue
                entries.append(ExampleEntry(relative, False, child.stat().st_size))
            if len(entries) > limit:
                break
        if symlinks:
            limitations.append(
                f"{symlinks} symbolic link(s) were skipped and never followed"
            )
        empty = [item.path for item in entries if item.size == 0]
        if empty:
            limitations.append(
                f"{len(empty)} empty file(s), e.g. {empty[0]}; the run or the "
                "transfer may be incomplete"
            )
    else:
        try:
            listed = read_output_listing(source)
        except (AnalysisOutputError, ValueError, OSError) as error:
            raise LayerError(f"cannot read example listing {path}: {error}") from error
        entries = [ExampleEntry(item, is_directory) for item, is_directory in listed]
        limitations.append(
            "a saved listing or index cannot show file sizes or detect symlinks"
        )
    for item in entries:
        pure = PurePosixPath(item.path)
        if pure.is_absolute() or ".." in pure.parts:
            raise LayerError(f"example path is not safely relative: {item.path!r}")
    if len(entries) > limit:
        entries = entries[:limit]
        limitations.append(f"only the first {limit} entries were examined")
    partial = [item.path for item in entries if item.path.endswith(_PARTIAL_SUFFIXES)]
    if partial:
        limitations.append(
            f"{len(partial)} partially written file(s), e.g. {partial[0]}"
        )
    if not any(not item.is_directory for item in entries):
        limitations.append("the example contains no files")
    return ExampleEnumeration(str(source), kind, tuple(entries), tuple(limitations))


# ------------------------------------------------------------ catalogue


@dataclass(frozen=True, slots=True)
class Catalogue:
    """Output types used for reconciliation, and where they came from."""

    source: str
    output_types: tuple[dict[str, Any], ...]


def draft_catalogue(repository_root: str | Path) -> Catalogue:
    """Reviewed outputs from ``outputs.draft.yaml`` in runtime shape."""
    root = Path(repository_root).resolve()
    state = read_layer(root, "outputs")
    if state.draft is None or not isinstance(state.draft.data, dict):
        raise LayerError("outputs.draft.yaml is missing or malformed")
    types = []
    for item in state.draft.data.get("outputs") or []:
        if not isinstance(item, dict) or not item.get("key"):
            continue
        types.append(
            {
                "key": str(item["key"]),
                "category": item.get("category"),
                "scope": list(item.get("scopes") or []),
                "entity_type": list(item.get("entity_types") or []),
                "format": list(item.get("formats") or []),
                "path_patterns": [
                    str(value) for value in item.get("path_patterns") or []
                ],
            }
        )
    return Catalogue(".splice-local/drafts/outputs.draft.yaml", tuple(types))


def current_catalogue(repository_root: str | Path) -> Catalogue | None:
    """The draft catalogue, or the published one when no draft exists."""
    root = Path(repository_root).resolve()
    try:
        return draft_catalogue(root)
    except LayerError:
        pass
    try:
        published = load_output_catalogue(root)
    except AnalysisOutputError:
        return None
    return Catalogue("splice/outputs.schema.json", published.output_types)


def _compiled(
    output_types: Sequence[Mapping[str, Any]],
) -> list[tuple[str, re.Pattern[str], set[str], set[str]]]:
    compiled = []
    order = {
        key: index
        for index, key in enumerate(
            output_type_order(tuple(dict(item) for item in output_types))
        )
    }
    for item in sorted(output_types, key=lambda value: order.get(str(value["key"]), 0)):
        for pattern in item.get("path_patterns", []):
            try:
                expression = re.compile(expand_output_path_pattern(str(pattern)))
            except (re.error, ValueError):
                continue
            compiled.append(
                (
                    str(item["key"]),
                    expression,
                    set(item.get("entity_type") or ["file"]),
                    set(item.get("scope") or []),
                )
            )
    return compiled


# ------------------------------------------------------------ reconciliation


@dataclass(frozen=True, slots=True)
class Reconciliation:
    """How one example's entries map onto the catalogue."""

    example: str
    kind: ExampleKind
    catalogue_source: str
    entries: int
    classified: dict[str, int]
    unclassified: tuple[str, ...]
    ambiguous: tuple[dict[str, Any], ...]
    not_observed: tuple[str, ...]
    identifier_issues: tuple[str, ...]
    limitations: tuple[str, ...]

    @property
    def compatible(self) -> bool:
        return not (self.unclassified or self.ambiguous or self.identifier_issues)

    def to_json(self) -> dict[str, Any]:
        return {
            "example": self.example,
            "kind": self.kind.value,
            "catalogue_source": self.catalogue_source,
            "entries": self.entries,
            "classified": dict(self.classified),
            "unclassified": list(self.unclassified),
            "ambiguous": list(self.ambiguous),
            "not_observed": list(self.not_observed),
            "identifier_issues": list(self.identifier_issues),
            "limitations": list(self.limitations),
            "compatible": self.compatible,
        }


def reconcile_example(
    catalogue: Catalogue, enumeration: ExampleEnumeration
) -> Reconciliation:
    """Classify each observed entry: classified, unclassified or ambiguous.

    Catalogue output types that the example does not contain are reported as
    ``not_observed``; that is expected for alternative or optional routes and
    is never a failure.
    """
    compiled = _compiled(catalogue.output_types)
    entries = list(enumeration.entries)
    directory_prefixes: list[str] = []
    for entry in entries:
        if entry.is_directory:
            for _key, expression, entities, _scopes in compiled:
                if "directory" in entities and expression.match(entry.path):
                    directory_prefixes.append(f"{entry.path}/")
                    break
    all_paths = {item.path for item in entries}
    classified: dict[str, int] = {}
    unclassified: list[str] = []
    ambiguous: list[dict[str, Any]] = []
    identifier_issues: list[str] = []
    for entry in sorted(entries, key=lambda item: item.path):
        if any(entry.path.startswith(prefix) for prefix in directory_prefixes):
            continue
        entity = "directory" if entry.is_directory else "file"
        hits = [
            (key, match, scopes)
            for key, expression, entities, scopes in compiled
            if entity in entities and (match := expression.match(entry.path))
        ]
        keys = list(dict.fromkeys(key for key, _match, _scopes in hits))
        if not keys:
            is_container = entry.is_directory and any(
                other != entry.path and other.startswith(f"{entry.path}/")
                for other in all_paths
            )
            if not is_container:
                unclassified.append(entry.path)
            continue
        if len(keys) > 1:
            ambiguous.append(
                {"path": entry.path, "output_types": keys, "runtime_choice": keys[0]}
            )
        key, match, scopes = hits[0]
        classified[key] = classified.get(key, 0) + 1
        groups = match.groupdict()
        if "job" not in scopes and not (
            groups.get("sample_id") or groups.get("run_id")
        ):
            identifier_issues.append(
                f"{entry.path} matches {key!r} (scopes {sorted(scopes)}) but its "
                "pattern captures no sample or run identifier"
            )
    not_observed = tuple(
        sorted(
            str(item["key"])
            for item in catalogue.output_types
            if str(item["key"]) not in classified
        )
    )
    limitations = list(enumeration.limitations)
    if not_observed and classified:
        limitations.append(
            f"{len(not_observed)} catalogue output type(s) were not observed; they "
            "may belong to routes or options this run did not use"
        )
    return Reconciliation(
        example=enumeration.source,
        kind=enumeration.kind,
        catalogue_source=catalogue.source,
        entries=len(entries),
        classified=classified,
        unclassified=tuple(unclassified),
        ambiguous=tuple(ambiguous),
        not_observed=not_observed,
        identifier_issues=tuple(identifier_issues),
        limitations=tuple(limitations),
    )


# ------------------------------------------------------------ assessment


def _route_catalogue_keys(
    glob: str | None, compiled: list[tuple[str, re.Pattern[str], set[str], set[str]]]
) -> list[str]:
    if glob is None:
        return []
    sample = example_path(glob)
    return list(
        dict.fromkeys(
            key for key, expression, _e, _s in compiled if expression.match(sample)
        )
    )


def _rejected_patterns(root: Path) -> set[str]:
    """Patterns of candidates rejected with the optional review tools."""
    try:
        state = load_review_state(root, "outputs")
    except (LayerError, OSError, ValueError):
        return set()
    patterns = set()
    for entry in state.candidates.values():
        if isinstance(entry, dict) and entry.get("status") == "rejected":
            pattern = (entry.get("candidate") or {}).get("path_pattern")
            if pattern:
                patterns.add(str(pattern))
    return patterns


def _excluded_routes(root: Path) -> tuple[set[str], set[str]]:
    """(globs, processes) the author excluded in ``outputs.draft.yaml``."""
    try:
        state = read_layer(root, "outputs")
    except (LayerError, OSError, ValueError):
        return set(), set()
    if state.draft is None or not isinstance(state.draft.data, dict):
        return set(), set()
    globs, processes = set(), set()
    for item in state.draft.data.get("excluded_routes") or []:
        if isinstance(item, dict) and str(item.get("reason") or "").strip():
            if item.get("glob"):
                globs.add(str(item["glob"]))
            if item.get("process"):
                processes.add(str(item["process"]))
    return globs, processes


@dataclass(frozen=True, slots=True)
class CoverageReport:
    """Route-by-route coverage against the catalogue and examples."""

    routes: tuple[dict[str, Any], ...]
    unpublished: tuple[dict[str, Any], ...]
    summary: dict[str, int]
    all_identified_routes_covered: bool
    statement: str
    notes: tuple[str, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "routes": list(self.routes),
            "unpublished": list(self.unpublished),
            "summary": dict(self.summary),
            "all_identified_routes_covered": self.all_identified_routes_covered,
            "statement": self.statement,
            "notes": list(self.notes),
        }


def assess_coverage(
    repository_root: str | Path,
    *,
    catalogue: Catalogue | None,
    examples: Iterable[ExampleEnumeration] = (),
    analysis: RouteAnalysis | None = None,
) -> CoverageReport:
    """Map statically identified routes to the catalogue and to examples."""
    root = Path(repository_root).resolve()
    analysis = analysis or analyse_routes(root)
    compiled = _compiled(catalogue.output_types) if catalogue else []
    rejected = _rejected_patterns(root)
    excluded_globs, excluded_processes = _excluded_routes(root)
    observed_paths = [item.path for example in examples for item in example.entries]
    routes = []
    summary = {
        "published_routes": len(analysis.published),
        "in_catalogue": 0,
        "excluded_by_review": 0,
        "not_in_catalogue": 0,
        "observed_in_example": 0,
        "unresolved": 0,
        "not_reachable": 0,
        "unpublished_declared_outputs": len(analysis.unpublished),
    }
    for route in analysis.published:
        document = route.to_json()
        keys = _route_catalogue_keys(route.published_glob, compiled)
        pattern = glob_to_regex(route.published_glob) if route.published_glob else None
        observed = bool(
            pattern and any(re.match(pattern, path) for path in observed_paths)
        )
        document["static_status"] = route.status.value
        if observed:
            document["status"] = CoverageStatus.OBSERVED_IN_EXAMPLE.value
            summary["observed_in_example"] += 1
        document["catalogue_keys"] = keys
        if keys:
            document["catalogue"] = "covered"
            summary["in_catalogue"] += 1
        elif (
            pattern in rejected
            or route.published_glob in excluded_globs
            or route.instance in excluded_processes
            or route.process in excluded_processes
        ):
            document["catalogue"] = "excluded_by_review"
            summary["excluded_by_review"] += 1
        else:
            document["catalogue"] = "not_covered"
            summary["not_in_catalogue"] += 1
        if route.status is CoverageStatus.UNRESOLVED:
            summary["unresolved"] += 1
        if route.status is CoverageStatus.NOT_REACHABLE:
            summary["not_reachable"] += 1
        routes.append(document)
    covered = (
        catalogue is not None
        and summary["not_in_catalogue"] == 0
        and summary["unresolved"] == 0
    )
    statement = (
        f"{summary['published_routes']} published route(s) were identified "
        f"statically: {summary['in_catalogue']} covered by the catalogue, "
        f"{summary['excluded_by_review']} excluded by the author, "
        f"{summary['not_in_catalogue']} not covered, {summary['unresolved']} "
        f"unresolved. {summary['observed_in_example']} were observed in example "
        "output. Static analysis cannot prove completeness: outputs named at run "
        "time, saveAs renaming and configuration supplied when the pipeline is "
        "launched can publish files it does not see."
    )
    notes = list(analysis.notes)
    if catalogue is None:
        notes.append("no outputs catalogue exists yet; coverage is routes only")
    return CoverageReport(
        routes=tuple(routes),
        unpublished=tuple(item.to_json() for item in analysis.unpublished),
        summary=summary,
        all_identified_routes_covered=covered,
        statement=statement,
        notes=tuple(notes),
    )


@dataclass(frozen=True, slots=True)
class ObservedOutputs:
    """Compatibility of one example with the catalogue and runtime contract."""

    reconciliation: Reconciliation
    analysis_output: dict[str, Any]

    @property
    def compatible(self) -> bool:
        return self.reconciliation.compatible and self.analysis_output.get(
            "status"
        ) in {"valid", "not_run"}

    def to_json(self) -> dict[str, Any]:
        return {
            "compatible": self.compatible,
            "reconciliation": self.reconciliation.to_json(),
            "analysis_output": dict(self.analysis_output),
        }


def _analysis_output(
    root: Path, enumeration: ExampleEnumeration, output_directory: Path | None
) -> dict[str, Any]:
    if not (root / "splice" / "outputs.schema.json").is_file():
        return {
            "status": "not_run",
            "reason": "the bundle is not built yet (splice/outputs.schema.json)",
        }
    source = Path(enumeration.source)
    arguments: dict[str, Any] = {
        ExampleKind.DIRECTORY: {"publish_directory": source},
        ExampleKind.INDEX: {"native_output_index": source},
        ExampleKind.LISTING: {"output_tree": source},
    }[enumeration.kind]
    try:
        result = generate_analysis_output(
            root,
            output_directory=output_directory,
            job_metadata={"job_id_long": PLACEHOLDER_JOB_ID},
            **arguments,
        )
    except (AnalysisOutputError, ValueError, OSError) as error:
        return {"status": "invalid", "reason": str(error)}
    return {
        "status": "valid",
        "records": result.validation.record_count,
        "path": str(result.path) if result.path else None,
        "reason": "generated from observed paths only and validated against "
        "splice/outputs.schema.json; the job identity is the nil UUID placeholder "
        f"{PLACEHOLDER_JOB_ID!r}, so generate the real file for a job with "
        "`nf-splice analysis-output generate`",
    }


@dataclass(frozen=True, slots=True)
class Assessment:
    """The three independent results, plus optional external checks."""

    contract: dict[str, Any]
    observed: tuple[ObservedOutputs, ...]
    coverage: CoverageReport
    optional_checks: tuple[CheckResult, ...]
    tools: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    @property
    def contract_valid(self) -> bool:
        return self.contract.get("status") == "valid"

    def to_json(self) -> dict[str, Any]:
        return {
            "contract_validity": dict(self.contract),
            "observed_output_compatibility": {
                "status": (
                    "not_assessed"
                    if not self.observed
                    else "compatible"
                    if all(item.compatible for item in self.observed)
                    else "incompatible"
                ),
                "examples": [item.to_json() for item in self.observed],
                "note": "no example output was supplied; this is evidence of "
                "no particular run, not a failure"
                if not self.observed
                else "each example is evidence of the routes one run took",
            },
            "coverage_assessment": self.coverage.to_json(),
            "optional_checks": [item.to_json() for item in self.optional_checks],
            "tools": list(self.tools),
        }


def contract_validity(repository_root: str | Path) -> dict[str, Any]:
    """Deterministic validation of the published bundle, or draft readiness."""
    root = Path(repository_root).resolve()
    if (root / "splice" / "bundle.json").is_file():
        report = validate_bundle(root)
        return {
            "status": "valid" if report.valid else "invalid",
            "checked_files": report.checked_files,
            "issues": [item.to_json() for item in report.issues],
        }
    try:
        plan = plan_promotion(root)
    except ValueError as error:
        return {"status": "not_built", "ready_to_build": False, "issues": [str(error)]}
    return {
        "status": "not_built",
        "ready_to_build": plan.ready,
        "issues": [
            f"{item.layer}{item.pointer}: {item.message}" for item in plan.blockers
        ],
    }


def assess(
    repository_root: str | Path,
    *,
    examples: Sequence[str | Path] = (),
    permitted: Collection[str] = (),
    analysis_output_directory: str | Path | None = None,
    run_checks: bool = True,
) -> Assessment:
    """Compute the three assessments; never writes to the repository."""
    root = Path(repository_root).resolve()
    catalogue = current_catalogue(root)
    enumerations = [enumerate_example(item) for item in examples]
    observed = []
    directory = (
        Path(analysis_output_directory).resolve()
        if analysis_output_directory is not None
        else None
    )
    for index, enumeration in enumerate(enumerations):
        target = None
        if directory is not None:
            target = directory / f"example-{index + 1}"
            target.mkdir(parents=True, exist_ok=True)
        reconciliation = (
            reconcile_example(catalogue, enumeration)
            if catalogue is not None
            else Reconciliation(
                example=enumeration.source,
                kind=enumeration.kind,
                catalogue_source="none",
                entries=len(enumeration.entries),
                classified={},
                unclassified=tuple(
                    item.path for item in enumeration.entries if not item.is_directory
                ),
                ambiguous=(),
                not_observed=(),
                identifier_issues=(),
                limitations=(*enumeration.limitations, "no outputs catalogue exists"),
            )
        )
        observed.append(
            ObservedOutputs(reconciliation, _analysis_output(root, enumeration, target))
        )
    return Assessment(
        contract=contract_validity(root),
        observed=tuple(observed),
        coverage=assess_coverage(root, catalogue=catalogue, examples=enumerations),
        optional_checks=run_optional_checks(root, permitted=permitted)
        if run_checks
        else (),
        tools=tuple(item.to_json() for item in detect_tools()),
    )


def dumps(assessment: Assessment) -> str:
    """Stable JSON for one assessment."""
    return json.dumps(assessment.to_json(), indent=2, ensure_ascii=False) + "\n"
