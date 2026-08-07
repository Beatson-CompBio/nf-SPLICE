"""Acceptance tests for read-only repository and integration-tree inspection."""

from __future__ import annotations

import json
from pathlib import Path

from nf_splice.domain import EvidenceKind, PathClassification, TreeState
from nf_splice.inspectors import inspect_repository, inspect_splice_tree


def _snapshot(root: Path) -> dict[str, bytes | None]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes() if path.is_file() else None
        for path in sorted(root.rglob("*"))
    }


def _write_json(path: Path, content: object) -> None:
    path.write_text(json.dumps(content), encoding="utf-8")


def test_absent_and_empty_splice_trees_are_distinct(tmp_path: Path) -> None:
    assert inspect_splice_tree(tmp_path).state is TreeState.ABSENT

    (tmp_path / "splice").mkdir()

    assert inspect_splice_tree(tmp_path).state is TreeState.EMPTY


def test_recognized_tree_uses_the_approved_bundle_shape(tmp_path: Path) -> None:
    splice = tmp_path / "splice"
    configs = splice / "configs"
    configs.mkdir(parents=True)
    (configs / "local.config").write_text("process.executor = 'local'\n")
    _write_json(
        splice / "bundle.json",
        {
            "bundle_format": "splice-pipeline-bundle",
            "schema_version": "1.0",
            "pipeline": {},
            "files": {},
        },
    )

    result = inspect_splice_tree(tmp_path)

    assert result.state is TreeState.RECOGNIZED
    assert {item.path for item in result.paths} == {
        "bundle.json",
        "configs",
        "configs/local.config",
    }
    assert {collision.path for collision in result.collisions} == {
        "splice/bundle.json",
        "splice/configs/local.config",
    }


def test_malformed_and_unknown_content_are_reported_per_path(
    tmp_path: Path,
) -> None:
    splice = tmp_path / "splice"
    splice.mkdir()
    (splice / "outputs.yaml").write_text("outputs: not-a-list\n")
    (splice / "notes.txt").write_text("preserve me\n")

    result = inspect_splice_tree(tmp_path)
    paths = {item.path: item for item in result.paths}

    assert result.state is TreeState.MIXED
    assert paths["outputs.yaml"].classification is PathClassification.MALFORMED
    assert paths["notes.txt"].classification is PathClassification.UNKNOWN
    assert result.collisions[0].path == "splice/outputs.yaml"
    assert result.collisions[0].affected_layers == ("outputs",)
    assert "missing required keys" in (paths["outputs.yaml"].detail or "")


def test_unknown_top_level_content_is_preserved_without_blocking_other_layers(
    tmp_path: Path,
) -> None:
    splice = tmp_path / "splice"
    splice.mkdir()
    (splice / "developer-notes.txt").write_text("keep\n")

    result = inspect_splice_tree(tmp_path)

    assert result.state is TreeState.UNKNOWN
    assert result.collisions == ()


def test_unknown_content_inside_generated_directory_has_an_exact_collision(
    tmp_path: Path,
) -> None:
    custom = tmp_path / "splice" / "configs" / "custom"
    custom.mkdir(parents=True)
    (custom / "notes.txt").write_text("keep\n")

    result = inspect_splice_tree(tmp_path)

    assert [collision.path for collision in result.collisions] == [
        "splice/configs/custom/notes.txt"
    ]
    assert result.collisions[0].affected_layers == ("execution_profiles",)


def test_repository_inspection_collects_pipeline_and_git_ready_evidence(
    tmp_path: Path,
) -> None:
    (tmp_path / "conf").mkdir()
    (tmp_path / "modules" / "tool").mkdir(parents=True)
    (tmp_path / "nextflow.config").write_text(
        "includeConfig 'conf/base.config'\n",
        encoding="utf-8",
    )
    (tmp_path / "conf" / "base.config").write_text(
        "process.executor = 'local'\n",
        encoding="utf-8",
    )
    (tmp_path / "main.nf").write_text(
        """workflow {
    output {
        reports = REPORT.out
    }
}
process REPORT {
    container 'quay.io/example/report:1.0'
    conda 'bioconda::example=1.0'
    publishDir "${params.outdir}/reports"
}
""",
        encoding="utf-8",
    )
    (tmp_path / "modules" / "tool" / "main.nf").write_text(
        "process TOOL {}\n", encoding="utf-8"
    )
    (tmp_path / "modules" / "tool" / "meta.yml").write_text(
        "name: tool\noutput: []\n", encoding="utf-8"
    )
    _write_json(tmp_path / "nextflow_schema.json", {"type": "object"})
    _write_json(tmp_path / "modules.json", {"repos": {}})
    _write_json(tmp_path / "ro-crate-metadata.json", {"@graph": []})

    before = _snapshot(tmp_path)
    result = inspect_repository(tmp_path)
    after = _snapshot(tmp_path)
    kinds = {item.kind for item in result.evidence}

    assert before == after
    assert result.splice_tree.state is TreeState.ABSENT
    assert {
        EvidenceKind.PIPELINE_CONFIG,
        EvidenceKind.INCLUDED_CONFIG,
        EvidenceKind.INPUT_SCHEMA,
        EvidenceKind.NEXTFLOW_SOURCE,
        EvidenceKind.WORKFLOW,
        EvidenceKind.MODULE,
        EvidenceKind.NATIVE_OUTPUT,
        EvidenceKind.PUBLISHED_OUTPUT,
        EvidenceKind.MODULE_INDEX,
        EvidenceKind.MODULE_METADATA,
        EvidenceKind.CONTAINER,
        EvidenceKind.CONDA_ENVIRONMENT,
        EvidenceKind.RO_CRATE,
    }.issubset(kinds)


def test_inspection_never_changes_an_existing_tree(tmp_path: Path) -> None:
    splice = tmp_path / "splice"
    splice.mkdir()
    (splice / "outputs.yaml").write_text(
        "schema_version: '1.0'\npipeline: {}\noutputs: []\n",
        encoding="utf-8",
    )
    (splice / "unknown.bin").write_bytes(b"\x00\x01")
    before = _snapshot(tmp_path)

    inspect_repository(tmp_path)

    assert _snapshot(tmp_path) == before
