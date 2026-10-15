"""One application facade shared by the CLI, the TUI and agent tools.

Every method delegates to the file-first services; interfaces never
re-implement inspection, review, validation or promotion rules
(ADR-0014). Drafts below ``.splice-local/drafts/`` are the authoring source.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from nf_splice.layers import ChangeContext, confirm_values
from nf_splice.layers import components as component_layer
from nf_splice.layers import execution as execution_layer
from nf_splice.layers import inputs as input_layer
from nf_splice.layers import outputs as output_layer
from nf_splice.layers import provenance as provenance_layer
from nf_splice.layers.base import EditResult, LayerValidation
from nf_splice.layers.bundle import set_identity_fields
from nf_splice.services import lifecycle, workspace


class ApplicationService:
    """Interface-neutral facade over the shared file-first operations."""

    # Read-only state -------------------------------------------------------

    def status(self, repository: str | Path) -> workspace.WorkspaceStatus:
        return workspace.workspace_status(repository)

    def inspect_layer(self, repository: str | Path, layer: str) -> dict[str, Any]:
        return workspace.inspect_layer(repository, layer)

    def validate_layer(self, repository: str | Path, layer: str) -> LayerValidation:
        return lifecycle.validate_layer(repository, layer)

    def plan_promotion(
        self, repository: str | Path, layer: str | None = None
    ) -> lifecycle.PromotionPlan:
        return lifecycle.plan_promotion(repository, layer)

    def validate_bundle(self, repository: str | Path) -> lifecycle.BundleReport:
        return lifecycle.validate_bundle(repository)

    # Drafts -------------------------------------------------------------

    def initialise(
        self, repository: str | Path, context: ChangeContext, **options: Any
    ) -> workspace.InitialisationReport:
        return workspace.initialise(repository, context, **options)

    def set_identity(
        self, repository: str | Path, changes: Mapping[str, Any], context: ChangeContext
    ) -> EditResult:
        return set_identity_fields(repository, changes, context)

    def confirm(
        self,
        repository: str | Path,
        layer: str,
        pointers: Sequence[str],
        context: ChangeContext,
    ) -> object:
        return confirm_values(Path(repository).resolve(), layer, pointers, context)

    def plan_patch(
        self,
        repository: str | Path,
        layer: str,
        operations: Sequence[Mapping[str, Any]],
        context: ChangeContext,
    ) -> EditResult:
        return workspace.plan_patch(repository, layer, operations, context)

    def apply_patch(
        self,
        repository: str | Path,
        layer: str,
        operations: Sequence[Mapping[str, Any]],
        context: ChangeContext,
    ) -> EditResult:
        return workspace.apply_patch(repository, layer, operations, context)

    def set_access(
        self,
        repository: str | Path,
        names: Sequence[str],
        editable_by: Sequence[str],
        context: ChangeContext,
        *,
        visibility: str | None = None,
        write: bool = True,
    ) -> EditResult:
        return input_layer.set_access(
            repository, names, editable_by, context, visibility=visibility, write=write
        )

    def discover_outputs(
        self, repository: str | Path, **options: Any
    ) -> output_layer.OutputDiscovery:
        return output_layer.discover_outputs(repository, **options)

    def accept_output(
        self,
        repository: str | Path,
        candidate_id: str,
        output: Mapping[str, Any],
        context: ChangeContext,
    ) -> EditResult:
        return output_layer.accept_output(repository, candidate_id, output, context)

    def reject_output(
        self,
        repository: str | Path,
        candidate_id: str,
        reason: str,
        context: ChangeContext,
    ) -> None:
        output_layer.reject_output(repository, candidate_id, reason, context)

    def discover_components(self, repository: str | Path) -> object:
        return component_layer.discover_components(repository)

    def discover_execution(self, repository: str | Path) -> object:
        return execution_layer.discover_execution(repository)

    def analyse_ro_crate(
        self, repository: str | Path
    ) -> provenance_layer.CrateAnalysis:
        return provenance_layer.analyse_ro_crate(repository)

    # Publication ---------------------------------------------------------

    def promote(
        self,
        repository: str | Path,
        layer: str | None,
        context: ChangeContext,
        **options: Any,
    ) -> lifecycle.PromotionResult:
        return lifecycle.promote(repository, layer, context, **options)

    def recover(self, repository: str | Path) -> lifecycle.RecoveryResult:
        return lifecycle.recover(repository)
