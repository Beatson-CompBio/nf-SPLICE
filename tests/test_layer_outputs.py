"""Single authoritative outputs.draft.yaml compiling to both output files."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from layer_fixtures import ADA, ready_identity
from nf_splice.layers import LayerError
from nf_splice.layers.base import load_review_state
from nf_splice.layers.outputs import (
    accept_output,
    apply_decision_file,
    discover_outputs,
    merge_outputs,
    pending_candidates,
    preview_outputs,
    split_output,
    update_output,
    validate_outputs_draft,
)

DRAFT = ".splice-local/drafts/outputs.draft.yaml"


def _tree(root: Path) -> Path:
    tree = root / "example-tree"
    for relative in (
        "multiqc/multiqc_report.html",
        "quant/S1/counts.tsv",
        "quant/S2/counts.tsv",
        "pipeline_info/trace.txt",
    ):
        path = tree / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")
    return tree


def _output(key: str, pattern: str, scope: str = "job", category: str = "job_report"):  # type: ignore[no-untyped-def]
    return {
        "key": key,
        "title": key.replace("_", " ").title(),
        "description": f"{key} description.",
        "category": category,
        "formats": ["html" if pattern.endswith(r"\.html$") else "tsv"],
        "scopes": [scope],
        "entity_types": ["file"],
        "path_patterns": [pattern],
    }


def _codes(root: Path) -> set[str]:
    return {item.code for item in validate_outputs_draft(root).issues}


def _candidate_ids(root: Path) -> list[str]:
    return sorted(load_review_state(root, "outputs").candidates)


def _clear_catalogue(root: Path) -> None:
    from layer_fixtures import edit_draft_file

    def clear(data: dict) -> None:  # type: ignore[type-arg]
        data["outputs"] = []
        data["categories"] = {}

    edit_draft_file(root, "outputs", clear)


def test_discovery_seeds_a_useful_catalogue_finished_by_editing_the_file(
    tmp_path: Path,
) -> None:
    ready_identity(tmp_path)
    discovery = discover_outputs(tmp_path, example_output_tree=_tree(tmp_path))
    assert discovery.created_draft and discovery.notes
    draft = yaml.safe_load((tmp_path / DRAFT).read_text(encoding="utf-8"))
    by_pattern = {item["path_patterns"][0]: item for item in draft["outputs"]}
    # Seeded, not empty: every observed output is an editable entry.
    assert set(by_pattern) == {
        r"^multiqc/multiqc_report\.html$",
        r"^quant/{sample}/counts\.tsv$",
        r"^pipeline_info/trace\.txt$",
    }
    counts = by_pattern[r"^quant/{sample}/counts\.tsv$"]
    # The category is the pipeline's own directory; nf-splice prescribes none.
    assert counts["scopes"] == ["sample"] and counts["category"] == "quant"
    # The contract version comes from the identity (X.Y.Z), unknowns stay empty.
    assert draft["contract"]["schema_version"] == "1.2.0"
    assert discovery.pending == ()
    codes = _codes(tmp_path)
    assert "pending_candidate" not in codes
    assert codes == {"unresolved"}  # descriptions nobody can know from a tree

    text = (tmp_path / DRAFT).read_text(encoding="utf-8")
    text = text.replace("description: null", "description: Written by the author.", 3)
    (tmp_path / DRAFT).write_text(text, encoding="utf-8")
    validation = validate_outputs_draft(tmp_path)
    assert validation.ready, validation.issues
    assert sorted(validation.files) == ["outputs.schema.json", "outputs.yaml"]
    schema = json.loads(validation.files["outputs.schema.json"])
    catalogue = yaml.safe_load(validation.files["outputs.yaml"])
    assert catalogue["outputs"] == schema["x-output-catalog"]["output_types"]
    assert validate_outputs_draft(tmp_path).files == validation.files
    assert json.loads(preview_outputs(tmp_path))["$id"] == schema["$id"]
    written = sorted(
        path.name for path in (tmp_path / "splice").rglob("*") if path.is_file()
    )
    assert "outputs.schema.json" not in written  # preview never writes
    # No candidate decision was recorded: the authored file is the decision.
    statuses = {
        entry["status"]
        for entry in load_review_state(tmp_path, "outputs").candidates.values()
    }
    assert statuses == {"seeded"}

    before = (tmp_path / DRAFT).read_bytes()
    rediscovered = discover_outputs(tmp_path, example_output_tree=_tree(tmp_path))
    assert not rediscovered.created_draft and rediscovered.pending == ()
    assert (tmp_path / DRAFT).read_bytes() == before


def test_a_replaced_catalogue_with_undiscovered_outputs_compiles(
    tmp_path: Path,
) -> None:
    ready_identity(tmp_path)
    discover_outputs(
        tmp_path, example_output_tree=_tree(tmp_path), schema_version="1.0.0"
    )
    path = tmp_path / DRAFT
    head = path.read_text(encoding="utf-8").split("outputs:", 1)[0]
    path.write_text(
        head.replace("categories: {}", "categories:\n  Run diagnostics: {}")
        + "outputs:  # curated by hand\n"
        "  - key: trace\n"
        "    title: Trace\n"
        "    description: Engine trace.\n"
        "    category: Run diagnostics\n"
        "    formats: [txt]\n"
        "    scopes: [job]\n"
        "    entity_types: [file]\n"
        "    path_patterns: ['^pipeline_info/trace\\.txt$']\n"
        "  - key: never_discovered\n"
        "    title: Sample summary\n"
        "    description: A per-sample summary discovery never saw.\n"
        "    category: summaries\n"
        "    formats: [json]\n"
        "    scopes: [sample]\n"
        "    entity_types: [file]\n"
        "    path_patterns: ['^summary/{sample}\\.json$']\n"
        "excluded_routes: []\n",
        encoding="utf-8",
    )
    assert validate_outputs_draft(tmp_path).ready
    # Optional tool reviews add to the file and keep the author's comments.
    candidate = _candidate_ids(tmp_path)[0]
    accept_output(
        tmp_path, candidate, _output("report", r"^multiqc/multiqc_report\.html$"), ADA
    )
    after = path.read_text(encoding="utf-8")
    assert "# curated by hand" in after and "key: never_discovered" in after
    assert "key: report" in after

    with pytest.raises(LayerError, match="already defined"):
        accept_output(tmp_path, candidate, _output("trace", r"^x\.txt$"), ADA)
    with pytest.raises(LayerError, match="unknown output candidate"):
        accept_output(tmp_path, "output:invented", _output("y", r"^y\.txt$"), ADA)
    with pytest.raises(LayerError, match="invalid reviewed output"):
        update_output(tmp_path, "trace", {"scopes": ["sample"]}, ADA)

    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "scopes: [job]", "scopes: [library]", 1
        ),
        encoding="utf-8",
    )
    pointers = {
        item.pointer
        for item in validate_outputs_draft(tmp_path).issues
        if item.code == "invalid_value"
    }
    assert any(pointer.startswith("/outputs/0/scopes") for pointer in pointers)


def test_optional_merge_split_and_decision_files(tmp_path: Path) -> None:
    ready_identity(tmp_path)
    tree = _tree(tmp_path)
    (tree / "multiqc" / "extra.txt").write_text("x", encoding="utf-8")
    discover_outputs(tmp_path, example_output_tree=tree)
    _clear_catalogue(tmp_path)
    ids = _candidate_ids(tmp_path)
    assert len(ids) == 4
    merge_outputs(tmp_path, ids[:2], _output("combined", r"^multiqc/.+\.html$"), ADA)
    split_output(
        tmp_path,
        ids[2],
        [
            _output("first", r"^quant/{sample}/counts\.tsv$", "sample"),
            _output("second", r"^quant/{sample}/other\.tsv$", "sample"),
        ],
        ADA,
    )
    apply_decision_file(
        tmp_path,
        {
            "actions": [
                {"action": "reject", "candidate_id": ids[3], "reason": "Not needed"},
                {"action": "version", "schema_version": "2.0.0"},
            ]
        },
        ADA,
    )
    assert pending_candidates(tmp_path) == ()
    candidates = load_review_state(tmp_path, "outputs").candidates
    assert candidates[ids[1]]["status"] == "merged"
    assert candidates[ids[1]]["merged_into"] == ids[0]
    assert candidates[ids[2]]["output_keys"] == ["first", "second"]
    assert validate_outputs_draft(tmp_path).ready
    with pytest.raises(LayerError, match="at least two"):
        merge_outputs(tmp_path, ids[:1], _output("x", r"^x\.html$"), ADA)


def test_identity_must_be_ready_before_outputs_compile(tmp_path: Path) -> None:
    discover_outputs(tmp_path, schema_version="1.0.0")
    assert "identity_not_ready" in _codes(tmp_path)
