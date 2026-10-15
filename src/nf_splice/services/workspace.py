"""File-first operations shared by every interface (CLI, TUI, agents, CI).

This module is the single application boundary over per-layer drafts,
promotion, publication and container operations. Interfaces call
these functions instead of duplicating business rules (ADR-0014).
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nf_splice.domain import EvidenceKind, RepositoryInspection
from nf_splice.drafts import PatchOp
from nf_splice.inspectors import inspect_repository
from nf_splice.layers import ChangeContext, confirm_values
from nf_splice.layers.base import (
    LAYERS,
    EditResult,
    LayerValidation,
    edit_draft,
    layer_spec,
    read_layer,
    seed_draft,
)
from nf_splice.layers.bundle import SeedResult, seed_bundle_draft, validate_bundle_draft
from nf_splice.layers.components import discover_components
from nf_splice.layers.execution import discover_execution
from nf_splice.layers.inputs import SOURCE as INPUT_SOURCE
from nf_splice.layers.inputs import import_inputs
from nf_splice.layers.outputs import discover_outputs
from nf_splice.layers.provenance import LAYER as PROVENANCE
from nf_splice.services.lifecycle import (
    JOURNAL,
    ArtifactStatus,
    list_artifacts,
    validate_layer,
)


@dataclass(frozen=True, slots=True)
class EvidenceCount:
    """Count of detected evidence for one kind."""

    kind: EvidenceKind
    count: int


@dataclass(frozen=True, slots=True)
class WorkspaceStatus:
    """Read-only status shared by CLI and TUI presentation."""

    inspection: RepositoryInspection
    evidence_counts: tuple[EvidenceCount, ...]
    artifacts: tuple[ArtifactStatus, ...]
    warnings: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return all(item.state.value == "ready" for item in self.artifacts)

    def to_json(self) -> dict[str, Any]:
        return {
            "repository": self.inspection.root,
            "revision": self.inspection.repository_revision,
            "splice_tree": self.inspection.splice_tree.state.value,
            "evidence": {item.kind.value: item.count for item in self.evidence_counts},
            "artifacts": [item.to_json() for item in self.artifacts],
            "warnings": list(self.warnings),
            "ready": self.ready,
        }


def workspace_status(repository_root: str | Path) -> WorkspaceStatus:
    """Inspect evidence and derive every layer's state from draft bytes."""
    inspection = inspect_repository(repository_root)
    root = Path(inspection.root)
    counts = tuple(
        EvidenceCount(kind, count)
        for kind, count in sorted(
            Counter(item.kind for item in inspection.evidence).items(),
            key=lambda item: item[0].value,
        )
    )
    warnings = []
    tree = inspection.splice_tree
    if tree.state.value == "absent":
        warnings.append("No repository-root splice/ integration exists yet.")
    unknown = [
        item.path for item in tree.paths if item.classification.value == "unknown"
    ]
    if unknown:
        warnings.append(f"{len(unknown)} unknown splice/ path(s) will be preserved.")
    if (root / "splice" / JOURNAL).exists():
        warnings.append(
            "An interrupted publication was found; run nf-splice draft recover."
        )
    return WorkspaceStatus(inspection, counts, list_artifacts(root), tuple(warnings))


@dataclass(frozen=True, slots=True)
class InitialisationReport:
    """Drafts created (never overwritten) by initialisation."""

    created: tuple[str, ...]
    preserved: tuple[str, ...]
    identity: SeedResult
    confirmed: tuple[str, ...]
    notes: tuple[str, ...]


def initialise(
    repository_root: str | Path,
    context: ChangeContext,
    *,
    identity: Mapping[str, Any] | None = None,
    accept_detected: bool = False,
    example_output_tree: str | Path | None = None,
    publish_directory: str | Path | None = None,
    contract_version: str | None = None,
) -> InitialisationReport:
    """Seed every applicable draft from evidence; existing drafts are kept."""
    root = Path(repository_root).resolve()
    before = {spec.name for spec in LAYERS if (root / spec.draft).exists()}
    notes: list[str] = []
    seeded = seed_bundle_draft(root, explicit=identity)
    confirmed: tuple[str, ...] = ()
    if accept_detected:
        pending = [
            item.pointer
            for item in validate_bundle_draft(root).issues
            if item.code == "unconfirmed_detected_value"
        ]
        if pending:
            confirm_values(root, "bundle", pending, context)
            confirmed = tuple(pending)
    if (root / INPUT_SOURCE).is_file():
        import_inputs(root)
    else:
        notes.append(f"{INPUT_SOURCE} not found; inputs draft not created")
    discover_outputs(
        root,
        example_output_tree=example_output_tree,
        publish_directory=publish_directory,
        schema_version=contract_version,
    )
    if (root / "modules.json").is_file():
        discover_components(root)
    else:
        notes.append("modules.json not found; components draft not created")
    if (root / "nextflow.config").is_file():
        discover_execution(root)
    else:
        notes.append("nextflow.config not found; execution-profiles draft not created")
    seed_draft(root, PROVENANCE, {"strategy": None, "source": None, "crate": None})
    after = {spec.name for spec in LAYERS if (root / spec.draft).exists()}
    return InitialisationReport(
        created=tuple(sorted(after - before)),
        preserved=tuple(sorted(before)),
        identity=seeded,
        confirmed=confirmed,
        notes=tuple(notes),
    )


def plan_patch(
    repository_root: str | Path,
    layer: str,
    operations: Sequence[Mapping[str, Any]],
    context: ChangeContext,
) -> EditResult:
    """Plan a raw JSON-pointer patch to a layer draft (no write)."""
    return edit_draft(
        Path(repository_root).resolve(),
        layer,
        [PatchOp.from_json(item) for item in operations],
        context,
        action="patch",
        write=False,
    )


def apply_patch(
    repository_root: str | Path,
    layer: str,
    operations: Sequence[Mapping[str, Any]],
    context: ChangeContext,
) -> EditResult:
    """Apply an approved raw patch with three-way conflict detection."""
    return edit_draft(
        Path(repository_root).resolve(),
        layer,
        [PatchOp.from_json(item) for item in operations],
        context,
        action="patch",
    )


def inspect_layer(repository_root: str | Path, layer: str) -> dict[str, Any]:
    """Read-only per-field issues and file facts for one layer draft."""
    root = Path(repository_root).resolve()
    spec = layer_spec(layer)
    state = read_layer(root, spec.name)
    validation: LayerValidation = validate_layer(root, spec.name)
    return {
        "layer": spec.name,
        "draft": spec.draft,
        "exists": state.file.exists,
        "sha256": state.file.sha256,
        "parse_error": str(state.error) if state.error else None,
        "ready": not validation.errors and state.draft is not None,
        "issues": [item.to_json() for item in validation.issues],
        "finals": list(spec.finals),
    }


def dumps(document: Any) -> str:
    """Stable JSON for machine-readable interface output."""
    return json.dumps(document, indent=2, ensure_ascii=False, default=str)
