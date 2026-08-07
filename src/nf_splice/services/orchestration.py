"""Plan, build, and validate the complete reviewed SPLICE integration."""

from __future__ import annotations

import difflib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from nf_splice.domain import LayerStatus, PathClassification
from nf_splice.inspectors import inspect_repository, inspect_splice_tree
from nf_splice.renderers import (
    render_bundle,
    render_component_inventory,
    render_execution,
    render_input_projection,
    render_output_contracts,
    render_provenance,
    reviewed_execution_profiles,
)
from nf_splice.services.authoring import load_repository_document
from nf_splice.services.static_layers import StaticChangeKind


class IntegrationBuildError(ValueError):
    """Raised when complete integration generation is blocked or unsafe."""


@dataclass(frozen=True, slots=True)
class IntegrationChange:
    """One planned complete-integration file effect."""

    path: Path
    kind: StaticChangeKind
    diff: str


@dataclass(frozen=True, slots=True)
class IntegrationPlan:
    """Complete desired-state plan with explicit blockers."""

    target: str
    changes: tuple[IntegrationChange, ...]
    blockers: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not self.blockers


@dataclass(frozen=True, slots=True)
class IntegrationBuildResult:
    """Applied or checked complete-integration result."""

    plan: IntegrationPlan
    wrote: bool


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """One stable integration validation finding."""

    path: str
    rule: str
    message: str


@dataclass(frozen=True, slots=True)
class IntegrationValidationReport:
    """Validation result for canonical state and the materialised bundle."""

    valid: bool
    checked_files: int
    issues: tuple[ValidationIssue, ...]


_REQUIRED_LAYERS = (
    "inputs",
    "outputs",
    "components",
    "execution_profiles",
    "provenance",
)
_BUNDLE_PATHS = frozenset({"bundle.json", "README.md", "nf-splice.lock.json"})


def _blockers(root: Path) -> tuple[str, ...]:
    try:
        document = load_repository_document(root)
    except (OSError, ValueError) as error:
        return (str(error),)
    by_name = {item.name: item for item in document.layers}
    blockers = []
    for name in _REQUIRED_LAYERS:
        layer = by_name.get(name)
        if layer is None:
            blockers.append(f"{name}: not configured")
        elif layer.status is not LayerStatus.READY:
            blockers.append(f"{name}: {len(layer.unresolved)} unresolved decision(s)")
    for field in ("name", "version", "repository_url"):
        if getattr(document.pipeline, field) is None:
            blockers.append(f"identity: missing {field}")
    return tuple(blockers)


def _desired_files(root: Path) -> dict[str, bytes]:
    document = load_repository_document(root)
    outputs = render_output_contracts(document)
    execution = render_execution(document, root)
    files: dict[str, bytes] = {
        "inputs.schema.json": render_input_projection(document).schema.encode("utf-8"),
        "outputs.yaml": outputs.catalogue.encode("utf-8"),
        "outputs.schema.json": outputs.schema.encode("utf-8"),
        "components.json": render_component_inventory(document).inventory.encode(
            "utf-8"
        ),
        "execution-profiles.json": execution.profiles.encode("utf-8"),
        "ro-crate-metadata.json": render_provenance(document, root).metadata,
    }
    files.update(dict(execution.configs))
    authoring = root / "splice" / "nf-splice.yaml"
    source_files = {"splice/nf-splice.yaml": authoring.read_bytes()}
    source_files["ro-crate-metadata.json"] = (
        root / "ro-crate-metadata.json"
    ).read_bytes()
    for profile in reviewed_execution_profiles(document):
        source_files[str(profile.config_source)] = (
            root / profile.config_source
        ).read_bytes()
    revision = inspect_repository(root).repository_revision
    rendered_bundle = render_bundle(
        document,
        repository_revision=revision,
        generated_files=files,
        source_files=source_files,
    )
    files["bundle.json"] = rendered_bundle.bundle
    files["README.md"] = rendered_bundle.readme
    files["nf-splice.lock.json"] = rendered_bundle.lock
    return files


def _diff(relative: str, current: bytes, proposed: bytes) -> str:
    return "".join(
        difflib.unified_diff(
            current.decode("utf-8", errors="replace").splitlines(keepends=True),
            proposed.decode("utf-8", errors="replace").splitlines(keepends=True),
            fromfile=f"splice/{relative}" if current else "/dev/null",
            tofile=f"splice/{relative}",
        )
    )


def _changes(
    root: Path, desired: dict[str, bytes], target: str
) -> tuple[IntegrationChange, ...]:
    selected = (
        desired
        if target == "all"
        else {
            path: payload for path, payload in desired.items() if path in _BUNDLE_PATHS
        }
    )
    changes = []
    for relative, proposed in sorted(selected.items()):
        path = root / "splice" / relative
        if path.exists() and (path.is_symlink() or not path.is_file()):
            raise IntegrationBuildError(
                f"integration target is not a regular file: {path}"
            )
        current = path.read_bytes() if path.is_file() else b""
        kind = (
            StaticChangeKind.UNCHANGED
            if current == proposed
            else StaticChangeKind.UPDATE
            if path.exists()
            else StaticChangeKind.CREATE
        )
        changes.append(
            IntegrationChange(
                path=path,
                kind=kind,
                diff=""
                if kind is StaticChangeKind.UNCHANGED
                else _diff(relative, current, proposed),
            )
        )
    return tuple(changes)


def plan_integration(
    repository_root: str | Path, *, target: str = "all"
) -> IntegrationPlan:
    """Render a stable complete-tree plan without changing the repository."""
    if target not in {"all", "bundle"}:
        raise IntegrationBuildError(f"unsupported integration plan target {target!r}")
    root = Path(repository_root).resolve()
    blockers = _blockers(root)
    if blockers:
        return IntegrationPlan(target=target, changes=(), blockers=blockers)
    try:
        desired = _desired_files(root)
        changes = _changes(root, desired, target)
    except (OSError, UnicodeError, ValueError) as error:
        return IntegrationPlan(target=target, changes=(), blockers=(str(error),))
    return IntegrationPlan(target=target, changes=changes, blockers=())


def _preflight(
    root: Path,
    plan: IntegrationPlan,
    *,
    replace_existing: bool,
) -> None:
    if not plan.ready:
        raise IntegrationBuildError(
            "integration is blocked: " + "; ".join(plan.blockers)
        )
    splice = root / "splice"
    if splice.exists() and (splice.is_symlink() or not splice.is_dir()):
        raise IntegrationBuildError(
            f"repository-root splice path must be a regular directory: {splice}"
        )
    classifications = {
        item.path: item.classification for item in inspect_splice_tree(root).paths
    }
    for change in plan.changes:
        if change.kind is StaticChangeKind.UNCHANGED:
            continue
        relative = change.path.relative_to(splice).as_posix()
        classification = classifications.get(relative)
        if classification is PathClassification.MALFORMED:
            raise IntegrationBuildError(
                f"refusing to replace malformed recognized artefact: {change.path}"
            )
        if classification is PathClassification.UNKNOWN:
            raise IntegrationBuildError(
                f"refusing to replace unknown content: {change.path}"
            )
        if classification is PathClassification.RECOGNIZED and not replace_existing:
            raise IntegrationBuildError(
                "review the displayed integration diff, then pass --replace-existing"
            )


def _write_atomic(path: Path, payload: bytes) -> None:
    temporary = path.with_name(f".{path.name}.nf-splice.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def build_integration(
    repository_root: str | Path,
    *,
    target: str = "all",
    replace_existing: bool = False,
    check: bool = False,
) -> IntegrationBuildResult:
    """Build all reviewed files or only bundle metadata after one preflight."""
    root = Path(repository_root).resolve()
    plan = plan_integration(root, target=target)
    _preflight(root, plan, replace_existing=replace_existing)
    if check:
        return IntegrationBuildResult(plan=plan, wrote=False)
    desired = _desired_files(root)
    if target == "bundle":
        for relative, expected in desired.items():
            if relative in _BUNDLE_PATHS:
                continue
            path = root / "splice" / relative
            if not path.is_file() or path.read_bytes() != expected:
                raise IntegrationBuildError(
                    "bundle metadata requires current reviewed layer artefacts; "
                    "run `nf-splice build all`"
                )
    changed = [
        item for item in plan.changes if item.kind is not StaticChangeKind.UNCHANGED
    ]
    if not changed:
        return IntegrationBuildResult(plan=plan, wrote=False)
    for change in changed:
        relative = change.path.relative_to(root / "splice").as_posix()
        change.path.parent.mkdir(parents=True, exist_ok=True)
        _write_atomic(change.path, desired[relative])
    return IntegrationBuildResult(plan=plan, wrote=True)


def validate_integration(
    repository_root: str | Path,
) -> IntegrationValidationReport:
    """Validate canonical readiness, cross-file content, sources, and hashes."""
    root = Path(repository_root).resolve()
    blockers = _blockers(root)
    issues = [
        ValidationIssue(path="splice/nf-splice.yaml", rule="blocked", message=item)
        for item in blockers
    ]
    if blockers:
        return IntegrationValidationReport(
            valid=False, checked_files=0, issues=tuple(issues)
        )
    try:
        desired = _desired_files(root)
    except (OSError, UnicodeError, ValueError) as error:
        return IntegrationValidationReport(
            valid=False,
            checked_files=0,
            issues=(ValidationIssue(path="splice", rule="render", message=str(error)),),
        )
    for relative, expected in sorted(desired.items()):
        path = root / "splice" / relative
        if path.is_symlink() or not path.is_file():
            issues.append(
                ValidationIssue(
                    path=f"splice/{relative}",
                    rule="missing",
                    message="managed file is missing or not regular",
                )
            )
        elif path.read_bytes() != expected:
            issues.append(
                ValidationIssue(
                    path=f"splice/{relative}",
                    rule="drift",
                    message="managed file differs from reviewed deterministic content",
                )
            )
    lock_path = root / "splice" / "nf-splice.lock.json"
    if lock_path.is_file():
        try:
            lock: object = json.loads(lock_path.read_text(encoding="utf-8"))
        except (UnicodeError, json.JSONDecodeError) as error:
            issues.append(
                ValidationIssue(
                    path="splice/nf-splice.lock.json",
                    rule="json",
                    message=str(error),
                )
            )
        else:
            if isinstance(lock, dict) and "nf-splice.lock.json" in lock.get(
                "managed_files", {}
            ):
                issues.append(
                    ValidationIssue(
                        path="splice/nf-splice.lock.json",
                        rule="self_hash",
                        message="lock file must not hash itself",
                    )
                )
    return IntegrationValidationReport(
        valid=not issues,
        checked_files=len(desired),
        issues=tuple(issues),
    )


def plan_document(plan: IntegrationPlan) -> dict[str, object]:
    """Return the stable machine-readable plan representation used by the CLI."""
    return {
        "target": plan.target,
        "ready": plan.ready,
        "blockers": list(plan.blockers),
        "changes": [
            {
                "path": item.path.name
                if item.path.parent.name == "splice"
                else item.path.as_posix().split("/splice/", 1)[-1],
                "kind": item.kind.value,
                "diff": item.diff,
            }
            for item in plan.changes
        ],
    }
