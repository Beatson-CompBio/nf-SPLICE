"""Per-layer promotion, transactional publication and bundle validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from layer_fixtures import ADA, ready_repository
from nf_splice.contracts import families
from nf_splice.services import lifecycle
from nf_splice.services.lifecycle import (
    ArtifactState,
    FinalState,
    LifecycleError,
    list_artifacts,
    plan_promotion,
    promote,
    recover,
    validate_bundle,
)


def _states(root: Path) -> dict[str, ArtifactState]:
    return {item.layer: item.state for item in list_artifacts(root)}


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted((root / "splice").rglob("*"))
        if path.is_file() and "/drafts/" not in path.as_posix()
    }


def test_layers_promote_independently_then_publish_coherently(tmp_path: Path) -> None:
    ready_repository(tmp_path)
    assert set(_states(tmp_path).values()) == {ArtifactState.READY}

    result = promote(tmp_path, "outputs", ADA)
    assert result.wrote == ("outputs.schema.json", "outputs.yaml")
    assert not (tmp_path / "splice" / "bundle.json").exists()
    assert validate_bundle(tmp_path).issues[0].rule == "missing"

    published = promote(tmp_path, None, ADA)
    assert "bundle.json" in published.wrote and "nf-splice.lock.json" in published.wrote
    report = validate_bundle(tmp_path)
    assert report.valid, report.issues
    assert report.checked_files >= 5
    splice = tmp_path / "splice"
    names = {path.name for path in splice.iterdir()}
    assert not names & {"outputs.json", "nf-splice.yaml", "outputs.schema.draft.json"}
    bundle = json.loads((splice / "bundle.json").read_text(encoding="utf-8"))
    assert (
        bundle["schema_id"] == "https://schemas.splice-data.io/workflow-bundle/bundle"
    )
    assert set(bundle["schemas"]) == {item.id for item in families()}
    assert bundle["default_execution_profile"] == "local"
    lock = json.loads((splice / "nf-splice.lock.json").read_text(encoding="utf-8"))
    assert lock["schema_version"] == "2.0"
    assert "nf-splice.lock.json" not in lock["managed_files"]
    assert not any("drafts/" in path for path in lock["managed_files"])
    assert "conf/local.config" in lock["sources"]
    readme = (splice / "README.md").read_text(encoding="utf-8")
    assert "manifest" not in readme.lower() and "job" in readme

    before = _snapshot(tmp_path)
    again = promote(tmp_path, None, ADA)
    assert again.wrote == ()
    assert _snapshot(tmp_path) == before
    assert {
        final.state
        for item in list_artifacts(tmp_path)
        for final in item.finals
        if item.layer != "bundle"
    } == {FinalState.CURRENT}


def test_external_final_edits_are_detected_and_never_overwritten(
    tmp_path: Path,
) -> None:
    ready_repository(tmp_path)
    promote(tmp_path, None, ADA)
    schema = tmp_path / "splice" / "outputs.schema.json"
    edited = schema.read_text(encoding="utf-8").replace("Job report.", "Edited.")
    schema.write_text(edited, encoding="utf-8")
    states = {
        final.path: final.state
        for item in list_artifacts(tmp_path)
        for final in item.finals
    }
    assert states["outputs.schema.json"] is FinalState.DRIFTED
    assert "drift" in {item.rule for item in validate_bundle(tmp_path).issues}
    with pytest.raises(LifecycleError, match="edited after it was published"):
        promote(tmp_path, None, ADA, replace_existing=True)
    assert schema.read_text(encoding="utf-8") == edited
    promote(
        tmp_path,
        None,
        ADA,
        replace_existing=True,
        overwrite_edited=["splice/outputs.schema.json"],
    )
    assert validate_bundle(tmp_path).valid


def test_failed_publication_rolls_back_to_the_previous_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ready_repository(tmp_path)
    promote(tmp_path, None, ADA)
    (tmp_path / "splice" / "unknown.txt").write_text("keep", encoding="utf-8")
    before = _snapshot(tmp_path)
    from nf_splice.layers.bundle import set_identity_fields
    from nf_splice.layers.inputs import sync_identity
    from nf_splice.layers.provenance import generate_minimal

    set_identity_fields(tmp_path, {"version": "1.3.0"}, ADA)
    sync_identity(tmp_path, ADA)
    generate_minimal(tmp_path, ADA, at="2026-10-15T11:00:00Z")
    calls = {"count": 0}
    original = lifecycle.replace_file

    def failing(source: Path, target: Path) -> None:
        calls["count"] += 1
        if calls["count"] == 3:
            raise OSError("disk full")
        original(source, target)

    monkeypatch.setattr(lifecycle, "replace_file", failing)
    with pytest.raises(OSError, match="disk full"):
        promote(tmp_path, None, ADA, replace_existing=True)
    assert _snapshot(tmp_path) == before
    assert not (tmp_path / "splice" / lifecycle.JOURNAL).exists()
    rolled_back = validate_bundle(tmp_path)
    assert rolled_back.valid  # the previous release is still coherent
    assert "unpromoted_draft" in {item.rule for item in rolled_back.issues}
    monkeypatch.setattr(lifecycle, "replace_file", original)
    promote(tmp_path, None, ADA, replace_existing=True)
    assert (
        json.loads((tmp_path / "splice" / "bundle.json").read_text())["pipeline"][
            "version"
        ]
        == "1.3.0"
    )
    assert (tmp_path / "splice" / "unknown.txt").read_text() == "keep"


def test_interrupted_publication_is_recovered_explicitly(tmp_path: Path) -> None:
    ready_repository(tmp_path)
    promote(tmp_path, None, ADA)
    splice = tmp_path / "splice"
    original = (splice / "bundle.json").read_bytes()
    backup = splice / lifecycle.BACKUP / "abc"
    backup.mkdir(parents=True)
    (backup / "bundle.json").write_bytes(original)
    (splice / "bundle.json").write_text("{partial", encoding="utf-8")
    (splice / lifecycle.JOURNAL).write_text(
        json.dumps(
            {"token": "abc", "files": ["bundle.json"], "existing": ["bundle.json"]}
        ),
        encoding="utf-8",
    )
    with pytest.raises(LifecycleError, match="recover"):
        plan_promotion(tmp_path)
    result = recover(tmp_path)
    assert result.recovered and result.restored == ("bundle.json",)
    assert (splice / "bundle.json").read_bytes() == original
    assert not (splice / lifecycle.BACKUP).exists()
    assert recover(tmp_path).recovered is False


def test_blocked_and_unsafe_targets(tmp_path: Path) -> None:
    from layer_fixtures import write_pipeline

    write_pipeline(tmp_path)
    plan = plan_promotion(tmp_path)
    assert not plan.ready
    with pytest.raises(LifecycleError, match="blocked"):
        promote(tmp_path, None, ADA)

    other = tmp_path / "other"
    other.mkdir()
    ready_repository(other)
    (other / "splice").mkdir(exist_ok=True)
    (other / "splice" / "outputs.yaml").symlink_to(other / "main.nf")
    with pytest.raises(LifecycleError, match="non-regular"):
        promote(other, "outputs", ADA)


def test_identical_reviewed_inputs_produce_identical_bundles(tmp_path: Path) -> None:
    first, second = tmp_path / "a", tmp_path / "b"
    for root in (first, second):
        root.mkdir()
        ready_repository(root)
        promote(root, None, ADA)
    assert {
        key.removeprefix("a/"): value for key, value in _snapshot(first).items()
    } == {key.removeprefix("b/"): value for key, value in _snapshot(second).items()}


def test_tree_inspection_keeps_drafts_private_and_flags_leftovers(
    tmp_path: Path,
) -> None:
    from nf_splice.domain import PathClassification
    from nf_splice.inspectors import inspect_splice_tree

    ready_repository(tmp_path)
    promote(tmp_path, None, ADA)
    (tmp_path / "splice" / lifecycle.JOURNAL).write_text("{}", encoding="utf-8")
    by_path = {
        item.path: item.classification for item in inspect_splice_tree(tmp_path).paths
    }
    # Drafts and reviews are private and never part of splice/.
    assert not any(path.startswith("drafts") for path in by_path)
    assert by_path["bundle.json"] is PathClassification.RECOGNIZED
    assert by_path["nf-splice.lock.json"] is PathClassification.RECOGNIZED
    assert by_path[lifecycle.JOURNAL] is PathClassification.MALFORMED
    # A drafts folder in splice/ is an earlier layout that must be migrated.
    (tmp_path / "splice" / "drafts").mkdir()
    (tmp_path / "splice" / "drafts" / "outputs.draft.yaml").write_text("x: 1\n")
    by_path = {
        item.path: item.classification for item in inspect_splice_tree(tmp_path).paths
    }
    assert by_path["drafts/outputs.draft.yaml"] is PathClassification.MALFORMED
