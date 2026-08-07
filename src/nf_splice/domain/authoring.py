"""Canonical domain models for nf-splice authoring state."""

from __future__ import annotations

from enum import Enum
from typing import Annotated, ClassVar

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

AUTHORING_SCHEMA_VERSION = "1.0"

NonEmptyString = Annotated[str, Field(min_length=1)]


class DomainModel(BaseModel):
    """Strict, immutable base for canonical domain values."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class PipelineIdentity(DomainModel):
    """Reviewed or unresolved identity of the pipeline being integrated."""

    name: NonEmptyString | None = None
    version: NonEmptyString | None = None
    repository_url: NonEmptyString | None = None
    release_url: NonEmptyString | None = None


class OutputContractSettings(DomainModel):
    """Reviewed version boundary for generated output contracts."""

    schema_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")


class EvidenceProvenance(DomainModel):
    """Location and revision from which evidence was observed."""

    source: NonEmptyString
    location: NonEmptyString
    repository_revision: NonEmptyString | None = None


class Evidence(DomainModel):
    """A detected fact that may support one or more decisions."""

    id: NonEmptyString
    provenance: EvidenceProvenance
    observed_value: JsonValue
    confidence: float = Field(ge=0.0, le=1.0)


class DecisionStatus(str, Enum):
    """Review state of a candidate authoring decision."""

    CANDIDATE = "candidate"
    REVIEWED = "reviewed"
    REJECTED = "rejected"
    CONFLICT = "conflict"


class InvalidDecisionTransition(ValueError):
    """Raised when a decision cannot move directly to a requested state."""


class Decision(DomainModel):
    """A candidate or explicit developer choice backed by evidence."""

    _TRANSITIONS: ClassVar[dict[DecisionStatus, frozenset[DecisionStatus]]] = {
        DecisionStatus.CANDIDATE: frozenset(
            {
                DecisionStatus.REVIEWED,
                DecisionStatus.REJECTED,
                DecisionStatus.CONFLICT,
            }
        ),
        DecisionStatus.REVIEWED: frozenset(
            {DecisionStatus.REJECTED, DecisionStatus.CONFLICT}
        ),
        DecisionStatus.REJECTED: frozenset(
            {DecisionStatus.REVIEWED, DecisionStatus.CONFLICT}
        ),
        DecisionStatus.CONFLICT: frozenset(
            {DecisionStatus.REVIEWED, DecisionStatus.REJECTED}
        ),
    }

    id: NonEmptyString
    status: DecisionStatus = DecisionStatus.CANDIDATE
    value: JsonValue | None = None
    evidence_ids: tuple[NonEmptyString, ...] = ()
    reason: NonEmptyString | None = None

    @model_validator(mode="after")
    def validate_state(self) -> Decision:
        """Require the supporting information appropriate to the state."""
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("evidence_ids must be unique")
        if self.status is DecisionStatus.REVIEWED and self.value is None:
            raise ValueError("a reviewed decision requires a value")
        if self.status in {DecisionStatus.REJECTED, DecisionStatus.CONFLICT}:
            if self.reason is None:
                raise ValueError(f"a {self.status.value} decision requires a reason")
        return self

    def transition(
        self,
        status: DecisionStatus,
        *,
        value: JsonValue | None = None,
        reason: str | None = None,
    ) -> Decision:
        """Return a validated decision in an explicitly allowed next state."""
        if status not in self._TRANSITIONS[self.status]:
            raise InvalidDecisionTransition(
                f"cannot transition decision {self.id!r} "
                f"from {self.status.value!r} to {status.value!r}"
            )

        update: dict[str, object] = {"status": status}
        if value is not None:
            update["value"] = value
        if reason is not None:
            update["reason"] = reason
        return Decision.model_validate(self.model_copy(update=update).model_dump())


class UnresolvedDecision(DomainModel):
    """Reason a decision still blocks one integration layer."""

    decision_id: NonEmptyString
    reason: NonEmptyString


class LayerStatus(str, Enum):
    """Readiness of an independently generated integration layer."""

    NOT_CONFIGURED = "not_configured"
    BLOCKED = "blocked"
    READY = "ready"


class LayerState(DomainModel):
    """Decision membership and blockers for an integration layer."""

    name: NonEmptyString
    configured: bool = False
    decision_ids: tuple[NonEmptyString, ...] = ()
    unresolved: tuple[UnresolvedDecision, ...] = ()

    @model_validator(mode="after")
    def validate_references(self) -> LayerState:
        """Keep layer references deterministic and unambiguous."""
        if len(self.decision_ids) != len(set(self.decision_ids)):
            raise ValueError("decision_ids must be unique")
        unresolved_ids = [item.decision_id for item in self.unresolved]
        if len(unresolved_ids) != len(set(unresolved_ids)):
            raise ValueError("unresolved decision_ids must be unique per layer")
        if not set(unresolved_ids).issubset(self.decision_ids):
            raise ValueError("unresolved decisions must belong to the layer")
        return self

    @property
    def status(self) -> LayerStatus:
        """Derive readiness so stored state cannot contradict its blockers."""
        if self.unresolved:
            return LayerStatus.BLOCKED
        if not self.configured:
            return LayerStatus.NOT_CONFIGURED
        return LayerStatus.READY


class AuthoringDocument(DomainModel):
    """Versioned canonical content of ``splice/nf-splice.yaml``."""

    schema_version: str = AUTHORING_SCHEMA_VERSION
    pipeline: PipelineIdentity = PipelineIdentity()
    output_contract: OutputContractSettings | None = None
    evidence: tuple[Evidence, ...] = ()
    decisions: tuple[Decision, ...] = ()
    layers: tuple[LayerState, ...] = ()

    @model_validator(mode="after")
    def validate_document(self) -> AuthoringDocument:
        """Validate identifiers and all references across the document."""
        if self.schema_version != AUTHORING_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported authoring schema version {self.schema_version!r}"
            )

        evidence_ids = [item.id for item in self.evidence]
        decision_ids = [item.id for item in self.decisions]
        layer_names = [item.name for item in self.layers]
        self._require_unique(evidence_ids, "evidence ids")
        self._require_unique(decision_ids, "decision ids")
        self._require_unique(layer_names, "layer names")

        known_evidence = set(evidence_ids)
        for decision in self.decisions:
            if not set(decision.evidence_ids).issubset(known_evidence):
                raise ValueError(
                    f"decision {decision.id!r} references unknown evidence"
                )

        known_decisions = set(decision_ids)
        decisions_by_id = {item.id: item for item in self.decisions}
        for layer in self.layers:
            if not set(layer.decision_ids).issubset(known_decisions):
                raise ValueError(f"layer {layer.name!r} references unknown decisions")
            for unresolved in layer.unresolved:
                status = decisions_by_id[unresolved.decision_id].status
                if status not in {DecisionStatus.CANDIDATE, DecisionStatus.CONFLICT}:
                    raise ValueError(
                        f"layer {layer.name!r} marks a {status.value} decision "
                        "unresolved"
                    )
        return self

    @staticmethod
    def _require_unique(values: list[str], label: str) -> None:
        if len(values) != len(set(values)):
            raise ValueError(f"{label} must be unique")
