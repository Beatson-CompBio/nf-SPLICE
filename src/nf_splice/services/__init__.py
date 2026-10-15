"""Public application-service API (file-first).

Exports resolve lazily so that low-level modules (for example
``nf_splice.services.audit``) can be imported by the layer package without
importing the facade, which itself depends on the layers.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from nf_splice.services.application import ApplicationService
    from nf_splice.services.lifecycle import (
        ArtifactState,
        ArtifactStatus,
        BundleIssue,
        BundleReport,
        FinalState,
        LifecycleError,
        PromotionPlan,
        PromotionResult,
        RecoveryResult,
        list_artifacts,
        plan_promotion,
        promote,
        recover,
        validate_bundle,
        validate_layer,
    )
    from nf_splice.services.migration import (
        MigrationError,
        MigrationNote,
        MigrationPlan,
        apply_draft_migration,
        plan_draft_migration,
    )
    from nf_splice.services.state import (
        MigrationChangeKind,
        StateMigrationChange,
        StateMigrationError,
        StateMigrationResult,
        apply_state_migration,
        plan_state_migration,
    )
    from nf_splice.services.workspace import (
        InitialisationReport,
        WorkspaceStatus,
        initialise,
        inspect_layer,
        workspace_status,
    )

_EXPORTS = {
    "ApplicationService": "nf_splice.services.application",
    "ArtifactState": "nf_splice.services.lifecycle",
    "ArtifactStatus": "nf_splice.services.lifecycle",
    "BundleIssue": "nf_splice.services.lifecycle",
    "BundleReport": "nf_splice.services.lifecycle",
    "FinalState": "nf_splice.services.lifecycle",
    "InitialisationReport": "nf_splice.services.workspace",
    "LifecycleError": "nf_splice.services.lifecycle",
    "MigrationChangeKind": "nf_splice.services.state",
    "MigrationError": "nf_splice.services.migration",
    "MigrationNote": "nf_splice.services.migration",
    "MigrationPlan": "nf_splice.services.migration",
    "PromotionPlan": "nf_splice.services.lifecycle",
    "PromotionResult": "nf_splice.services.lifecycle",
    "RecoveryResult": "nf_splice.services.lifecycle",
    "StateMigrationChange": "nf_splice.services.state",
    "StateMigrationError": "nf_splice.services.state",
    "StateMigrationResult": "nf_splice.services.state",
    "WorkspaceStatus": "nf_splice.services.workspace",
    "apply_draft_migration": "nf_splice.services.migration",
    "apply_state_migration": "nf_splice.services.state",
    "initialise": "nf_splice.services.workspace",
    "inspect_layer": "nf_splice.services.workspace",
    "list_artifacts": "nf_splice.services.lifecycle",
    "plan_draft_migration": "nf_splice.services.migration",
    "plan_promotion": "nf_splice.services.lifecycle",
    "plan_state_migration": "nf_splice.services.state",
    "promote": "nf_splice.services.lifecycle",
    "recover": "nf_splice.services.lifecycle",
    "validate_bundle": "nf_splice.services.lifecycle",
    "validate_layer": "nf_splice.services.lifecycle",
    "workspace_status": "nf_splice.services.workspace",
}

__all__ = [
    "ApplicationService",
    "ArtifactState",
    "ArtifactStatus",
    "BundleIssue",
    "BundleReport",
    "FinalState",
    "InitialisationReport",
    "LifecycleError",
    "MigrationChangeKind",
    "MigrationError",
    "MigrationNote",
    "MigrationPlan",
    "PromotionPlan",
    "PromotionResult",
    "RecoveryResult",
    "StateMigrationChange",
    "StateMigrationError",
    "StateMigrationResult",
    "WorkspaceStatus",
    "apply_draft_migration",
    "apply_state_migration",
    "initialise",
    "inspect_layer",
    "list_artifacts",
    "plan_draft_migration",
    "plan_promotion",
    "plan_state_migration",
    "promote",
    "recover",
    "validate_bundle",
    "validate_layer",
    "workspace_status",
]


def __getattr__(name: str) -> Any:
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(importlib.import_module(_EXPORTS[name]), name)
