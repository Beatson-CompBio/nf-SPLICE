"""File-first draft lifecycle: status, promotion, publication and validation.

Readiness always derives from current draft bytes. A single layer may be
promoted to its final file names while others remain drafts; the whole
bundle (``bundle.json``, ``README.md`` and the lock) is published only when
every layer is ready, through a staged, journalled, rollback-safe transaction
that writes ``nf-splice.lock.json`` and ``bundle.json`` last.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from nf_splice.contracts import families, release, validate_contract_document
from nf_splice.domain import PathClassification
from nf_splice.domain.identity import PipelineMetadata
from nf_splice.drafts import DRAFT_MARKER, sha256, text_diff
from nf_splice.inspectors.splice_tree import inspect_splice_tree
from nf_splice.layers.base import (
    LAYERS,
    ChangeContext,
    DraftIssue,
    LayerError,
    LayerValidation,
    ReviewState,
    Severity,
    layer_spec,
    load_review_state,
    read_layer,
    record_decision,
)
from nf_splice.layers.bundle import validate_bundle_draft
from nf_splice.layers.components import validate_components_draft
from nf_splice.layers.execution import validate_execution_draft
from nf_splice.layers.inputs import SOURCE as INPUT_SOURCE
from nf_splice.layers.inputs import validate_inputs_draft
from nf_splice.layers.outputs import validate_outputs_draft
from nf_splice.layers.provenance import validate_provenance_draft
from nf_splice.renderers.bundle_index import BUNDLE_FILES, render_bundle_index

SPLICE = "splice"
JOURNAL = ".nf-splice-publish.json"
STAGING = ".nf-splice-staging"
BACKUP = ".nf-splice-backup"
WHOLE_BUNDLE_FILES = ("bundle.json", "README.md", "nf-splice.lock.json")
FORBIDDEN_FINALS = ("outputs.json", "outputs.schema.draft.json", "nf-splice.yaml")

#: Indirection used by failure-injection tests.
replace_file: Callable[[Path, Path], None] = os.replace

_VALIDATORS: dict[str, Callable[[Path], LayerValidation]] = {
    "inputs": validate_inputs_draft,
    "outputs": validate_outputs_draft,
    "components": validate_components_draft,
    "execution-profiles": validate_execution_draft,
    "provenance": validate_provenance_draft,
}


class LifecycleError(ValueError):
    """Raised when a promotion or publication is blocked or unsafe."""


def validate_layer(repository_root: str | Path, layer: str) -> LayerValidation:
    """Validate one layer (read-only)."""
    root = Path(repository_root).resolve()
    name = layer_spec(layer).name
    if name == "bundle":
        validation = validate_bundle_draft(root)
        return LayerValidation(
            "bundle",
            validation.issues,
            {"bundle.json": b""} if validation.ready else {},
        )
    return _VALIDATORS[name](root)


class FinalState(str, Enum):
    """Relationship between a final file and its current draft compilation."""

    ABSENT = "absent"
    CURRENT = "current"
    OUTDATED = "outdated"
    DRIFTED = "drifted"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class FinalStatus:
    """One published file's state."""

    path: str
    state: FinalState


class ArtifactState(str, Enum):
    """Derived readiness of one draft layer."""

    MISSING = "missing"
    MALFORMED = "malformed"
    INCOMPLETE = "incomplete"
    READY = "ready"


@dataclass(frozen=True, slots=True)
class ArtifactStatus:
    """Status of one layer derived from its draft bytes and final files."""

    layer: str
    draft: str
    draft_sha256: str | None
    state: ArtifactState
    errors: int
    warnings: int
    finals: tuple[FinalStatus, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "layer": self.layer,
            "draft": self.draft,
            "draft_sha256": self.draft_sha256,
            "state": self.state.value,
            "errors": self.errors,
            "warnings": self.warnings,
            "finals": [
                {"path": item.path, "state": item.state.value} for item in self.finals
            ],
        }


def _final(root: Path, relative: str) -> Path:
    return root / SPLICE / relative


def _recorded_hash(root: Path, layer: str, relative: str) -> str | None:
    promoted = load_review_state(root, layer).promoted.get(relative)
    if isinstance(promoted, str):
        return promoted
    lock = _final(root, "nf-splice.lock.json")
    if lock.is_file():
        try:
            loaded = json.loads(lock.read_text(encoding="utf-8"))
            record = loaded.get("managed_files", {}).get(relative, {})
            value = record.get("sha256") if isinstance(record, dict) else None
            return value if isinstance(value, str) else None
        except (OSError, UnicodeError, json.JSONDecodeError, AttributeError):
            return None
    return None


def _final_state(
    root: Path, layer: str, relative: str, desired: bytes | None
) -> FinalState:
    path = _final(root, relative)
    if not path.exists() and not path.is_symlink():
        return FinalState.ABSENT
    if path.is_symlink() or not path.is_file():
        return FinalState.UNKNOWN
    current = sha256(path.read_bytes())
    recorded = _recorded_hash(root, layer, relative)
    if desired is not None and current == sha256(desired):
        return FinalState.CURRENT
    if recorded is not None and current != recorded:
        return FinalState.DRIFTED
    if recorded is None:
        classification = {
            item.path: item.classification for item in inspect_splice_tree(root).paths
        }.get(relative)
        if classification is PathClassification.RECOGNIZED:
            return FinalState.OUTDATED
        return FinalState.UNKNOWN
    return FinalState.OUTDATED


def _layer_finals(spec_name: str, validation: LayerValidation, root: Path) -> list[str]:
    if spec_name == "execution-profiles":
        existing = sorted(
            f"configs/{item.name}"
            for item in (root / SPLICE / "configs").glob("*.config")
            if item.is_file()
        )
        return sorted({"execution-profiles.json", *validation.files, *existing})
    return list(layer_spec(spec_name).finals)


def list_artifacts(repository_root: str | Path) -> tuple[ArtifactStatus, ...]:
    """Return every layer's derived status (read-only)."""
    root = Path(repository_root).resolve()
    statuses = []
    for spec in LAYERS:
        state = read_layer(root, spec.name)
        validation = validate_layer(root, spec.name)
        if not state.file.exists:
            derived = ArtifactState.MISSING
        elif state.draft is None:
            derived = ArtifactState.MALFORMED
        elif validation.errors:
            derived = ArtifactState.INCOMPLETE
        else:
            derived = ArtifactState.READY
        finals = tuple(
            FinalStatus(
                relative,
                _final_state(
                    root,
                    spec.name,
                    relative,
                    validation.files.get(relative) if spec.name != "bundle" else None,
                ),
            )
            for relative in _layer_finals(spec.name, validation, root)
        )
        statuses.append(
            ArtifactStatus(
                spec.name,
                spec.draft,
                state.file.sha256,
                derived,
                len(validation.errors),
                len(validation.issues) - len(validation.errors),
                finals,
            )
        )
    return tuple(statuses)


@dataclass(frozen=True, slots=True)
class FileChange:
    """One planned final-file write."""

    path: str
    kind: str
    diff: str
    state: FinalState


@dataclass(frozen=True, slots=True)
class PromotionPlan:
    """Read-only plan for promoting one layer or publishing the bundle."""

    target: str
    changes: tuple[FileChange, ...]
    blockers: tuple[DraftIssue, ...]
    payloads: Mapping[str, bytes] = field(default_factory=dict, repr=False)

    @property
    def ready(self) -> bool:
        return not self.blockers

    def to_json(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "ready": self.ready,
            "blockers": [item.to_json() for item in self.blockers],
            "changes": [
                {
                    "path": item.path,
                    "kind": item.kind,
                    "state": item.state.value,
                    "diff": item.diff,
                }
                for item in self.changes
            ],
        }


def _changes(
    root: Path, layer_of: Mapping[str, str], payloads: Mapping[str, bytes]
) -> tuple[FileChange, ...]:
    changes = []
    for relative in sorted(payloads):
        desired = payloads[relative]
        path = _final(root, relative)
        current = path.read_bytes() if path.is_file() and not path.is_symlink() else b""
        state = _final_state(root, layer_of[relative], relative, desired)
        kind = (
            "unchanged"
            if path.is_file() and current == desired
            else "update"
            if path.exists() or path.is_symlink()
            else "create"
        )
        diff = (
            ""
            if kind == "unchanged"
            else text_diff(
                f"splice/{relative}",
                current.decode("utf-8", errors="replace"),
                desired.decode("utf-8", errors="replace"),
            )
        )
        changes.append(FileChange(relative, kind, diff, state))
    return tuple(changes)


def _sources(root: Path) -> dict[str, dict[str, str]]:
    sources: dict[str, dict[str, str]] = {}
    schema = root / INPUT_SOURCE
    if schema.is_file():
        sources[INPUT_SOURCE] = {
            "sha256": sha256(schema.read_bytes()),
            "role": "input-schema-evidence",
        }
    crate = root / "ro-crate-metadata.json"
    provenance = read_layer(root, "provenance")
    strategy = None
    if provenance.draft is not None and isinstance(provenance.draft.data, dict):
        strategy = provenance.draft.data.get("strategy")
    if crate.is_file() and strategy in {"include", "enriched"}:
        sources["ro-crate-metadata.json"] = {
            "sha256": sha256(crate.read_bytes()),
            "role": f"ro-crate-source:{strategy}",
        }
    execution = read_layer(root, "execution-profiles")
    if execution.draft is not None and isinstance(execution.draft.data, dict):
        for profile in execution.draft.data.get("profiles") or []:
            config = (profile or {}).get("config") or {}
            if (
                config.get("strategy") == "adopted"
                and (root / str(config.get("source"))).is_file()
            ):
                sources[str(config["source"])] = {
                    "sha256": sha256((root / str(config["source"])).read_bytes()),
                    "role": "adopted-config",
                }
    return sources


def _revision(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ("git", "-C", str(root), "rev-parse", "HEAD"),
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = result.stdout.strip()
    return value if result.returncode == 0 and value else None


def _whole_bundle(
    root: Path,
) -> tuple[dict[str, bytes], dict[str, str], list[DraftIssue]]:
    payloads: dict[str, bytes] = {}
    layer_of: dict[str, str] = {}
    blockers: list[DraftIssue] = []
    identity = validate_bundle_draft(root)
    blockers.extend(item for item in identity.issues if item.severity is Severity.ERROR)
    for name, validator in _VALIDATORS.items():
        validation = validator(root)
        blockers.extend(validation.errors)
        for relative, payload in validation.files.items():
            payloads[relative] = payload
            layer_of[relative] = name
    if blockers or identity.metadata is None:
        return payloads, layer_of, blockers
    profiles = json.loads(payloads["execution-profiles.json"])
    provenance = read_layer(root, "provenance")
    strategy = (
        provenance.draft.data.get("strategy")
        if provenance.draft is not None and isinstance(provenance.draft.data, dict)
        else None
    )
    crate_source = _sources(root).get("ro-crate-metadata.json")
    rendered = render_bundle_index(
        identity.metadata,
        identity.maintainers,
        profiles.get("default_profile"),
        generated_files=payloads,
        sources=_sources(root),
        provenance={
            "ro_crate_strategy": strategy,
            "ro_crate_source_sha256": crate_source["sha256"] if crate_source else None,
            "ro_crate_sha256": sha256(payloads["ro-crate-metadata.json"]),
        },
        repository_revision=_revision(root),
    )
    payloads["bundle.json"] = rendered.bundle
    payloads["README.md"] = rendered.readme
    payloads["nf-splice.lock.json"] = _stable_lock(root, rendered.lock)
    for relative in WHOLE_BUNDLE_FILES:
        layer_of[relative] = "bundle"
    return payloads, layer_of, blockers


def _stable_lock(root: Path, proposed: bytes) -> bytes:
    """Keep the existing lock when only the informational revision differs."""
    path = _final(root, "nf-splice.lock.json")
    if not path.is_file():
        return proposed
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return proposed
    desired = json.loads(proposed)
    if isinstance(existing, dict):
        comparable = dict(existing)
        comparable["repository"] = desired["repository"]
        if comparable == desired:
            return path.read_bytes()
    return proposed


def plan_promotion(
    repository_root: str | Path, layer: str | None = None
) -> PromotionPlan:
    """Plan promoting one layer, or publishing the whole bundle (read-only)."""
    root = Path(repository_root).resolve()
    _require_no_journal(root)
    if layer is None or layer_spec(layer).name == "bundle":
        payloads, layer_of, blockers = _whole_bundle(root)
        target = "bundle"
    else:
        name = layer_spec(layer).name
        validation = _VALIDATORS[name](root)
        payloads = dict(validation.files)
        layer_of = dict.fromkeys(payloads, name)
        blockers = list(validation.errors)
        target = name
    if blockers:
        return PromotionPlan(target, (), tuple(blockers))
    return PromotionPlan(target, _changes(root, layer_of, payloads), (), payloads)


def _require_no_journal(root: Path) -> None:
    if _final(root, JOURNAL).exists():
        raise LifecycleError(
            "an interrupted publication was detected; run `nf-splice draft recover`"
        )


def _check_targets(
    root: Path,
    plan: PromotionPlan,
    *,
    replace_existing: bool,
    overwrite_edited: Sequence[str],
) -> None:
    # Accept paths as error messages print them (splice/<file>) or bare.
    allowed = {item.removeprefix(f"{SPLICE}/") for item in overwrite_edited}
    splice = root / SPLICE
    if splice.exists() and (splice.is_symlink() or not splice.is_dir()):
        raise LifecycleError("repository-root splice path must be a regular directory")
    for change in plan.changes:
        if change.kind == "unchanged":
            continue
        path = _final(root, change.path)
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise LifecycleError(f"refusing to replace non-regular {path}")
        if change.state is FinalState.UNKNOWN and path.exists():
            raise LifecycleError(
                f"refusing to replace unrecognised content at splice/{change.path}"
            )
        if change.state is FinalState.DRIFTED and change.path not in allowed:
            raise LifecycleError(
                f"splice/{change.path} was edited after it was published; reconcile "
                "the edit into the draft or pass --overwrite-edited explicitly"
            )
        if change.kind == "update" and not replace_existing:
            raise LifecycleError(
                "review the displayed diff, then pass --replace-existing to update "
                "published files"
            )


@dataclass(frozen=True, slots=True)
class PromotionResult:
    """Outcome of an applied promotion or publication."""

    plan: PromotionPlan
    wrote: tuple[str, ...]


def _write_transaction(root: Path, writes: Mapping[str, bytes]) -> None:
    """Stage, back up and atomically replace files; roll back on failure."""
    splice = root / SPLICE
    splice.mkdir(exist_ok=True)
    token = secrets.token_hex(6)
    staging = splice / STAGING / token
    backup = splice / BACKUP / token
    journal = _final(root, JOURNAL)
    order = sorted(
        writes,
        key=lambda item: (
            item == "bundle.json",
            item == "nf-splice.lock.json",
            item,
        ),
    )
    staging.mkdir(parents=True)
    backup.mkdir(parents=True)
    replaced: list[str] = []
    try:
        for relative in order:
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as handle:
                handle.write(writes[relative])
                handle.flush()
                os.fsync(handle.fileno())
            if sha256(target.read_bytes()) != sha256(writes[relative]):
                raise LifecycleError(f"staged copy of {relative} failed verification")
        existing = [item for item in order if _final(root, item).is_file()]
        for relative in existing:
            (backup / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(_final(root, relative), backup / relative)
        journal.write_text(
            json.dumps(
                {"token": token, "files": order, "existing": existing}, indent=2
            ),
            encoding="utf-8",
        )
        for relative in order:
            final = _final(root, relative)
            final.parent.mkdir(parents=True, exist_ok=True)
            replace_file(staging / relative, final)
            replaced.append(relative)
    except BaseException:
        _restore(
            root,
            token,
            replaced,
            existing_names=set(item for item in order if (backup / item).is_file()),
        )
        raise
    else:
        journal.unlink(missing_ok=True)
        _cleanup(splice, token)


def _restore(
    root: Path, token: str, replaced: Sequence[str], *, existing_names: set[str]
) -> None:
    splice = root / SPLICE
    backup = splice / BACKUP / token
    for relative in replaced:
        final = _final(root, relative)
        if relative in existing_names:
            os.replace(backup / relative, final)
        else:
            final.unlink(missing_ok=True)
    _final(root, JOURNAL).unlink(missing_ok=True)
    _cleanup(splice, token)


def _cleanup(splice: Path, token: str) -> None:
    for name in (STAGING, BACKUP):
        shutil.rmtree(splice / name / token, ignore_errors=True)
        parent = splice / name
        if parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()


@dataclass(frozen=True, slots=True)
class RecoveryResult:
    """Outcome of recovering an interrupted publication."""

    recovered: bool
    restored: tuple[str, ...]


def recover(repository_root: str | Path) -> RecoveryResult:
    """Restore the previous coherent release after an interrupted publication."""
    root = Path(repository_root).resolve()
    journal_path = _final(root, JOURNAL)
    if not journal_path.is_file():
        return RecoveryResult(False, ())
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    token = str(journal["token"])
    backup = root / SPLICE / BACKUP / token
    restored = []
    for relative in journal["files"]:
        final = _final(root, relative)
        if relative in journal["existing"] and (backup / relative).is_file():
            os.replace(backup / relative, final)
            restored.append(relative)
        elif relative not in journal["existing"]:
            final.unlink(missing_ok=True)
            restored.append(relative)
    journal_path.unlink()
    _cleanup(root / SPLICE, token)
    return RecoveryResult(True, tuple(restored))


def _record_promoted(
    root: Path,
    written: Mapping[str, bytes],
    layer_of: Mapping[str, str],
    context: ChangeContext,
) -> None:
    by_layer: dict[str, dict[str, str]] = {}
    for relative, payload in written.items():
        by_layer.setdefault(layer_of[relative], {})[relative] = sha256(payload)
    for layer, hashes in sorted(by_layer.items()):

        def mutate(state: ReviewState, hashes: dict[str, str] = hashes) -> None:
            state.promoted.update(hashes)

        record_decision(root, layer, "promote", context, tuple(sorted(hashes)), mutate)


def promote(
    repository_root: str | Path,
    layer: str | None,
    context: ChangeContext,
    *,
    replace_existing: bool = False,
    overwrite_edited: Sequence[str] = (),
) -> PromotionResult:
    """Promote one ready layer, or publish the whole ready bundle."""
    root = Path(repository_root).resolve()
    if not context.approved:
        raise LifecycleError("promotion requires explicit approval")
    plan = plan_promotion(root, layer)
    if not plan.ready:
        raise LifecycleError(
            "blocked: "
            + "; ".join(
                f"{item.layer}{item.pointer}: {item.message}" for item in plan.blockers
            )
        )
    _check_targets(
        root, plan, replace_existing=replace_existing, overwrite_edited=overwrite_edited
    )
    writes = {
        item.path: plan.payloads[item.path]
        for item in plan.changes
        if item.kind != "unchanged"
    }
    if writes:
        _write_transaction(root, writes)
    layer_of = (
        {path: _layer_for_final(path) for path in plan.payloads}
        if plan.target == "bundle"
        else dict.fromkeys(plan.payloads, plan.target)
    )
    if writes or any(
        _recorded_hash(root, layer_of[path], path) != sha256(payload)
        for path, payload in plan.payloads.items()
    ):
        _record_promoted(root, plan.payloads, layer_of, context)
    return PromotionResult(plan, tuple(sorted(writes)))


def _layer_for_final(relative: str) -> str:
    if relative in WHOLE_BUNDLE_FILES:
        return "bundle"
    if relative.startswith("configs/"):
        return "execution-profiles"
    for spec in LAYERS:
        if relative in spec.finals:
            return spec.name
    raise LayerError(f"no layer owns {relative}")


@dataclass(frozen=True, slots=True)
class BundleIssue:
    """One whole-bundle validation finding."""

    path: str
    rule: str
    message: str
    severity: Severity = Severity.ERROR

    def to_json(self) -> dict[str, str]:
        return {
            "path": self.path,
            "rule": self.rule,
            "message": self.message,
            "severity": self.severity.value,
        }


@dataclass(frozen=True, slots=True)
class BundleReport:
    """Whole-bundle ingestion readiness."""

    issues: tuple[BundleIssue, ...]
    checked_files: int

    @property
    def valid(self) -> bool:
        return not any(item.severity is Severity.ERROR for item in self.issues)


def _load_json(path: Path, issues: list[BundleIssue], relative: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        issues.append(BundleIssue(relative, "json", str(error)))
        return None


def validate_bundle(repository_root: str | Path) -> BundleReport:
    """Validate published files, cross-file identity and the lock (read-only)."""
    root = Path(repository_root).resolve()
    splice = root / SPLICE
    issues: list[BundleIssue] = []
    if _final(root, JOURNAL).exists():
        issues.append(
            BundleIssue(JOURNAL, "interrupted", "run nf-splice draft recover")
        )
    bundle_path = splice / "bundle.json"
    if not bundle_path.is_file():
        return BundleReport(
            (BundleIssue("splice/bundle.json", "missing", "bundle is not published"),),
            0,
        )
    bundle = _load_json(bundle_path, issues, "splice/bundle.json")
    if not isinstance(bundle, dict):
        return BundleReport(tuple(issues), 0)
    if bundle.get("schema_version") == "1.0":
        return BundleReport(
            (
                BundleIssue(
                    "splice/bundle.json",
                    "legacy_bundle",
                    "bundle schema 1.0 from nf-splice 0.1.0; run "
                    "`nf-splice migrate drafts`",
                ),
            ),
            0,
        )
    report = validate_contract_document(bundle, filename="bundle.json")
    issues.extend(
        BundleIssue(
            "splice/bundle.json",
            "contract",
            f"{item.json_pointer or '/'}: {item.message}",
        )
        for item in report.issues
    )
    expected_schemas = {
        item.id: {"version": dict(release().contracts)[item.id], "path": item.path}
        for item in families()
    }
    if bundle.get("schemas") != expected_schemas:
        issues.append(
            BundleIssue(
                "splice/bundle.json", "schemas", "schemas map differs from registry"
            )
        )
    pipeline = bundle.get("pipeline") or {}
    reference = {key: pipeline.get(key) for key in ("id", "name", "version", "engine")}
    checked = 1
    files = bundle.get("files") or {}
    if files != BUNDLE_FILES:
        issues.append(
            BundleIssue("splice/bundle.json", "files", "unexpected bundle file index")
        )
    for name in FORBIDDEN_FINALS:
        if (splice / name).exists():
            severity = Severity.WARNING if name == "nf-splice.yaml" else Severity.ERROR
            issues.append(
                BundleIssue(
                    f"splice/{name}",
                    "forbidden_artefact",
                    f"{name} is not part of a 0.3.0 bundle",
                    severity,
                )
            )
    for item in families():
        if item.path == "bundle.json":
            continue
        path = splice / item.path
        if not path.is_file():
            issues.append(
                BundleIssue(f"splice/{item.path}", "missing", "not published")
            )
            continue
        checked += 1
        document = _load_json(path, issues, f"splice/{item.path}")
        if document is None:
            continue
        result = validate_contract_document(document, item.id)
        issues.extend(
            BundleIssue(
                f"splice/{item.path}",
                "contract",
                f"{entry.json_pointer or '/'}: {entry.message}",
            )
            for entry in result.issues
        )
        envelope = (
            document.get("x-splice-pipeline")
            if item.key == "inputs"
            else (document.get("x-output-catalog") or {}).get("pipeline")
            if item.key == "outputs"
            else document.get("pipeline")
        )
        if (
            isinstance(envelope, dict)
            and {key: envelope.get(key) for key in reference} != reference
        ):
            issues.append(
                BundleIssue(
                    f"splice/{item.path}",
                    "identity_mismatch",
                    "pipeline identity differs from bundle.json",
                )
            )
        if DRAFT_MARKER in json.dumps(document):
            issues.append(
                BundleIssue(f"splice/{item.path}", "draft_marker", "draft marker")
            )
    catalogue_path = splice / "outputs.yaml"
    schema_path = splice / "outputs.schema.json"
    if catalogue_path.is_file() and schema_path.is_file():
        try:
            catalogue = yaml.safe_load(catalogue_path.read_text(encoding="utf-8"))
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            if catalogue.get("outputs") != schema["x-output-catalog"]["output_types"]:
                issues.append(
                    BundleIssue(
                        "splice/outputs.yaml",
                        "projection",
                        "differs from x-output-catalog",
                    )
                )
        except (
            yaml.YAMLError,
            KeyError,
            AttributeError,
            json.JSONDecodeError,
        ) as error:
            issues.append(BundleIssue("splice/outputs.yaml", "projection", str(error)))
        checked += 1
    lock = (
        _load_json(splice / "nf-splice.lock.json", issues, "splice/nf-splice.lock.json")
        if (splice / "nf-splice.lock.json").is_file()
        else None
    )
    if lock is None:
        issues.append(
            BundleIssue("splice/nf-splice.lock.json", "missing", "lock is missing")
        )
    else:
        managed = lock.get("managed_files", {})
        if "nf-splice.lock.json" in managed:
            issues.append(
                BundleIssue(
                    "splice/nf-splice.lock.json", "self_hash", "lock hashes itself"
                )
            )
        for relative, record in sorted(managed.items()):
            path = splice / relative
            if not path.is_file() or path.is_symlink():
                issues.append(
                    BundleIssue(f"splice/{relative}", "missing", "managed file missing")
                )
            elif sha256(path.read_bytes()) != record.get("sha256"):
                issues.append(
                    BundleIssue(
                        f"splice/{relative}", "drift", "differs from the lock hash"
                    )
                )
        expected_managed = {*BUNDLE_FILES.values(), "bundle.json", "README.md"}
        if not expected_managed <= set(managed):
            issues.append(
                BundleIssue(
                    "splice/nf-splice.lock.json",
                    "inventory",
                    "lock inventory incomplete",
                )
            )
        for relative, record in sorted((lock.get("sources") or {}).items()):
            path = root / relative
            if path.is_file() and sha256(path.read_bytes()) != record.get("sha256"):
                issues.append(
                    BundleIssue(
                        relative,
                        "stale_source",
                        "source changed since publication",
                        Severity.WARNING,
                    )
                )
    for name, validator in _VALIDATORS.items():
        validation = validator(root)
        for relative, payload in validation.files.items():
            path = splice / relative
            if path.is_file() and path.read_bytes() != payload:
                issues.append(
                    BundleIssue(
                        f"splice/{relative}",
                        "unpromoted_draft",
                        f"{name} draft has changes not yet promoted",
                        Severity.WARNING,
                    )
                )
    return BundleReport(tuple(issues), checked)


def bundle_identity(repository_root: str | Path) -> PipelineMetadata | None:
    """Reviewed identity, when ready."""
    validation = validate_bundle_draft(repository_root)
    return validation.metadata if validation.ready else None
