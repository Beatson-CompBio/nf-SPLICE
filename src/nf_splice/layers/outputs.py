"""Output layer: the single editable ``splice/drafts/outputs.draft.yaml``.

The draft is the only authoritative output source. Promotion compiles it,
together with the reviewed identity, into both published files:
``outputs.yaml`` (developer-readable) and ``outputs.schema.json`` (runtime
schema with the embedded ``x-output-catalog``). There is no editable JSON
output draft; JSON previews are derived and never written.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]
from pydantic import ValidationError

from nf_splice.contracts import OUTPUTS_FAMILY, validate_contract_document
from nf_splice.domain import OutputCandidate, ReviewedOutput
from nf_splice.drafts import ABSENT, PatchOp, resolve
from nf_splice.inspectors import discover_output_candidates
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


def _empty_draft(schema_version: str | None) -> dict[str, Any]:
    return {
        "contract": {"schema_version": schema_version},
        "categories": {},
        "outputs": [],
    }


@dataclass(frozen=True, slots=True)
class OutputDiscovery:
    """Result of merging discovered candidates into the review sidecar."""

    created_draft: bool
    pending: tuple[OutputCandidate, ...]
    new_candidates: tuple[str, ...]


def discover_outputs(
    repository_root: str | Path,
    *,
    example_output_tree: str | Path | None = None,
    publish_directory: str | Path | None = None,
    schema_version: str | None = None,
) -> OutputDiscovery:
    """Seed the draft if absent and merge candidates without touching reviews.

    Candidate IDs are stable hashes of key and pattern, so rediscovery never
    applies an earlier review to a different candidate.
    """
    root = Path(repository_root).resolve()
    created = seed_draft(root, LAYER, _empty_draft(schema_version))
    discovered = discover_output_candidates(
        root,
        example_output_tree=example_output_tree,
        publish_directory=publish_directory,
    )
    added: list[str] = []

    def merge(state: ReviewState) -> None:
        for item in discovered:
            candidate = item.candidate.model_dump(mode="json")
            evidence = [entry.model_dump(mode="json") for entry in item.evidence]
            existing = state.candidates.get(item.candidate.id)
            if existing is None:
                added.append(item.candidate.id)
                state.candidates[item.candidate.id] = {
                    "status": PENDING,
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
    return OutputDiscovery(created, pending_candidates(root), tuple(sorted(added)))


def pending_candidates(repository_root: str | Path) -> tuple[OutputCandidate, ...]:
    """Return candidates that still require an explicit review decision."""
    state = load_review_state(Path(repository_root).resolve(), LAYER)
    return tuple(
        OutputCandidate.model_validate(entry["candidate"])
        for _, entry in sorted(state.candidates.items())
        if entry.get("status") == PENDING
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


def _contract_input(
    root: Path, data: Mapping[str, Any]
) -> tuple[OutputContractInput | None, list[DraftIssue]]:
    issues: list[DraftIssue] = []
    unknown = sorted(set(data) - {"contract", "categories", "outputs"})
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
                    f"category metadata {label!r} is not used by any output",
                )
            )
            continue
        details = details if isinstance(details, dict) else {}
        categories[label] = CategoryDetails(
            title=details.get("title"), description=details.get("description")
        )
    pipeline, identity_issues = _pipeline(root)
    issues.extend(identity_issues)
    if issues or pipeline is None:
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
    review = load_review_state(root, LAYER)
    for candidate_id, entry in sorted(review.candidates.items()):
        if entry.get("status") == PENDING:
            issues.append(
                issue(
                    LAYER,
                    "",
                    "pending_candidate",
                    f"output candidate {candidate_id} "
                    f"({entry['candidate'].get('suggested_key')}) requires review",
                )
            )
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
