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
    add_output,
    discover_outputs,
    preview_outputs,
    set_contract_version,
    update_output,
    validate_outputs_draft,
)

DRAFT = ".splice-local/drafts/outputs.draft.yaml"


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


def test_a_new_catalogue_starts_empty_and_is_authored_in_the_file(
    tmp_path: Path,
) -> None:
    """ADR-0068: no speculative entries and no version taken from the release."""
    ready_identity(tmp_path)
    discovery = discover_outputs(tmp_path)
    assert discovery.created_draft and discovery.notes
    draft = yaml.safe_load((tmp_path / DRAFT).read_text(encoding="utf-8"))
    assert draft["outputs"] == []
    # The analysis-output data version is not the pipeline release (1.2.0).
    assert draft["contract"]["schema_version"] is None
    assert not load_review_state(tmp_path, "outputs").candidates
    validation = validate_outputs_draft(tmp_path)
    issues = {item.pointer: item.code for item in validation.issues}
    assert issues == {
        "/contract/schema_version": "missing_required",
        "/outputs": "missing_required",
    }

    add_output(tmp_path, _output("report", r"^multiqc/multiqc_report\.html$"), ADA)
    set_contract_version(tmp_path, "1.0.0", ADA)
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

    before = (tmp_path / DRAFT).read_bytes()
    rediscovered = discover_outputs(tmp_path)
    assert not rediscovered.created_draft
    assert (tmp_path / DRAFT).read_bytes() == before


def test_a_published_catalogue_seeds_the_draft_with_its_own_version(
    tmp_path: Path,
) -> None:
    ready_identity(tmp_path)
    splice = tmp_path / "splice"
    splice.mkdir()
    (splice / "outputs.yaml").write_text(
        yaml.safe_dump(
            {
                "catalogue_format_version": "0.3.0",
                "analysis_output_schema_version": "2.1.0",
                "outputs": [
                    {
                        "key": "report",
                        "title": "Report",
                        "description": "Job report.",
                        "category": "job_report",
                        "format": "html",
                        "scope": "job",
                        "entity_type": "file",
                        "path_patterns": ["^report\\.html$"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    discover_outputs(tmp_path)
    draft = yaml.safe_load((tmp_path / DRAFT).read_text(encoding="utf-8"))
    assert [item["key"] for item in draft["outputs"]] == ["report"]
    assert draft["contract"]["schema_version"] == "2.1.0"


def test_a_replaced_catalogue_with_undiscovered_outputs_compiles(
    tmp_path: Path,
) -> None:
    ready_identity(tmp_path)
    discover_outputs(tmp_path, schema_version="1.0.0")
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
    # Edits through the service add to the file and keep the author's comments.
    add_output(tmp_path, _output("report", r"^multiqc/multiqc_report\.html$"), ADA)
    after = path.read_text(encoding="utf-8")
    assert "# curated by hand" in after and "key: never_discovered" in after
    assert "key: report" in after

    with pytest.raises(LayerError, match="already defined"):
        add_output(tmp_path, _output("trace", r"^x\.txt$"), ADA)
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


def test_identity_must_be_ready_before_outputs_compile(tmp_path: Path) -> None:
    discover_outputs(tmp_path, schema_version="1.0.0")
    assert "identity_not_ready" in _codes(tmp_path)
