"""Workflow stages and their deterministic validation gates.

A stage is complete only when its gate, computed by the same services the
CLI uses, passes. A model's statement that a stage is done is never a gate.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from nf_splice.layers.base import LAYERS
from nf_splice.services.lifecycle import plan_promotion, validate_bundle, validate_layer
from nf_splice.services.workspace import workspace_status


class Stage(str, Enum):
    """Ordered stages of an integration session."""

    DISCOVER = "discover"
    IDENTITY = "identity"
    INPUTS = "inputs"
    OUTPUTS = "outputs"
    COMPONENTS = "components"
    PROFILES = "profiles"
    PROVENANCE = "provenance"
    VALIDATE = "validate"
    BUILD = "build"
    VERIFY = "verify"
    EXPORT = "export"
    COMMIT = "commit"
    REPORT = "report"


class StageStatus(str, Enum):
    """Where a stage stands."""

    PENDING = "pending"
    READY = "ready"
    NEEDS_APPROVAL = "needs_approval"
    EXECUTING = "executing"
    VALIDATION_FAILED = "validation_failed"
    REPAIRING = "repairing"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class GateResult:
    """Outcome of a deterministic gate."""

    passed: bool
    issues: tuple[str, ...] = ()
    summary: str = ""


@dataclass(frozen=True, slots=True)
class StageSpec:
    """What a stage is for, what it depends on and how it is checked."""

    stage: Stage
    title: str
    objective: str
    layer: str | None
    depends_on: tuple[Stage, ...]
    operations: tuple[str, ...]
    deterministic: bool = False


def _layer_gate(layer: str) -> Callable[[Path], GateResult]:
    def gate(root: Path) -> GateResult:
        try:
            validation = validate_layer(root, layer)
        except ValueError as error:
            return GateResult(False, (str(error),), f"{layer}: not ready")
        issues = tuple(
            f"{item.path}#{item.pointer or '/'} [{item.code}] {item.message}"
            for item in validation.errors
        )
        return GateResult(
            validation.ready,
            issues,
            f"{layer}: ready"
            if validation.ready
            else f"{layer}: {len(issues)} error(s)",
        )

    return gate


def _discover_gate(root: Path) -> GateResult:
    status = workspace_status(root)
    missing = [
        item.draft
        for item in status.artifacts
        if item.state.value in {"missing", "malformed"}
    ]
    return GateResult(
        not missing,
        tuple(f"{item}: missing or malformed" for item in missing),
        "every draft exists" if not missing else f"{len(missing)} draft(s) missing",
    )


def _validate_gate(root: Path) -> GateResult:
    try:
        plan = plan_promotion(root)
    except ValueError as error:
        return GateResult(False, (str(error),), "cross-layer plan failed")
    issues = tuple(
        f"{item.layer}{item.pointer}: {item.message}" for item in plan.blockers
    )
    return GateResult(
        plan.ready,
        issues,
        "every layer is ready to publish"
        if plan.ready
        else f"{len(issues)} blocker(s)",
    )


def _build_gate(root: Path) -> GateResult:
    if not (root / "splice" / "bundle.json").is_file():
        return GateResult(False, ("splice/bundle.json is not published",), "not built")
    report = validate_bundle(root)
    issues = tuple(
        f"{item.path} [{item.rule}] {item.message}"
        for item in report.issues
        if item.severity.value == "error"
    )
    try:
        current = plan_promotion(root)
        stale = [
            change.path for change in current.changes if change.kind != "unchanged"
        ]
    except ValueError:
        stale = []
    if report.valid and stale:
        return GateResult(
            False,
            tuple(f"splice/{item} differs from the drafts" for item in stale),
            "published bundle is out of date",
        )
    from nf_splice.services.readiness import lifecycle

    return GateResult(
        report.valid,
        issues,
        f"published ({report.checked_files} contract files checked); "
        + lifecycle(root).headline.lower()
        if report.valid
        else "invalid",
    )


def _commit_gate(root: Path) -> GateResult:
    from nf_splice.services import gitops

    current = gitops.status(root)
    if not current.repository:
        return GateResult(False, ("not a Git repository",), "not committed")
    return GateResult(
        not current.owned,
        tuple(f"uncommitted: {item}" for item in current.owned),
        "splice/ is committed" if not current.owned else "uncommitted bundle changes",
    )


def _always(_root: Path) -> GateResult:
    return GateResult(False, (), "")


_LAYER_STAGES = {
    Stage.IDENTITY: "bundle",
    Stage.INPUTS: "inputs",
    Stage.OUTPUTS: "outputs",
    Stage.COMPONENTS: "components",
    Stage.PROFILES: "execution-profiles",
    Stage.PROVENANCE: "provenance",
}
LAYER_FOR_STAGE = dict(_LAYER_STAGES)
STAGE_FOR_LAYER = {layer: stage for stage, layer in _LAYER_STAGES.items()}

SPECS: tuple[StageSpec, ...] = (
    StageSpec(
        Stage.DISCOVER,
        "Discover",
        "Inspect the repository and create every draft, seeded with what its "
        "evidence supports.",
        None,
        (),
        ("initialise_drafts",),
    ),
    StageSpec(
        Stage.IDENTITY,
        "Identity",
        "Author the pipeline identity and descriptive metadata in "
        "bundle.draft.yaml from the evidence and what the person tells you, and "
        "declare every assay the pipeline supports, with evidence.",
        "bundle",
        (Stage.DISCOVER,),
        (
            "replace_draft",
            "set_identity",
            "patch_draft",
            "add_assay_capability",
            "remove_assay_capability",
            "reject_assay_candidate",
            "confirm_values",
        ),
    ),
    StageSpec(
        Stage.INPUTS,
        "Inputs",
        "Author the runtime input contract: keep every declared parameter and "
        "give each the least-privilege access its use justifies.",
        "inputs",
        (Stage.IDENTITY,),
        (
            "replace_draft",
            "set_parameter_access",
            "sync_identity",
            "reimport_inputs",
            "patch_draft",
            "confirm_values",
        ),
    ),
    StageSpec(
        Stage.OUTPUTS,
        "Outputs",
        "Author the output catalogue: the union of outputs the pipeline may "
        "publish across its supported routes, with their scientific meaning.",
        "outputs",
        (Stage.IDENTITY,),
        (
            "replace_draft",
            "update_output",
            "set_output_contract_version",
            "discover_outputs",
            "accept_output",
            "reject_output",
            "merge_outputs",
            "split_output",
            "patch_draft",
            "confirm_values",
        ),
    ),
    StageSpec(
        Stage.COMPONENTS,
        "Components",
        "Author the component inventory: every module, its tool and version and "
        "the real container source for each runtime; the image policy.",
        "components",
        (Stage.IDENTITY,),
        (
            "replace_draft",
            "set_image_policy",
            "discover_components",
            "accept_component",
            "accept_unambiguous_components",
            "reject_component",
            "patch_draft",
            "confirm_values",
        ),
    ),
    StageSpec(
        Stage.PROFILES,
        "Execution profiles",
        "Author the execution profiles: metadata and references in the YAML, "
        "the configuration itself in native Nextflow config files, one default.",
        "execution-profiles",
        (Stage.IDENTITY, Stage.INPUTS),
        (
            "replace_draft",
            "write_config",
            "set_default_profile",
            "discover_profiles",
            "review_profile",
            "reject_profile",
            "add_slurm_default_profile",
            "patch_draft",
            "confirm_values",
        ),
    ),
    StageSpec(
        Stage.PROVENANCE,
        "Provenance",
        "Author the pipeline's RO-Crate graph so it describes this pipeline "
        "with the reviewed identity and attribution.",
        "provenance",
        (Stage.IDENTITY,),
        ("replace_draft", "provenance_strategy", "patch_draft", "confirm_values"),
    ),
    StageSpec(
        Stage.VALIDATE,
        "Cross-layer validation",
        "Check that every layer is ready to publish together.",
        None,
        (
            Stage.IDENTITY,
            Stage.INPUTS,
            Stage.OUTPUTS,
            Stage.COMPONENTS,
            Stage.PROFILES,
            Stage.PROVENANCE,
        ),
        (),
        deterministic=True,
    ),
    StageSpec(
        Stage.BUILD,
        "Build",
        "Publish the validated drafts into splice/.",
        None,
        (Stage.VALIDATE,),
        ("build_bundle",),
    ),
    StageSpec(
        Stage.VERIFY,
        "Verify",
        "Validate the published bundle, example outputs and route coverage.",
        None,
        (),
        ("run_optional_checks",),
        deterministic=True,
    ),
    StageSpec(
        Stage.EXPORT,
        "Export",
        "Write and verify a ZIP archive of the published bundle.",
        None,
        (Stage.BUILD,),
        (),
        deterministic=True,
    ),
    StageSpec(
        Stage.COMMIT,
        "Local commit",
        "Commit the validated splice/ and .gitignore to the local branch.",
        None,
        (Stage.BUILD,),
        ("git_commit",),
    ),
    StageSpec(
        Stage.REPORT,
        "Report",
        "Write the final report.",
        None,
        (),
        (),
        deterministic=True,
    ),
)
ORDER = tuple(item.stage for item in SPECS)
#: Stages after the build that record, archive and report the result.
FINISHING = frozenset({Stage.VERIFY, Stage.EXPORT, Stage.COMMIT, Stage.REPORT})

GATES: dict[Stage, Callable[[Path], GateResult]] = {
    Stage.DISCOVER: _discover_gate,
    **{stage: _layer_gate(layer) for stage, layer in _LAYER_STAGES.items()},
    Stage.VALIDATE: _validate_gate,
    Stage.BUILD: _build_gate,
    Stage.VERIFY: _always,
    Stage.EXPORT: _always,
    Stage.COMMIT: _commit_gate,
    Stage.REPORT: _always,
}


def spec(stage: Stage | str) -> StageSpec:
    """Return the specification of a stage."""
    value = Stage(stage)
    return next(item for item in SPECS if item.stage is value)


def gate(stage: Stage | str, root: Path) -> GateResult:
    """Run a stage's deterministic gate."""
    return GATES[Stage(stage)](root)


assert {item.name for item in LAYERS} == set(LAYER_FOR_STAGE.values())
