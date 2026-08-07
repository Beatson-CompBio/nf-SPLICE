"""Acceptance tests for shared application-service results."""

from pathlib import Path

from nf_splice.domain import (
    AuthoringDocument,
    Decision,
    LayerState,
    LayerStatus,
    UnresolvedDecision,
    dump_authoring_document,
)
from nf_splice.services import ApplicationService, AuthoringState, Operation


def test_workspace_snapshot_summarizes_inspection_once(tmp_path: Path) -> None:
    (tmp_path / "main.nf").write_text(
        "workflow {\n    output { reports = REPORT.out }\n}\n",
        encoding="utf-8",
    )

    snapshot = ApplicationService().inspect(tmp_path)

    assert snapshot.inspection.root == str(tmp_path.resolve())
    assert snapshot.authoring.state is AuthoringState.ABSENT
    assert snapshot.authoring.unresolved_decisions is None
    assert sum(item.count for item in snapshot.evidence_counts) == len(
        snapshot.inspection.evidence
    )
    assert snapshot.layers[0].name == "identity"
    assert snapshot.layers[0].status is LayerStatus.NOT_CONFIGURED
    assert snapshot.warnings == ("No repository-root splice/ integration exists.",)


def test_workspace_snapshot_reads_existing_authoring_state(tmp_path: Path) -> None:
    document = AuthoringDocument(
        decisions=(Decision(id="output-path"),),
        layers=(
            LayerState(
                name="outputs",
                configured=True,
                decision_ids=("output-path",),
                unresolved=(
                    UnresolvedDecision(
                        decision_id="output-path",
                        reason="Path pattern requires review",
                    ),
                ),
            ),
        ),
    )
    (tmp_path / "nf-splice.yaml").write_text(
        dump_authoring_document(document), encoding="utf-8"
    )

    snapshot = ApplicationService().inspect(tmp_path)
    outputs = next(layer for layer in snapshot.layers if layer.name == "outputs")

    assert snapshot.authoring.state is AuthoringState.VALID
    assert snapshot.authoring.unresolved_decisions == 1
    assert outputs.status is LayerStatus.BLOCKED
    assert outputs.decision_count == 1
    assert outputs.unresolved_decisions == 1


def test_invalid_authoring_and_unavailable_operations_are_explicit(
    tmp_path: Path,
) -> None:
    (tmp_path / "nf-splice.yaml").write_text("schema_version: '99'\n", encoding="utf-8")
    service = ApplicationService()

    snapshot = service.inspect(tmp_path)

    assert snapshot.authoring.state is AuthoringState.INVALID
    assert any("nf-splice.yaml is invalid" in item for item in snapshot.warnings)
    for operation in Operation:
        result = service.unavailable(operation)
        assert result.operation is operation
        assert result.message.endswith("is not available yet.")
