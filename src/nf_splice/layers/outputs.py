"""Output layer: the single editable ``.splice-local/drafts/outputs.draft.yaml``.

The draft is the only authoritative output source. Promotion compiles it,
together with the reviewed identity, into both published files:
``outputs.yaml`` (developer-readable) and ``outputs.schema.json`` (runtime
schema with the embedded ``x-output-catalog``). There is no editable JSON
output draft; JSON previews are derived and never written.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]
from pydantic import ValidationError

from nf_splice.contracts import OUTPUTS_FAMILY, validate_contract_document
from nf_splice.domain import (
    OutputCandidate,
    OutputScope,
    ReviewedOutput,
    expand_output_path_pattern,
)
from nf_splice.drafts import ABSENT, PatchOp, resolve
from nf_splice.inspectors import discover_output_candidates
from nf_splice.inspectors.outputs import published_catalogue
from nf_splice.inspectors.routes import CoverageStatus, analyse_routes, example_path
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
    record_decision,
    seed_draft,
    strip_marker,
    update_review_state,
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
PENDING = "pending"
ACCEPTED = "accepted"
REJECTED = "rejected"
MERGED = "merged"
SPLIT = "split"


#: Fields of ``outputs.draft.yaml``. ``excluded_routes`` is draft-only: it
#: records published routes the author deliberately leaves out, with why.
DRAFT_FIELDS = ("contract", "categories", "outputs", "excluded_routes")
SEEDED = "seeded"
_SEMVER = re.compile(r"^v?(\d+\.\d+\.\d+)$")
#: Provisional category from the producing tool's name. Hints only: the seed
#: says so, and the author or an agent replaces them with the real meaning.
_CATEGORY_HINTS = (
    (("multiqc",), "aggregate_qc"),
    (
        ("pipeline_info", "software_versions", "dumpsoftware", "custom_dump"),
        "job_report",
    ),
    (("samplesheet", "check_samplesheet"), "sample_metadata"),
    (("umi", "umitools", "umicollapse"), "umi"),
    (
        ("fastp", "trimgalore", "cutadapt", "trim", "sortmerna", "bbsplit", "fq_"),
        "preprocessing",
    ),
    (
        (
            "fastqc",
            "qualimap",
            "rseqc",
            "dupradar",
            "preseq",
            "biotype",
            "deseq2_qc",
            "qc",
        ),
        "quality_control",
    ),
    (("star_align", "hisat2_align", "bowtie", "bwa", "_align"), "alignment"),
    (("markduplicates", "picard", "samtools", "sort", "dedup"), "postprocessing"),
    (("bedgraph", "bigwig", "genomecov", "coverage"), "coverage"),
    (
        (
            "salmon",
            "rsem",
            "featurecounts",
            "kallisto",
            "htseq",
            "stringtie",
            "tximport",
            "tximeta",
            "quant",
            "summarizedexperiment",
        ),
        "quantification",
    ),
    (
        (
            "genome",
            "index",
            "gtf",
            "fasta",
            "gffread",
            "build",
            "reference",
            "chromsizes",
        ),
        "reference",
    ),
)
_REFERENCE_PREFIXES = ("genome/", "reference/", "references/", "index/")


def _empty_draft(schema_version: str | None) -> dict[str, Any]:
    return {
        "contract": {"schema_version": schema_version},
        "categories": {},
        "outputs": [],
        "excluded_routes": [],
    }


def _category_hint(*names: str) -> str | None:
    text = " ".join(names).lower()
    for needles, category in _CATEGORY_HINTS:
        if any(needle in text for needle in needles):
            return category
    return None


def _contract_version(root: Path, explicit: str | None) -> str | None:
    """The analysis-output schema version: explicit, else the pipeline's X.Y.Z."""
    if explicit is not None:
        return explicit
    state = read_layer(root, "bundle")
    if state.draft is None or not isinstance(state.draft.data, dict):
        return None
    version = resolve(state.draft.data, "/pipeline/version")
    match = _SEMVER.match(str(version)) if isinstance(version, str) else None
    return match.group(1) if match else None


def _route_entry(candidate: OutputCandidate) -> dict[str, Any] | None:
    """A provisional draft entry for one published-route candidate."""
    pattern = candidate.path_pattern
    if pattern is None or pattern.endswith(r"versions\.yml$"):
        # nf-core modules emit versions.yml for provenance; nf-core pipelines
        # collect them into pipeline_info rather than publishing each one.
        return None
    scope = candidate.likely_scope
    body = pattern.removeprefix("^")
    if body.startswith(_REFERENCE_PREFIXES):
        # A capture inside a reference directory names a genome or index,
        # not a sample: reference files belong to the whole job.
        pattern = pattern.replace("(?P<sample_id>[^/]+)", "[^/]+")
        scope = OutputScope.JOB
    elif scope is None:
        scope = OutputScope.SAMPLE if "(?P<sample_id>" in pattern else OutputScope.JOB
    entity = candidate.likely_entity_type
    entry: dict[str, Any] = {
        "key": candidate.suggested_key,
        "title": candidate.suggested_title,
        "description": candidate.suggested_description,
        "category": _category_hint(*candidate.processes, candidate.suggested_key),
        "formats": [candidate.suggested_format.value]
        if candidate.suggested_format
        else [],
        "scopes": [scope.value],
        "entity_types": [entity.value] if entity else [],
        "path_patterns": [pattern],
    }
    return entry


def seed_catalogue(
    root: Path,
    discovered: Sequence[Any],
    schema_version: str | None,
) -> tuple[dict[str, Any], dict[str, str], list[str]]:
    """Build the first ``outputs.draft.yaml`` from evidence.

    A previously published catalogue (``splice/outputs.yaml``, in 0.3.0 or an
    earlier layout) is the richest evidence: it was written by people, so it
    seeds the draft whole. Otherwise every statically published route becomes
    one provisional entry; identical patterns are one entry. Unknown values
    stay empty and are reported by validation, never invented.

    Returns the draft, the candidate ids each entry was seeded from (by key)
    and notes for the author.
    """
    draft = _empty_draft(_contract_version(root, schema_version))
    notes: list[str] = []
    seeded_from: dict[str, str] = {}
    published = published_catalogue(root)
    if published is not None and published.outputs:
        draft["outputs"] = [dict(item) for item in published.outputs]
        used = {item.get("category") for item in published.outputs}
        draft["categories"] = {
            key: value
            for key, value in sorted(published.categories.items())
            if key in used and value
        }
        notes.append(
            f"seeded {len(published.outputs)} output(s) from the published "
            f"{published.location} ({published.format} layout)"
        )
        notes.extend(published.notes)
        return draft, seeded_from, notes
    keys: set[str] = set()
    patterns: set[str] = set()
    # Route evidence names outputs after their emits; prefer it to names
    # made up from an example's file names when both describe one pattern.
    ordered = sorted(
        discovered, key=lambda item: (not item.candidate.processes, item.candidate.id)
    )
    for item in ordered:
        candidate = item.candidate
        entry = _route_entry(candidate)
        if entry is None or entry["path_patterns"][0] in patterns:
            continue
        patterns.add(entry["path_patterns"][0])
        key = entry["key"]
        if key in keys and candidate.processes:
            key = re.sub(
                r"[^a-z0-9_]+", "_", f"{candidate.processes[0]}_{key}".lower()
            ).strip("_")
        base, number = key, 2
        while key in keys:
            key, number = f"{base}_{number}", number + 1
        keys.add(key)
        entry["key"] = key
        draft["outputs"].append(entry)
        seeded_from[key] = candidate.id
    if draft["outputs"]:
        notes.append(
            f"seeded {len(draft['outputs'])} provisional output(s) from published "
            "routes; descriptions, categories and scopes are first guesses"
        )
    else:
        notes.append("no published output route was found; the catalogue is empty")
    return draft, seeded_from, notes


@dataclass(frozen=True, slots=True)
class OutputDiscovery:
    """Result of seeding the draft and refreshing the advisory candidates."""

    created_draft: bool
    pending: tuple[OutputCandidate, ...]
    new_candidates: tuple[str, ...]
    notes: tuple[str, ...] = ()


def discover_outputs(
    repository_root: str | Path,
    *,
    example_output_tree: str | Path | None = None,
    publish_directory: str | Path | None = None,
    schema_version: str | None = None,
) -> OutputDiscovery:
    """Seed a populated draft if absent; refresh advisory candidates.

    The first run writes a useful catalogue into ``outputs.draft.yaml``.
    Later runs never touch the draft: new evidence only updates the advisory
    candidates in the sidecar, which never block validation. Candidate IDs
    are stable hashes of key and pattern.
    """
    root = Path(repository_root).resolve()
    discovered = discover_output_candidates(
        root,
        example_output_tree=example_output_tree,
        publish_directory=publish_directory,
    )
    seed, seeded_from, notes = seed_catalogue(root, discovered, schema_version)
    created = seed_draft(
        root,
        LAYER,
        seed,
        header=(
            "nf-SPLICE output catalogue draft (authoritative, editable).",
            "Seeded from published routes or the published catalogue: rewrite "
            "anything,",
            "add outputs discovery missed, or list deliberate omissions in "
            "excluded_routes.",
        ),
    )
    if not created:
        notes = []
    added: list[str] = []
    seeded_ids = set(seeded_from.values()) if created else set()

    def merge(state: ReviewState) -> None:
        for item in discovered:
            candidate = item.candidate.model_dump(mode="json")
            evidence = [entry.model_dump(mode="json") for entry in item.evidence]
            existing = state.candidates.get(item.candidate.id)
            if existing is None:
                added.append(item.candidate.id)
                state.candidates[item.candidate.id] = {
                    "status": SEEDED if item.candidate.id in seeded_ids else PENDING,
                    "candidate": candidate,
                    "evidence": evidence,
                }
            else:
                if existing.get("status") == PENDING:
                    existing["candidate"] = candidate
                known = {
                    json.dumps(entry, sort_keys=True)
                    for entry in existing.get("evidence", [])
                }
                existing["evidence"] = existing.get("evidence", []) + [
                    entry
                    for entry in evidence
                    if json.dumps(entry, sort_keys=True) not in known
                ]

    update_review_state(root, LAYER, merge)
    return OutputDiscovery(
        created, pending_candidates(root), tuple(sorted(added)), tuple(notes)
    )


def pending_candidates(repository_root: str | Path) -> tuple[OutputCandidate, ...]:
    """Advisory candidates nobody has acted on (never a validation gate)."""
    state = load_review_state(Path(repository_root).resolve(), LAYER)
    return tuple(
        OutputCandidate.model_validate(entry["candidate"])
        for _, entry in sorted(state.candidates.items())
        if entry.get("status") == PENDING
    )


def all_candidates(repository_root: str | Path) -> tuple[OutputCandidate, ...]:
    """Every advisory candidate discovery recorded, whatever its status."""
    state = load_review_state(Path(repository_root).resolve(), LAYER)
    return tuple(
        OutputCandidate.model_validate(entry["candidate"])
        for _, entry in sorted(state.candidates.items())
        if isinstance(entry, dict) and isinstance(entry.get("candidate"), dict)
    )


def candidate_evidence(
    repository_root: str | Path, candidate_id: str
) -> tuple[dict[str, Any], ...]:
    """Return the evidence recorded for one candidate."""
    state = load_review_state(Path(repository_root).resolve(), LAYER)
    entry = state.candidates.get(candidate_id)
    if entry is None:
        raise LayerError(f"unknown output candidate {candidate_id!r}")
    return tuple(entry.get("evidence", []))


def _draft(root: Path) -> dict[str, Any]:
    state = read_layer(root, LAYER)
    if state.draft is None or not isinstance(state.draft.data, dict):
        raise LayerError(
            f"outputs.draft.yaml is missing or malformed: {state.error or 'absent'}"
        )
    data: dict[str, Any] = state.draft.data
    return data


def _require_candidate(state: ReviewState, candidate_id: str) -> dict[str, Any]:
    entry = state.candidates.get(candidate_id)
    if not isinstance(entry, dict):
        raise LayerError(f"unknown output candidate {candidate_id!r}")
    return entry


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


def accept_output(
    repository_root: str | Path,
    candidate_id: str,
    output: ReviewedOutput | Mapping[str, Any],
    context: ChangeContext,
) -> EditResult:
    """Add one complete reviewed output to the draft for a candidate."""
    root = Path(repository_root).resolve()
    reviewed = _reviewed(output)
    _require_candidate(load_review_state(root, LAYER), candidate_id)

    def mark(state: ReviewState) -> None:
        entry = _require_candidate(state, candidate_id)
        entry.update({"status": ACCEPTED, "output_keys": [reviewed.key]})

    return edit_draft(
        root,
        LAYER,
        _append_ops(_draft(root), [reviewed]),
        context,
        action="accept_output",
        review=mark,
    )


def reject_output(
    repository_root: str | Path,
    candidate_id: str,
    reason: str,
    context: ChangeContext,
) -> None:
    """Reject a candidate; the rejection survives rediscovery."""
    if not reason.strip():
        raise LayerError("rejecting an output candidate requires a reason")
    root = Path(repository_root).resolve()
    _require_candidate(load_review_state(root, LAYER), candidate_id)

    def mark(state: ReviewState) -> None:
        _require_candidate(state, candidate_id).update(
            {"status": REJECTED, "reason": reason.strip()}
        )

    record_decision(root, LAYER, "reject_output", context, (), mark)


def merge_outputs(
    repository_root: str | Path,
    candidate_ids: Sequence[str],
    output: ReviewedOutput | Mapping[str, Any],
    context: ChangeContext,
) -> EditResult:
    """Merge several candidates into one reviewed output."""
    if len(candidate_ids) < 2 or len(set(candidate_ids)) != len(candidate_ids):
        raise LayerError("merge requires at least two unique candidate ids")
    root = Path(repository_root).resolve()
    reviewed = _reviewed(output)
    state = load_review_state(root, LAYER)
    for item in candidate_ids:
        _require_candidate(state, item)

    def mark(review: ReviewState) -> None:
        for index, item in enumerate(candidate_ids):
            _require_candidate(review, item).update(
                {
                    "status": ACCEPTED if index == 0 else MERGED,
                    "output_keys": [reviewed.key],
                }
                | ({} if index == 0 else {"merged_into": candidate_ids[0]})
            )

    return edit_draft(
        root,
        LAYER,
        _append_ops(_draft(root), [reviewed]),
        context,
        action="merge_outputs",
        review=mark,
    )


def split_output(
    repository_root: str | Path,
    candidate_id: str,
    outputs: Sequence[ReviewedOutput | Mapping[str, Any]],
    context: ChangeContext,
) -> EditResult:
    """Replace one broad candidate with two or more narrower reviewed outputs."""
    if len(outputs) < 2:
        raise LayerError("split requires at least two reviewed outputs")
    root = Path(repository_root).resolve()
    reviewed = [_reviewed(item) for item in outputs]
    _require_candidate(load_review_state(root, LAYER), candidate_id)

    def mark(state: ReviewState) -> None:
        _require_candidate(state, candidate_id).update(
            {"status": SPLIT, "output_keys": [item.key for item in reviewed]}
        )

    return edit_draft(
        root,
        LAYER,
        _append_ops(_draft(root), reviewed),
        context,
        action="split_output",
        review=mark,
    )


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


def apply_decision_file(
    repository_root: str | Path, decisions: Mapping[str, Any], context: ChangeContext
) -> None:
    """Apply explicit accept/reject/merge/split actions (CI-reproducible)."""
    actions = decisions.get("actions")
    if not isinstance(actions, list):
        raise LayerError("decision file must contain an actions list")
    for index, action in enumerate(actions):
        if not isinstance(action, dict):
            raise LayerError(f"decision action {index} is invalid")
        kind = action.get("action")
        if kind == "accept":
            accept_output(
                repository_root,
                str(action.get("candidate_id")),
                action.get("output") or {},
                context,
            )
        elif kind == "reject":
            reject_output(
                repository_root,
                str(action.get("candidate_id")),
                str(action.get("reason", "")),
                context,
            )
        elif kind == "merge":
            merge_outputs(
                repository_root,
                [str(item) for item in action.get("candidate_ids") or []],
                action.get("output") or {},
                context,
            )
        elif kind == "split":
            split_output(
                repository_root,
                str(action.get("candidate_id")),
                list(action.get("outputs") or []),
                context,
            )
        elif kind == "version":
            set_contract_version(
                repository_root, str(action.get("schema_version")), context
            )
        else:
            raise LayerError(f"unknown output review action {kind!r}")


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


def _coverage_issues(
    root: Path,
    patterns: Sequence[str],
    exclusions: Sequence[tuple[str, str]],
) -> list[DraftIssue]:
    """Published routes no catalogue entry matches, by how firm the evidence is.

    - *Established* (confirmed from the code, with no condition, switch or
      dynamic path): an error, ``route_not_covered``. The catalogue is the
      union of what the pipeline publishes, so an established output may not
      be silently missing. Resolve it by adding or correcting an output, or
      by listing it under ``excluded_routes`` with a reason (``kind:
      false_positive`` when static discovery is wrong).
    - *Conditional* (a workflow branch, ``when:``, ``ext.when``, an
      ``enabled`` switch or a dynamic path): a warning,
      ``conditional_route_not_covered``. The union of routes still applies:
      an example run that took another branch is no reason to drop it.
    - *Unverified* (static analysis could not resolve the route): a warning,
      ``route_unverified``. Never a blocker.

    Excluded routes, ``versions.yml`` and unreachable code are not reported.
    This replaces the former candidate-review gate: what matters is what the
    catalogue covers, not whether each heuristic candidate was clicked.
    """
    try:
        analysis = analyse_routes(root)
    except (OSError, ValueError):
        return []
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
    for route in analysis.published:
        glob = route.published_glob
        if (
            glob is None
            or glob in seen
            or route.status is CoverageStatus.NOT_REACHABLE
            or glob.endswith("versions.yml")
            or glob in excluded_globs
            or route.instance in excluded_processes
            or route.process in excluded_processes
        ):
            continue
        seen.add(glob)
        examples = [example_path(glob)]
        if glob.startswith("*/"):
            examples.extend(
                example_path(f"{name}/{glob[2:]}") for name in first_directories
            )
        if any(
            expression.match(sample) for expression in compiled for sample in examples
        ):
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
    found = []
    for (kind, instance), globs in sorted(uncovered.items()):
        place = f" ({where[instance]})" if instance in where else ""
        paths = ", ".join(sorted(globs))
        if kind == ESTABLISHED:
            found.append(
                issue(
                    LAYER,
                    "/outputs",
                    "route_not_covered",
                    f"{instance} always publishes {len(globs)} path(s) no output "
                    f"pattern matches{place}: {paths}. Add or correct outputs for "
                    "them, or list them under excluded_routes with a reason (kind: "
                    "intermediate, false_positive or out_of_scope)",
                )
            )
        elif kind == CONDITIONAL:
            when = f" ({conditions[instance]})" if instance in conditions else ""
            found.append(
                issue(
                    LAYER,
                    "/outputs",
                    "conditional_route_not_covered",
                    f"{instance} publishes {len(globs)} path(s){when}{place} that no "
                    f"output pattern matches: {paths}. The catalogue is the union "
                    "of every route; add outputs for them, or exclude them with a "
                    "reason",
                    Severity.WARNING,
                )
            )
        else:
            found.append(
                issue(
                    LAYER,
                    "/outputs",
                    "route_unverified",
                    f"static analysis could not establish whether {instance} "
                    f"publishes {paths}{place}; check the code and catalogue or "
                    "exclude it if it is published",
                    Severity.WARNING,
                )
            )
    return found


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
            issue(LAYER, "/outputs", "missing_required", "review at least one output")
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
    exclusions, exclusion_issues = _exclusions(data)
    issues.extend(exclusion_issues)
    # Every pattern the author wrote counts, even on an unfinished entry.
    patterns = [
        str(pattern)
        for item in raw_outputs
        if isinstance(item, Mapping)
        for pattern in item.get("path_patterns") or []
        if isinstance(pattern, str)
    ]
    issues.extend(_coverage_issues(root, patterns, exclusions))
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
    # Advisory candidates in the sidecar never gate the catalogue (ADR-0057);
    # route coverage is checked against the catalogue's actual content.
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


def candidate_digest(candidate_id: str) -> str:
    """Short display form of a stable candidate ID."""
    return hashlib.sha256(candidate_id.encode()).hexdigest()[:8]
