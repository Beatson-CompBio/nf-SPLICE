"""Acceptance tests for reviewed output catalogue and schema rendering."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from nf_splice.domain import (
    AuthoringDocument,
    Decision,
    DecisionStatus,
    LayerState,
    OutputCategory,
    OutputContractSettings,
    OutputEntityType,
    OutputFormat,
    OutputScope,
    PipelineIdentity,
    ReviewedOutput,
    UnresolvedDecision,
    dump_authoring_document,
)
from nf_splice.renderers import OutputContractError, render_output_contracts
from nf_splice.services import (
    ChangeKind,
    OutputContractBuildError,
    build_output_contracts,
    plan_output_contracts,
)


def reviewed_document(
    *, blocked: bool = False, title: str = "Run report"
) -> AuthoringDocument:
    """Return representative reviewed state shared with runtime acceptance tests."""
    outputs = (
        ReviewedOutput(
            key="run_report_html",
            title=title,
            description="Run-level HTML report.",
            category=OutputCategory.RUN_REPORT,
            formats=(OutputFormat.HTML,),
            scopes=(OutputScope.RUN,),
            entity_types=(OutputEntityType.FILE,),
            path_patterns=(r"^reports/report\.html$",),
        ),
        ReviewedOutput(
            key="sample_metrics_json",
            title="Sample metrics",
            description="Per-sample JSON metrics.",
            category=OutputCategory.QUALITY_CONTROL,
            formats=(OutputFormat.JSON,),
            scopes=(OutputScope.SAMPLE,),
            entity_types=(OutputEntityType.FILE,),
            path_patterns=(r"^metrics/{sample}\.json$",),
        ),
        ReviewedOutput(
            key="sample_quantification",
            title="Sample quantification directory",
            description="Complete per-sample quantification results.",
            category=OutputCategory.QUANTIFICATION,
            formats=(OutputFormat.DIRECTORY,),
            scopes=(OutputScope.SAMPLE,),
            entity_types=(OutputEntityType.DIRECTORY,),
            path_patterns=(r"^quant/{sample}$",),
        ),
    )
    decisions = tuple(
        Decision(
            id=f"output:{index}",
            status=DecisionStatus.REVIEWED,
            value=output.model_dump(mode="json"),
        )
        for index, output in enumerate(outputs)
    )
    unresolved = (
        (
            UnresolvedDecision(
                decision_id="output:0",
                reason="Output meaning still requires review",
            ),
        )
        if blocked
        else ()
    )
    if blocked:
        decisions = (
            Decision(id="output:0", value={"candidate": True}),
            *decisions[1:],
        )
    return AuthoringDocument(
        pipeline=PipelineIdentity(
            name="pipeline",
            version="2.3.4",
            repository_url="https://github.com/org/pipeline",
            release_url="https://github.com/org/pipeline/releases/tag/v2.3.4",
        ),
        output_contract=OutputContractSettings(schema_version="1.2.0"),
        decisions=decisions,
        layers=(
            LayerState(
                name="outputs",
                configured=True,
                decision_ids=tuple(item.id for item in decisions),
                unresolved=unresolved,
            ),
        ),
    )


def write_document(root: Path, document: AuthoringDocument) -> None:
    (root / "nf-splice.yaml").write_text(
        dump_authoring_document(document), encoding="utf-8"
    )


def test_renderer_is_deterministic_and_catalogue_matches_schema() -> None:
    document = reviewed_document()

    first = render_output_contracts(document)
    second = render_output_contracts(document)
    catalogue = yaml.safe_load(first.catalogue)
    schema = json.loads(first.schema)

    assert first == second
    assert catalogue["schema_version"] == "1.2.0"
    assert catalogue["pipeline"]["version"] == "2.3.4"
    assert [item["key"] for item in catalogue["outputs"]] == [
        "sample_metrics_json",
        "sample_quantification",
        "run_report_html",
    ]
    catalogued = {
        item["key"]: item for item in schema["x-output-catalog"]["output_types"]
    }
    constrained = {
        item["if"]["properties"]["output_type"]["const"]: item["then"]["properties"]
        for item in schema["definitions"]["file_record"]["allOf"]
    }
    assert catalogued.keys() == constrained.keys()
    for key, output in catalogued.items():
        assert constrained[key]["category"]["const"] == output["category"]
        assert constrained[key]["scope"]["enum"] == output["scope"]
    assert "analysis_output_schema_version" in schema["properties"]
    assert "manifest" not in first.catalogue.lower()
    assert "manifest" not in first.schema.lower()


def test_renderer_blocks_unresolved_or_unversioned_state() -> None:
    with pytest.raises(OutputContractError, match="1 unresolved"):
        render_output_contracts(reviewed_document(blocked=True))

    unversioned = reviewed_document().model_copy(update={"output_contract": None})
    with pytest.raises(OutputContractError, match="contract version is not reviewed"):
        render_output_contracts(
            AuthoringDocument.model_validate(unversioned.model_dump())
        )


def test_output_contract_build_is_visible_collision_safe_and_idempotent(
    tmp_path: Path,
) -> None:
    write_document(tmp_path, reviewed_document())
    (tmp_path / "splice").mkdir()
    unknown = tmp_path / "splice" / "developer-notes.txt"
    unknown.write_text("preserve\n", encoding="utf-8")

    plan = plan_output_contracts(tmp_path)

    assert {item.kind for item in plan.changes} == {ChangeKind.CREATE}
    assert all("/dev/null" in item.diff for item in plan.changes)
    assert not (tmp_path / "splice" / "outputs.yaml").exists()

    built = build_output_contracts(tmp_path)
    first_bytes = {item.path.name: item.path.read_bytes() for item in built.changes}
    first_mtimes = {
        item.path.name: item.path.stat().st_mtime_ns for item in built.changes
    }

    assert built.wrote
    assert unknown.read_text(encoding="utf-8") == "preserve\n"
    second = build_output_contracts(tmp_path)
    assert not second.wrote
    assert {item.kind for item in second.changes} == {ChangeKind.UNCHANGED}
    assert {
        item.path.name: item.path.read_bytes() for item in second.changes
    } == first_bytes
    assert {
        item.path.name: item.path.stat().st_mtime_ns for item in second.changes
    } == first_mtimes

    write_document(tmp_path, reviewed_document(title="Updated run report"))
    update = plan_output_contracts(tmp_path)
    assert ChangeKind.UPDATE in {item.kind for item in update.changes}
    assert any("Updated run report" in item.diff for item in update.changes)
    with pytest.raises(OutputContractBuildError, match="--replace-existing"):
        build_output_contracts(tmp_path)
    assert (tmp_path / "splice" / "outputs.yaml").read_bytes() == first_bytes[
        "outputs.yaml"
    ]

    replaced = build_output_contracts(tmp_path, replace_existing=True)
    assert replaced.wrote
    assert "Updated run report" in (tmp_path / "splice" / "outputs.yaml").read_text(
        encoding="utf-8"
    )


def test_malformed_recognized_contract_is_never_overwritten(tmp_path: Path) -> None:
    write_document(tmp_path, reviewed_document())
    splice = tmp_path / "splice"
    splice.mkdir()
    malformed = splice / "outputs.yaml"
    malformed.write_text("outputs: not-a-list\n", encoding="utf-8")

    with pytest.raises(OutputContractBuildError, match="malformed"):
        build_output_contracts(tmp_path, replace_existing=True)

    assert malformed.read_text(encoding="utf-8") == "outputs: not-a-list\n"
