"""Acceptance tests for canonical authoring state."""

import pytest
from pydantic import ValidationError

from nf_splice.domain import (
    AuthoringDocument,
    Decision,
    DecisionStatus,
    Evidence,
    EvidenceProvenance,
    InvalidAuthoringDocument,
    InvalidDecisionTransition,
    LayerState,
    LayerStatus,
    PipelineIdentity,
    UnresolvedDecision,
    UnsupportedSchemaVersion,
    dump_authoring_document,
    load_authoring_document,
)


def test_authoring_document_has_deterministic_round_trip() -> None:
    document = AuthoringDocument(
        pipeline=PipelineIdentity(
            name="example-pipeline",
            version="1.2.3",
            repository_url="https://example.org/pipeline",
        ),
        evidence=(
            Evidence(
                id="pipeline-config-name",
                provenance=EvidenceProvenance(
                    source="nextflow.config",
                    location="nextflow.config pipeline name",
                    repository_revision="abc123",
                ),
                observed_value="example-pipeline",
                confidence=1.0,
            ),
        ),
        decisions=(
            Decision(
                id="pipeline-name",
                status=DecisionStatus.REVIEWED,
                value="example-pipeline",
                evidence_ids=("pipeline-config-name",),
            ),
            Decision(
                id="unused-candidate",
                status=DecisionStatus.REJECTED,
                reason="Not part of the public integration",
            ),
        ),
        layers=(
            LayerState(
                name="identity",
                configured=True,
                decision_ids=("pipeline-name", "unused-candidate"),
            ),
        ),
    )

    first_dump = dump_authoring_document(document)
    loaded = load_authoring_document(first_dump)

    assert loaded == document
    assert dump_authoring_document(loaded) == first_dump
    assert loaded.decisions[0].status is DecisionStatus.REVIEWED
    assert loaded.decisions[1].status is DecisionStatus.REJECTED


def test_decision_transitions_are_explicit_and_validated() -> None:
    candidate = Decision(id="pipeline-name")
    reviewed = candidate.transition(DecisionStatus.REVIEWED, value="pipeline")

    assert reviewed.status is DecisionStatus.REVIEWED
    assert reviewed.value == "pipeline"

    with pytest.raises(InvalidDecisionTransition):
        reviewed.transition(DecisionStatus.CANDIDATE)
    with pytest.raises(ValidationError, match="requires a reason"):
        candidate.transition(DecisionStatus.REJECTED)


def test_layer_status_is_derived_from_configuration_and_blockers() -> None:
    not_configured = LayerState(name="outputs")
    blocked = LayerState(
        name="outputs",
        configured=True,
        decision_ids=("output-path",),
        unresolved=(
            UnresolvedDecision(
                decision_id="output-path",
                reason="Path pattern requires review",
            ),
        ),
    )
    ready = LayerState(name="outputs", configured=True)

    assert not_configured.status is LayerStatus.NOT_CONFIGURED
    assert blocked.status is LayerStatus.BLOCKED
    assert ready.status is LayerStatus.READY


def test_schema_version_and_document_shape_fail_explicitly() -> None:
    with pytest.raises(UnsupportedSchemaVersion, match=r"'2\.0'"):
        load_authoring_document("schema_version: '2.0'\n")

    with pytest.raises(InvalidAuthoringDocument, match="extra_forbidden"):
        load_authoring_document("schema_version: '1.0'\nunknown: true\n")


def test_cross_document_references_are_validated() -> None:
    with pytest.raises(ValidationError, match="references unknown evidence"):
        AuthoringDocument(decisions=(Decision(id="name", evidence_ids=("missing",)),))

    with pytest.raises(ValidationError, match="marks a reviewed decision unresolved"):
        AuthoringDocument(
            decisions=(
                Decision(
                    id="name",
                    status=DecisionStatus.REVIEWED,
                    value="pipeline",
                ),
            ),
            layers=(
                LayerState(
                    name="identity",
                    decision_ids=("name",),
                    unresolved=(
                        UnresolvedDecision(
                            decision_id="name",
                            reason="Should no longer be unresolved",
                        ),
                    ),
                ),
            ),
        )
