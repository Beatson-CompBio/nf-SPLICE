"""Discover, review, validate, and materialise execution environments."""

from __future__ import annotations

import difflib
import os
import re
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from nf_splice.domain import (
    AuthoringDocument,
    Decision,
    DecisionStatus,
    LayerState,
    PathClassification,
    UnresolvedDecision,
)
from nf_splice.domain.execution import (
    ContainerEngine,
    ExecutionEngine,
    ExecutionExecutor,
    ExecutionProfileCandidate,
    ExecutionProfileType,
    ReviewedExecutionProfile,
)
from nf_splice.domain.inputs import InputClassification, ReviewedInput
from nf_splice.inspectors import inspect_splice_tree
from nf_splice.inspectors.profiles import (
    _ACCOUNT_LITERAL,
    _DEMO_TEST,
    _PARAM_ASSIGNMENT,
    _PERSONAL_PATH,
    _SECRET_ASSIGNMENT,
    ProfileDiscoveryError,
    discover_profiles,
)
from nf_splice.inspectors.profiles import safe_relative as _safe_relative
from nf_splice.inspectors.profiles import strip_comments as _strip_comments
from nf_splice.renderers.execution import render_execution, reviewed_execution_profiles
from nf_splice.services.authoring import (
    load_repository_document,
    save_repository_document,
)
from nf_splice.services.static_layers import StaticChangeKind, StaticLayerChange


class ExecutionProfileError(ValueError):
    """Raised when execution evidence or a requested decision is unsafe."""


@dataclass(frozen=True, slots=True)
class ExecutionBuildResult:
    """Preview or application result for the profile index and configs."""

    changes: tuple[StaticLayerChange, ...]
    wrote: bool


def _replace_layer(
    layers: tuple[LayerState, ...], replacement: LayerState
) -> tuple[LayerState, ...]:
    retained = [item for item in layers if item.name != replacement.name]
    retained.append(replacement)
    return tuple(sorted(retained, key=lambda item: item.name))


def discover_execution_profiles(repository_root: str | Path) -> AuthoringDocument:
    """Persist detected profiles as unselected candidates or explicit conflicts."""
    root = Path(repository_root).resolve()
    document = load_repository_document(root)
    evidence = {item.id: item for item in document.evidence}
    decisions = {item.id: item for item in document.decisions}
    profile_ids: set[str] = set()
    try:
        discovered = discover_profiles(root)
    except ProfileDiscoveryError as error:
        raise ExecutionProfileError(str(error)) from error
    for candidate, candidate_evidence in discovered:
        profile_ids.add(candidate.id)
        for item in candidate_evidence:
            evidence[item.id] = item
        existing = decisions.get(candidate.id)
        if existing is not None and existing.status in {
            DecisionStatus.REVIEWED,
            DecisionStatus.REJECTED,
        }:
            continue
        conflict_fields = tuple(
            field
            for field in candidate.unresolved_fields
            if field in {"executor", "container_engine"}
        )
        decisions[candidate.id] = Decision(
            id=candidate.id,
            status=(
                DecisionStatus.CONFLICT if conflict_fields else DecisionStatus.CANDIDATE
            ),
            value=candidate.model_dump(mode="json"),
            evidence_ids=tuple(item.id for item in candidate_evidence),
            reason=(
                f"conflicting or incomplete detected {', '.join(conflict_fields)}"
                if conflict_fields
                else None
            ),
        )
    unresolved = tuple(
        UnresolvedDecision(
            decision_id=decision_id,
            reason="Detected execution profiles require explicit support review",
        )
        for decision_id in sorted(profile_ids)
        if decisions[decision_id].status
        in {DecisionStatus.CANDIDATE, DecisionStatus.CONFLICT}
    )
    layer = LayerState(
        name="execution_profiles",
        configured=True,
        decision_ids=tuple(sorted(profile_ids)),
        unresolved=unresolved,
    )
    updated = AuthoringDocument(
        schema_version=document.schema_version,
        pipeline=document.pipeline,
        output_contract=document.output_contract,
        evidence=tuple(sorted(evidence.values(), key=lambda item: item.id)),
        decisions=tuple(sorted(decisions.values(), key=lambda item: item.id)),
        layers=_replace_layer(document.layers, layer),
    )
    save_repository_document(root, updated)
    return updated


def unresolved_execution_profiles(
    document: AuthoringDocument,
) -> tuple[ExecutionProfileCandidate, ...]:
    """Return detected profiles that still need selection or rejection."""
    layer = next(
        (item for item in document.layers if item.name == "execution_profiles"), None
    )
    if layer is None:
        return ()
    decisions = {item.id: item for item in document.decisions}
    candidates = []
    for decision_id in layer.decision_ids:
        decision = decisions[decision_id]
        if decision.status not in {DecisionStatus.CANDIDATE, DecisionStatus.CONFLICT}:
            continue
        try:
            candidates.append(ExecutionProfileCandidate.model_validate(decision.value))
        except ValidationError:
            continue
    return tuple(sorted(candidates, key=lambda item: item.id))


def _updated_profile_document(
    document: AuthoringDocument, replacement: Decision
) -> AuthoringDocument:
    decisions = {item.id: item for item in document.decisions}
    if replacement.id not in decisions:
        raise ExecutionProfileError(f"unknown execution profile {replacement.id!r}")
    layer = next(
        (item for item in document.layers if item.name == "execution_profiles"), None
    )
    if layer is None or replacement.id not in layer.decision_ids:
        raise ExecutionProfileError("execution profiles have not been discovered")
    decisions[replacement.id] = replacement
    updated_layer = layer.model_copy(
        update={
            "unresolved": tuple(
                item for item in layer.unresolved if item.decision_id != replacement.id
            )
        }
    )
    return AuthoringDocument(
        schema_version=document.schema_version,
        pipeline=document.pipeline,
        output_contract=document.output_contract,
        evidence=document.evidence,
        decisions=tuple(sorted(decisions.values(), key=lambda item: item.id)),
        layers=_replace_layer(document.layers, updated_layer),
    )


def review_execution_profile(
    repository_root: str | Path,
    candidate_id: str,
    *,
    profile_type: str,
    description: str,
    executor: str | None = None,
    container_engine: str | None = None,
    config_source: str | None = None,
) -> AuthoringDocument:
    """Explicitly select and resolve one supported environment."""
    root = Path(repository_root).resolve()
    document = load_repository_document(root)
    decisions = {item.id: item for item in document.decisions}
    decision = decisions.get(candidate_id)
    if decision is None:
        raise ExecutionProfileError(f"unknown execution profile {candidate_id!r}")
    try:
        candidate = ExecutionProfileCandidate.model_validate(decision.value)
    except ValidationError as error:
        raise ExecutionProfileError(str(error)) from error
    selected_executor = executor
    selected_engine = container_engine
    if selected_executor is None:
        raise ExecutionProfileError(
            f"{candidate_id} requires an explicitly selected executor"
        )
    if selected_engine is None:
        raise ExecutionProfileError(
            f"{candidate_id} requires an explicitly selected container engine"
        )
    if candidate.executors and selected_executor not in candidate.executors:
        raise ExecutionProfileError(
            f"selected executor {selected_executor!r} is not present in detected "
            "evidence"
        )
    if (
        candidate.container_engines
        and selected_engine not in candidate.container_engines
    ):
        raise ExecutionProfileError(
            f"selected container engine {selected_engine!r} is not present in "
            "detected evidence"
        )
    if config_source is None or not config_source.strip():
        raise ExecutionProfileError(
            f"{candidate_id} requires one explicitly selected source config"
        )
    safe_source = _safe_relative(root, config_source.strip())
    if (
        safe_source is None
        or not safe_source.endswith(".config")
        or safe_source.startswith("splice/")
    ):
        raise ExecutionProfileError(
            "execution config source must be a repository-local .config file "
            f"outside splice/: {config_source}"
        )
    profile_slug = (
        re.sub(r"[^a-z0-9_-]+", "-", candidate.source_profile.lower()).strip("-_")
        or "profile"
    )
    profile_token = candidate.source_profile.encode("utf-8").hex()
    profile_id = f"profile-{profile_slug}-{profile_token}"
    evidence_by_id = {item.id: item for item in document.evidence}
    locations = {
        evidence_by_id[item_id].provenance.location
        for item_id in decision.evidence_ids
        if item_id in evidence_by_id
    }
    locations.add(safe_source)
    try:
        reviewed = ReviewedExecutionProfile(
            id=profile_id,
            name=candidate.name,
            description=description,
            type=ExecutionProfileType(profile_type),
            engine=ExecutionEngine.NEXTFLOW,
            executor=ExecutionExecutor(selected_executor),
            container_engine=ContainerEngine(selected_engine),
            source_profile=candidate.source_profile,
            config_source=safe_source,
            config_path=f"configs/{profile_id}.config",
            evidence_locations=tuple(sorted(locations)),
        )
    except (ValidationError, ValueError) as error:
        raise ExecutionProfileError(str(error)) from error
    updated = _updated_profile_document(
        document,
        Decision(
            id=candidate_id,
            status=DecisionStatus.REVIEWED,
            value=reviewed.model_dump(mode="json"),
            evidence_ids=decision.evidence_ids,
        ),
    )
    save_repository_document(root, updated)
    return updated


def reject_execution_profile(
    repository_root: str | Path, candidate_id: str, reason: str
) -> AuthoringDocument:
    """Explicitly mark one detected profile as unsupported by the integration."""
    if not reason.strip():
        raise ExecutionProfileError("rejecting an execution profile requires a reason")
    root = Path(repository_root).resolve()
    document = load_repository_document(root)
    decisions = {item.id: item for item in document.decisions}
    decision = decisions.get(candidate_id)
    if decision is None:
        raise ExecutionProfileError(f"unknown execution profile {candidate_id!r}")
    updated = _updated_profile_document(
        document,
        Decision(
            id=candidate_id,
            status=DecisionStatus.REJECTED,
            value=decision.value,
            evidence_ids=decision.evidence_ids,
            reason=reason.strip(),
        ),
    )
    save_repository_document(root, updated)
    return updated


def _user_configurable_parameters(document: AuthoringDocument) -> set[str]:
    parameters = set()
    for decision in document.decisions:
        if decision.status is not DecisionStatus.REVIEWED:
            continue
        try:
            reviewed = ReviewedInput.model_validate(decision.value)
        except ValidationError:
            continue
        if reviewed.classification is InputClassification.USER_CONFIGURABLE:
            parameters.add(reviewed.name)
    return parameters


def _validate_config_safety(
    document: AuthoringDocument,
    profile: ReviewedExecutionProfile,
    source: str,
    content: str,
) -> None:
    issues: list[str] = []
    scientific = _user_configurable_parameters(document)
    cleaned = _strip_comments(content)
    for line_number, code in enumerate(cleaned.splitlines(), start=1):
        if _SECRET_ASSIGNMENT.search(code):
            issues.append(f"line {line_number}: embedded credential or secret")
        if _PERSONAL_PATH.search(code):
            issues.append(f"line {line_number}: personal absolute path")
        if _ACCOUNT_LITERAL.search(code):
            issues.append(f"line {line_number}: literal HPC account or budget")
        if profile.type is ExecutionProfileType.PRODUCTION and _DEMO_TEST.search(code):
            issues.append(f"line {line_number}: test or demonstration setting")
        for parameter in _PARAM_ASSIGNMENT.findall(code):
            if parameter in scientific:
                issues.append(
                    f"line {line_number}: scientific parameter override {parameter!r}"
                )
    if issues:
        raise ExecutionProfileError(
            f"unsafe execution config {source}: " + "; ".join(issues)
        )


def _render_checked(
    root: Path, document: AuthoringDocument
) -> tuple[tuple[Path, str | bytes], ...]:
    reviewed = reviewed_execution_profiles(document)
    for profile in reviewed:
        try:
            content = (root / profile.config_source).read_bytes().decode("utf-8")
        except UnicodeDecodeError as error:
            raise ExecutionProfileError(
                f"execution config source must be UTF-8: {profile.config_source}"
            ) from error
        _validate_config_safety(document, profile, profile.config_source, content)
    rendered = render_execution(document, root)
    files: list[tuple[Path, str | bytes]] = [
        (root / "splice" / "execution-profiles.json", rendered.profiles)
    ]
    files.extend(
        (root / "splice" / relative, content) for relative, content in rendered.configs
    )
    return tuple(files)


def _change(root: Path, path: Path, proposed: str | bytes) -> StaticLayerChange:
    proposed_bytes = proposed.encode("utf-8") if isinstance(proposed, str) else proposed
    current_bytes = path.read_bytes() if path.is_file() else b""
    kind = (
        StaticChangeKind.UNCHANGED
        if current_bytes == proposed_bytes
        else StaticChangeKind.UPDATE
        if path.exists()
        else StaticChangeKind.CREATE
    )
    relative = path.relative_to(root).as_posix()
    current = current_bytes.decode("utf-8", errors="replace")
    proposed_text = proposed_bytes.decode("utf-8", errors="replace")
    diff = (
        ""
        if kind is StaticChangeKind.UNCHANGED
        else "".join(
            difflib.unified_diff(
                current.splitlines(keepends=True),
                proposed_text.splitlines(keepends=True),
                fromfile=relative if current else "/dev/null",
                tofile=relative,
            )
        )
    )
    return StaticLayerChange(path=path, kind=kind, diff=diff)


def plan_execution_profiles(repository_root: str | Path) -> ExecutionBuildResult:
    """Preview the complete selected profile/config relationship without writes."""
    root = Path(repository_root).resolve()
    document = load_repository_document(root)
    files = _render_checked(root, document)
    return ExecutionBuildResult(
        changes=tuple(_change(root, path, content) for path, content in files),
        wrote=False,
    )


def _preflight(
    root: Path, changes: tuple[StaticLayerChange, ...], replace_existing: bool
) -> None:
    splice = root / "splice"
    configs = splice / "configs"
    for directory in (splice, configs):
        if directory.exists() and (directory.is_symlink() or not directory.is_dir()):
            raise ExecutionProfileError(
                f"execution target directory is not a regular directory: {directory}"
            )
    inspected = inspect_splice_tree(root)
    by_path = {item.path: item.classification for item in inspected.paths}
    for change in changes:
        if change.kind is StaticChangeKind.UNCHANGED:
            continue
        relative = change.path.relative_to(splice).as_posix()
        classification = by_path.get(relative)
        if classification is PathClassification.MALFORMED:
            raise ExecutionProfileError(
                f"refusing to replace malformed recognized artefact: {change.path}"
            )
        if classification is PathClassification.UNKNOWN:
            raise ExecutionProfileError(
                f"refusing to replace unknown content: {change.path}"
            )
        if classification is PathClassification.RECOGNIZED and not replace_existing:
            raise ExecutionProfileError(
                "review the displayed execution diff, then pass --replace-existing"
            )


def build_execution_profiles(
    repository_root: str | Path, *, replace_existing: bool = False
) -> ExecutionBuildResult:
    """Materialise the reviewed profile index and safe configs atomically per file."""
    root = Path(repository_root).resolve()
    document = load_repository_document(root)
    files = _render_checked(root, document)
    plan = ExecutionBuildResult(
        changes=tuple(_change(root, path, content) for path, content in files),
        wrote=False,
    )
    _preflight(root, plan.changes, replace_existing)
    changed = [
        item for item in plan.changes if item.kind is not StaticChangeKind.UNCHANGED
    ]
    if not changed:
        return plan
    (root / "splice" / "configs").mkdir(exist_ok=True)
    content_by_path = dict(files)
    for change in changed:
        temporary = change.path.with_name(f".{change.path.name}.nf-splice.tmp")
        try:
            with temporary.open("xb") as handle:
                payload = content_by_path[change.path]
                handle.write(
                    payload.encode("utf-8") if isinstance(payload, str) else payload
                )
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, change.path)
        finally:
            temporary.unlink(missing_ok=True)
    return ExecutionBuildResult(changes=plan.changes, wrote=True)
