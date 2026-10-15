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
    "PromotionPlan": "nf_splice.services.lifecycle",
    "PromotionResult": "nf_splice.services.lifecycle",
    "RecoveryResult": "nf_splice.services.lifecycle",
    "WorkspaceStatus": "nf_splice.services.workspace",
    "initialise": "nf_splice.services.workspace",
    "inspect_layer": "nf_splice.services.workspace",
    "list_artifacts": "nf_splice.services.lifecycle",
    "plan_promotion": "nf_splice.services.lifecycle",
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
    "PromotionPlan",
    "PromotionResult",
    "RecoveryResult",
    "WorkspaceStatus",
    "initialise",
    "inspect_layer",
    "list_artifacts",
    "plan_promotion",
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
