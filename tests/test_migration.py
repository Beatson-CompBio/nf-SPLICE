"""Non-destructive migration of the frozen 0.1.0 bundle to 0.3.0 drafts."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from layer_fixtures import ADA
from nf_splice.layers.base import read_layer
from nf_splice.layers.components import set_image_policy
from nf_splice.layers.execution import set_default_profile
from nf_splice.layers.provenance import prepare_enrichment
from nf_splice.runtime import generate_analysis_output
from nf_splice.services.lifecycle import list_artifacts, promote, validate_bundle
from nf_splice.services.migration import (
    MigrationError,
    apply_draft_migration,
    plan_draft_migration,
)

LEGACY = Path(__file__).parent / "fixtures" / "legacy-0.1.0"


def _copy(root: Path) -> Path:
    repository = root / "repository"
    shutil.copytree(LEGACY / "repository", repository)
    return repository


def _bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_preview_is_read_only_and_reports_every_transformation(tmp_path: Path) -> None:
    repository = _copy(tmp_path)
    before = _bytes(repository)
    plan = plan_draft_migration(repository)
    assert _bytes(repository) == before
    kinds = {(note.layer, note.kind) for note in plan.notes}
    assert ("outputs", "blocker") in kinds  # legacy library scope
    assert ("inputs", "permission") in kinds
    assert ("execution-profiles", "blocker") in kinds
    messages = " ".join(note.message for note in plan.notes)
    assert "'run' -> 'job'" in messages and "run_report" in messages
    assert sorted(plan.drafts) == sorted(
        f"splice/drafts/{name}"
        for name in (
            "bundle.draft.yaml",
            "inputs.schema.draft.yaml",
            "outputs.draft.yaml",
            "components.draft.yaml",
            "execution-profiles.draft.yaml",
            "ro-crate-metadata.draft.yaml",
        )
    )
    assert "editable_by" in plan.drafts["splice/drafts/inputs.schema.draft.yaml"]
    assert json.loads(json.dumps(plan.to_json()))["source"] == "splice/nf-splice.yaml"


def test_apply_migrates_semantics_without_touching_legacy_files(tmp_path: Path) -> None:
    repository = _copy(tmp_path)
    legacy_files = _bytes(repository)
    apply_draft_migration(repository, ADA, map_library_to_run=True)
    for relative, payload in legacy_files.items():
        assert (repository / relative).read_bytes() == payload, relative

    inputs = read_layer(repository, "inputs").draft
    assert inputs is not None
    properties = {
        name: value
        for group in inputs.data["$defs"].values()
        for name, value in group["properties"].items()
    }
    assert properties["input"]["x-splice-access"] == {"editable_by": ["user"]}
    assert properties["outdir"]["x-splice-access"] == {"editable_by": ["platform"]}
    assert properties["max_cpus"]["x-splice-access"] == {"editable_by": ["platform"]}
    assert properties["max_cpus"]["x-splice-ui"] == {"visibility": "hidden"}

    outputs = read_layer(repository, "outputs").draft
    assert outputs is not None
    by_key = {item["key"]: item for item in outputs.data["outputs"]}
    assert by_key["multiqc_report"]["scopes"] == ["job"]
    assert by_key["multiqc_report"]["category"] == "job_report"
    assert by_key["counts"]["scopes"] == ["sample"]
    assert by_key["library_qc"]["scopes"] == ["run"]
    assert by_key["library_qc"]["path_patterns"] == [r"^qc/{sample}/{run}\.json$"]

    components = read_layer(repository, "components").draft
    assert components is not None
    legacy = json.loads(
        (repository / "splice" / "components.json").read_text(encoding="utf-8")
    )
    assert components.data["containers"][0]["id"] == legacy["containers"][0]["id"]

    with pytest.raises(MigrationError, match="approval"):
        from nf_splice.domain import Actor
        from nf_splice.layers import ChangeContext

        apply_draft_migration(
            repository, ChangeContext(actor=Actor(label="x"), approved=False)
        )


def test_unmapped_library_scope_blocks_until_reviewed(tmp_path: Path) -> None:
    repository = _copy(tmp_path)
    apply_draft_migration(repository, ADA)
    states = {item.layer: item.state.value for item in list_artifacts(repository)}
    assert states["outputs"] == "incomplete"


def test_migrated_bundle_completes_publishes_and_runs(tmp_path: Path) -> None:
    repository = _copy(tmp_path)
    apply_draft_migration(repository, ADA, map_library_to_run=True)
    set_image_policy(repository, False, ADA)
    set_default_profile(repository, "profile-local-6c6f63616c", ADA)
    prepare_enrichment(repository, ADA, at="2026-10-15T10:00:00Z")
    from nf_splice.layers.bundle import validate_bundle_draft

    pending = [
        item.pointer
        for item in validate_bundle_draft(repository).issues
        if item.code == "unconfirmed_detected_value"
    ]
    if pending:
        from nf_splice.layers import confirm_values

        confirm_values(repository, "bundle", pending, ADA)
    statuses = {
        item.layer: (item.state.value, item.errors)
        for item in list_artifacts(repository)
    }
    assert all(state == "ready" for state, _ in statuses.values()), statuses
    promote(
        repository,
        None,
        ADA,
        replace_existing=True,
    )
    report = validate_bundle(repository)
    assert report.valid, report.issues
    assert (repository / "splice" / "nf-splice.yaml").exists()  # untouched source
    bundle = json.loads((repository / "splice" / "bundle.json").read_text())
    assert bundle["schema_version"] == "0.3.0"

    samples = tmp_path / "samples.csv"
    samples.write_text(
        "sample,run_id\nS1,S1_L001\nS1,S1_L002\nS2,S2_L001\n", encoding="utf-8"
    )
    result = generate_analysis_output(
        repository,
        publish_directory=LEGACY / "completed-job" / "results",
        sample_metadata=samples,
        job_metadata={"job_id_short": "A123"},
    )
    runs = {
        (item["run_id"], item["sample_id"])
        for item in result.document["files"]
        if item["scope"] == "run"
    }
    assert runs == {("S1_L001", "S1"), ("S1_L002", "S1"), ("S2_L001", "S2")}
    assert dict(result.validation.by_scope) == {"job": 1, "run": 3, "sample": 2}
