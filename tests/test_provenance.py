"""Acceptance tests for reviewed deterministic workflow RO-Crate metadata."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from nf_splice.cli import app
from nf_splice.domain import (
    AuthoringDocument,
    Decision,
    DecisionStatus,
    LayerState,
    PipelineIdentity,
    ReviewedAuthor,
    ReviewedComponent,
    dump_authoring_document,
)
from nf_splice.renderers import ProvenanceRenderError, validate_ro_crate
from nf_splice.services import (
    ApplicationService,
    StaticChangeKind,
    unresolved_provenance_candidates,
)

runner = CliRunner()


def _repository(root: Path) -> ApplicationService:
    component = ReviewedComponent(
        id="component:modules__local__tool",
        name="tool",
        path="modules/local/tool",
        namespace="local",
        tool_name="tool",
        version="1.2.3",
        container_uri="quay.io/example/tool:1.2.3",
        evidence_locations=("modules/local/tool/main.nf",),
    )
    decision = Decision(
        id=component.id,
        status=DecisionStatus.REVIEWED,
        value=component.model_dump(mode="json"),
    )
    document = AuthoringDocument(
        pipeline=PipelineIdentity(
            name="pipeline",
            version="1.0.0",
            repository_url="https://github.com/org/pipeline",
            release_url="https://github.com/org/pipeline/releases/tag/1.0.0",
        ),
        decisions=(decision,),
        layers=(
            LayerState(
                name="components",
                configured=True,
                decision_ids=(decision.id,),
            ),
        ),
    )
    splice = root / "splice"
    splice.mkdir()
    (splice / "nf-splice.yaml").write_text(
        dump_authoring_document(document), encoding="utf-8"
    )
    return ApplicationService()


def test_minimal_internal_ro_crate_is_reviewed_valid_and_deterministic(
    tmp_path: Path,
) -> None:
    service = _repository(tmp_path)
    document = service.discover_provenance(tmp_path)

    assert [item.id for item in unresolved_provenance_candidates(document)] == [
        "provenance:minimal_internal"
    ]
    with pytest.raises(ProvenanceRenderError, match="not ready"):
        service.plan_provenance(tmp_path)

    service.review_provenance(
        tmp_path,
        "provenance:minimal_internal",
        authors=(
            ReviewedAuthor(name="Ada Example", identifier="https://orcid.org/0000"),
        ),
        licenses=("https://spdx.org/licenses/MIT.html",),
        published_at="2026-08-07",
        source_revision="0123456789abcdef",
    )
    preview = service.plan_provenance(tmp_path)
    built = service.build_provenance(tmp_path)
    repeated = service.plan_provenance(tmp_path)
    payload = json.loads((tmp_path / "splice" / "ro-crate-metadata.json").read_text())

    assert preview.change.kind is StaticChangeKind.CREATE
    assert built.wrote
    assert repeated.change.kind is StaticChangeKind.UNCHANGED
    validate_ro_crate(payload)
    by_id = {item["@id"]: item for item in payload["@graph"]}
    assert by_id["./"]["identifier"] == "0123456789abcdef"
    assert by_id["./"]["creator"] == [{"@id": "https://orcid.org/0000"}]
    assert len(by_id["main.nf"]["softwareRequirements"]) == 1


def test_existing_ro_crate_is_a_candidate_and_selected_normalization_preserves_extras(
    tmp_path: Path,
) -> None:
    service = _repository(tmp_path)
    existing = {
        "@context": "https://w3id.org/ro/crate/1.1/context",
        "@graph": [
            {"@id": "./", "@type": "Dataset", "name": "stale"},
            {"@id": "docs/", "@type": "Dataset", "description": "Documentation"},
        ],
    }
    (tmp_path / "ro-crate-metadata.json").write_text(
        json.dumps(existing), encoding="utf-8"
    )
    document = service.discover_provenance(tmp_path)
    candidates = unresolved_provenance_candidates(document)
    selected = next(
        item for item in candidates if item.strategy.value == "normalize_existing"
    )

    assert len(candidates) == 2
    service.review_provenance(
        tmp_path,
        selected.id,
        authors=(ReviewedAuthor(name="Ada Example"),),
        licenses=("https://spdx.org/licenses/MIT.html",),
        published_at="2026-08-07",
        source_revision="abcdef",
    )
    service.build_provenance(tmp_path)
    payload = json.loads((tmp_path / "splice" / "ro-crate-metadata.json").read_text())
    by_id = {item["@id"]: item for item in payload["@graph"]}

    assert by_id["./"]["name"] == "pipeline"
    assert by_id["docs/"]["description"] == "Documentation"


def test_ro_crate_requires_reviewed_components_and_protects_malformed_target(
    tmp_path: Path,
) -> None:
    service = ApplicationService()
    service.initialise(
        tmp_path,
        name="pipeline",
        version="1.0.0",
        repository_url="https://github.com/org/pipeline",
    )
    service.discover_provenance(tmp_path)
    service.review_provenance(
        tmp_path,
        "provenance:minimal_internal",
        authors=(ReviewedAuthor(name="Ada Example"),),
        licenses=("MIT",),
        published_at="2026-08-07",
        source_revision="abcdef",
    )

    with pytest.raises(ProvenanceRenderError, match="component layer"):
        service.plan_provenance(tmp_path)


def test_cli_reviews_and_builds_provenance(tmp_path: Path) -> None:
    _repository(tmp_path)
    decision = tmp_path / "provenance.json"
    decision.write_text(
        json.dumps(
            {
                "strategy": "minimal_internal",
                "authors": [{"name": "Ada Example"}],
                "licenses": ["MIT"],
                "published_at": "2026-08-07",
                "source_revision": "abcdef",
            }
        ),
        encoding="utf-8",
    )

    configured = runner.invoke(
        app,
        [
            "configure",
            "provenance",
            "--repository",
            str(tmp_path),
            "--decision-file",
            str(decision),
        ],
    )
    checked = runner.invoke(
        app,
        ["build", "provenance", "--repository", str(tmp_path), "--check"],
    )
    built = runner.invoke(app, ["build", "provenance", "--repository", str(tmp_path)])

    assert configured.exit_code == 0
    assert "Provenance review is complete" in configured.output
    assert checked.exit_code == 0
    assert "repository was not changed" in checked.output
    assert built.exit_code == 0
    assert "Built reviewed provenance artefact" in built.output
