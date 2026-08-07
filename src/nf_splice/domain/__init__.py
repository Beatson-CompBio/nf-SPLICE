"""Public domain API for canonical nf-splice authoring state."""

from nf_splice.domain.authoring import (
    AUTHORING_SCHEMA_VERSION,
    AuthoringDocument,
    Decision,
    DecisionStatus,
    Evidence,
    EvidenceProvenance,
    InvalidDecisionTransition,
    LayerState,
    LayerStatus,
    PipelineIdentity,
    UnresolvedDecision,
)
from nf_splice.domain.serialization import (
    AuthoringDocumentError,
    InvalidAuthoringDocument,
    UnsupportedSchemaVersion,
    dump_authoring_document,
    load_authoring_document,
)

__all__ = [
    "AUTHORING_SCHEMA_VERSION",
    "AuthoringDocument",
    "AuthoringDocumentError",
    "Decision",
    "DecisionStatus",
    "Evidence",
    "EvidenceProvenance",
    "InvalidAuthoringDocument",
    "InvalidDecisionTransition",
    "LayerState",
    "LayerStatus",
    "PipelineIdentity",
    "UnresolvedDecision",
    "UnsupportedSchemaVersion",
    "dump_authoring_document",
    "load_authoring_document",
]
