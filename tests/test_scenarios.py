"""Cross-cutting acceptance scenarios (specification section 15.2)."""

from __future__ import annotations

import asyncio
import json
import os
import socket
import stat
import sys
from pathlib import Path
from typing import Any

import pytest

from layer_fixtures import ADA, ready_repository, review_turn, write_pipeline
from nf_splice.agents import ExecutionPolicy, InteractionMode, SessionEngine
from nf_splice.agents.providers.scripted import ScriptedProvider
from nf_splice.contracts import families
from nf_splice.drafts import DraftStoreError, read_yaml
from nf_splice.layers.outputs import add_output, preview_outputs
from nf_splice.runtime import generate_analysis_output
from nf_splice.services.lifecycle import LifecycleError, promote, validate_bundle
from nf_splice.vocabulary import reserved_terms_in


def _published(root: Path) -> dict[str, bytes]:
    splice = root / "splice"
    return {
        path.relative_to(splice).as_posix(): path.read_bytes()
        for path in sorted(splice.rglob("*"))
        if path.is_file() and "drafts" not in path.relative_to(splice).parts
    }


def test_s03_manual_and_ai_work_are_interchangeable(tmp_path: Path) -> None:
    manual, assisted = tmp_path / "manual", tmp_path / "assisted"
    for root in (manual, assisted):
        root.mkdir()
        ready_repository(root)
    # One more output: described by hand in one copy, through the assistant
    # (a proposal the person approves) in the other.
    extra = {
        "key": "qc_summary",
        "title": "QC summary",
        "description": "Per-job quality-control summary.",
        "category": "quality_control",
        "formats": ["json"],
        "scopes": ["job"],
        "entity_types": ["file"],
        "path_patterns": [r"^qc/summary\.json$"],
    }
    add_output(manual, extra, ADA)

    def review(stage: str) -> dict[str, object]:
        """A scripted review: inspect the scope, find nothing to change."""
        return review_turn(stage)

    engine = SessionEngine.create(
        assisted,
        mode=InteractionMode.ASSISTED,
        provider=ScriptedProvider(
            [
                review("identity"),
                review("inputs"),
                {
                    "stage": "outputs",
                    "purpose": "plan",
                    "steps": [
                        {"tool": "analyse_routes", "arguments": {}},
                        {"tool": "route_coverage", "arguments": {}},
                        {"tool": "add_output", "arguments": {"output": extra}},
                        {"follow": "review_scope"},
                        {
                            "tool": "submit_stage_proposal",
                            "arguments": {
                                "summary": "Add the QC summary output.",
                                "evidence": ["analyse_routes"],
                            },
                        },
                    ],
                },
                review("components"),
                review("profiles"),
                review("provenance"),
            ]
        ),
        objective="describe the QC summary output",
        policy=ExecutionPolicy(),
        actor=ADA.actor,
    )
    asyncio.run(engine.advance())
    assert engine.state.pending is not None
    assert engine.state.pending.stage.value == "outputs"
    asyncio.run(engine.approve(ADA.actor))
    # The next proposal is the build, which this scenario performs manually.
    assert engine.state.pending is not None
    assert engine.state.pending.stage.value == "build"
    # External editor change to a draft, then validate/promote without import.
    for root in (manual, assisted):
        draft = root / ".splice-local" / "drafts" / "bundle.draft.yaml"
        draft.write_text(
            draft.read_text(encoding="utf-8").replace(
                "description: Quantifies RNA-seq reads.",
                "description: Quantifies RNA-seq reads per sample.  # edited in vim",
            ),
            encoding="utf-8",
        )
        from nf_splice.layers.inputs import sync_identity
        from nf_splice.layers.provenance import generate_minimal

        sync_identity(root, ADA)
        generate_minimal(root, ADA, at="2026-10-15T10:00:00Z")
        promote(root, None, ADA)
        assert validate_bundle(root).valid
    assert _published(manual) == _published(assisted)


def test_s04_preview_reflects_external_draft_edits(tmp_path: Path) -> None:
    ready_repository(tmp_path)
    draft = tmp_path / ".splice-local" / "drafts" / "outputs.draft.yaml"
    draft.write_text(
        draft.read_text(encoding="utf-8").replace(
            "Job report.", "Job report (edited)."
        ),
        encoding="utf-8",
    )
    assert "Job report (edited)." in preview_outputs(tmp_path, "json")
    assert "Job report (edited)." in preview_outputs(tmp_path, "yaml")
    assert not (tmp_path / "splice" / "outputs.schema.json").exists()


def test_s08_full_workflow_without_ai_or_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", None)

    def no_network(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket, "socket", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    ready_repository(tmp_path)
    promote(tmp_path, None, ADA)
    assert validate_bundle(tmp_path).valid
    publish = tmp_path / "results" / "reports"
    publish.mkdir(parents=True)
    (publish / "report.html").write_text("ok", encoding="utf-8")
    result = generate_analysis_output(
        tmp_path,
        publish_directory=publish.parent,
        job_metadata={"job_id_short": "A001"},
    )
    assert result.validation.valid


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_s09_failures_never_lose_data_or_fake_readiness(tmp_path: Path) -> None:
    ready_repository(tmp_path)
    promote(tmp_path, None, ADA)
    splice = tmp_path / "splice"
    before = _published(tmp_path)

    # Read-only target: publication fails, nothing changes.
    from nf_splice.layers.bundle import set_identity_fields
    from nf_splice.layers.inputs import sync_identity
    from nf_splice.layers.provenance import generate_minimal

    set_identity_fields(tmp_path, {"version": "1.3.0"}, ADA)
    sync_identity(tmp_path, ADA)
    generate_minimal(tmp_path, ADA, at="2026-10-15T11:00:00Z")
    mode = splice.stat().st_mode
    splice.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        with pytest.raises(OSError):
            promote(tmp_path, None, ADA, replace_existing=True)
    finally:
        splice.chmod(mode)
    assert _published(tmp_path) == before
    assert validate_bundle(tmp_path).valid  # previous release still coherent

    # Malformed draft edits are preserved and block, never regenerated.
    draft = tmp_path / ".splice-local" / "drafts" / "outputs.draft.yaml"
    draft.write_text("outputs: [broken\n", encoding="utf-8")
    with pytest.raises(LifecycleError, match="blocked"):
        promote(tmp_path, None, ADA, replace_existing=True)
    assert draft.read_text(encoding="utf-8") == "outputs: [broken\n"
    assert (
        read_yaml(tmp_path, ".splice-local/drafts/outputs.draft.yaml").error is not None
    )

    # Malformed published JSON is reported, not trusted.
    (splice / "components.json").write_text("{not json", encoding="utf-8")
    assert not validate_bundle(tmp_path).valid

    # Malicious draft paths are refused.
    from nf_splice.drafts import replace_file

    for path in (".splice-local/drafts/../../escape", "/tmp/x", "drafts/x"):
        with pytest.raises(DraftStoreError):
            replace_file(tmp_path, path, b"x", expected_sha256=None)


def test_s10_json_consumers_need_only_the_five_contracts(tmp_path: Path) -> None:
    ready_repository(tmp_path)
    promote(tmp_path, None, ADA)
    splice = tmp_path / "splice"
    (splice / "outputs.yaml").unlink()
    bundle = json.loads((splice / "bundle.json").read_text(encoding="utf-8"))
    assert len(bundle["schemas"]) == 5 == len(families())
    documents = {
        uri: json.loads((splice / entry["path"]).read_text(encoding="utf-8"))
        for uri, entry in bundle["schemas"].items()
    }
    inputs = documents["https://schemas.splice-data.io/workflow-bundle/inputs"]
    outputs = documents["https://schemas.splice-data.io/workflow-bundle/outputs"]
    components = documents["https://schemas.splice-data.io/workflow-bundle/components"]
    profiles = documents[
        "https://schemas.splice-data.io/workflow-bundle/execution-profiles"
    ]
    assert bundle["pipeline"]["id"] == inputs["x-splice-pipeline"]["id"]
    assert [item["key"] for item in outputs["x-output-catalog"]["output_types"]] == [
        "report"
    ]
    assert (
        components["containers"][0]["source_images"]["docker"]
        == "quay.io/example/tool:1.0"
    )
    assert profiles["default_profile"] == bundle["default_execution_profile"]
    assert not (splice / "outputs.json").exists()
    assert not (splice / "nf-splice.yaml").exists()
    ro_crate = json.loads(
        (splice / bundle["files"]["ro_crate"]).read_text(encoding="utf-8")
    )
    assert ro_crate["@graph"]
    lock = json.loads((splice / "nf-splice.lock.json").read_text(encoding="utf-8"))
    assert set(lock["contracts"]) == set(bundle["schemas"])
    result = generate_analysis_output(
        tmp_path,
        output_tree=_tree(tmp_path),
        job_metadata={"job_id_short": "A001"},
    )
    assert result.validation.valid


def _tree(root: Path) -> Path:
    path = root / "tree.txt"
    path.write_text(".:\nreports\n\n./reports:\nreport.html\n", encoding="utf-8")
    return path


def test_s13_generated_surfaces_avoid_the_reserved_word(tmp_path: Path) -> None:
    write_pipeline(tmp_path)
    (tmp_path / "nextflow.config").write_text(
        "manifest { name = 'rnaquant' }\n"
        "profiles { local { includeConfig 'conf/local.config' } }\n",
        encoding="utf-8",
    )
    ready_repository_after = tmp_path / "repo"
    ready_repository_after.mkdir()
    ready_repository(ready_repository_after)
    promote(ready_repository_after, None, ADA)
    for path in (ready_repository_after / "splice").rglob("*"):
        if path.is_file():
            assert not reserved_terms_in(path.read_text(encoding="utf-8")), path
    bundle = json.loads((ready_repository_after / "splice" / "bundle.json").read_text())
    assert bundle["schema_id"].endswith("/workflow-bundle/bundle")
    from nf_splice.inspectors import inspect_pipeline_identity

    assert ("name", "rnaquant") in {
        (item.field, item.value) for item in inspect_pipeline_identity(tmp_path).values
    }
