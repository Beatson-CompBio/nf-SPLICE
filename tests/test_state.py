"""Acceptance tests for canonical state placement and legacy reconciliation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nf_splice.domain import (
    AuthoringDocument,
    LegacyStateClassification,
    PathClassification,
    PipelineIdentity,
    dump_authoring_document,
)
from nf_splice.inspectors import inspect_repository, inspect_splice_tree
from nf_splice.services import (
    ApplicationService,
    MigrationChangeKind,
    StateMigrationError,
)


def _document() -> str:
    return dump_authoring_document(
        AuthoringDocument(
            pipeline=PipelineIdentity(
                name="pipeline",
                version="1.0.0",
                repository_url="https://github.com/org/pipeline",
            )
        )
    )


def test_initialisation_creates_and_inspection_recognizes_control_files(
    tmp_path: Path,
) -> None:
    (tmp_path / "splice").mkdir()
    (tmp_path / "splice" / "nf-splice.yaml").write_text(_document(), encoding="utf-8")
    lock = tmp_path / "splice" / "nf-splice.lock.json"
    lock.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "generator": {"name": "nf-splice", "version": "0.1.0"},
                "repository": {
                    "url": "https://github.com/org/pipeline",
                    "revision": None,
                },
                "selected_evidence": [],
                "sources": {},
                "managed_files": {},
            }
        ),
        encoding="utf-8",
    )

    result = inspect_splice_tree(tmp_path)
    paths = {item.path: item for item in result.paths}

    assert paths["nf-splice.yaml"].classification is PathClassification.RECOGNIZED
    assert paths["nf-splice.lock.json"].classification is PathClassification.RECOGNIZED
    assert result.collisions == ()


def test_lock_inspection_rejects_invalid_hash_inventory(tmp_path: Path) -> None:
    splice = tmp_path / "splice"
    splice.mkdir()
    (splice / "nf-splice.lock.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "generator": {"name": "nf-splice", "version": "0.1.0"},
                "repository": {
                    "url": "https://github.com/org/pipeline",
                    "revision": None,
                },
                "selected_evidence": [],
                "sources": {"nf-splice.yaml": {"sha256": "not-a-hash"}},
                "managed_files": {},
            }
        ),
        encoding="utf-8",
    )

    lock = inspect_splice_tree(tmp_path).paths[0]

    assert lock.classification is PathClassification.MALFORMED
    assert "lowercase SHA-256" in (lock.detail or "")


def test_legacy_migration_is_previewed_atomic_non_destructive_and_idempotent(
    tmp_path: Path,
) -> None:
    source = tmp_path / "nf-splice.yaml"
    source.write_text(_document(), encoding="utf-8")
    original = source.read_bytes()
    service = ApplicationService()

    preview = service.plan_state_migration(tmp_path)

    assert preview.wrote is False
    assert preview.changes[0].kind is MigrationChangeKind.CREATE
    assert not (tmp_path / "splice").exists()

    applied = service.apply_state_migration(tmp_path)
    repeated = service.apply_state_migration(tmp_path)

    destination = tmp_path / "splice" / "nf-splice.yaml"
    assert applied.wrote is True
    assert source.read_bytes() == original
    assert destination.read_bytes() == original
    assert repeated.wrote is False
    assert repeated.changes[0].kind is MigrationChangeKind.UNCHANGED


@pytest.mark.parametrize(
    "content",
    ["not: [valid", "schema_version: '99'\n"],
)
def test_malformed_or_incompatible_legacy_authoring_blocks_without_mutation(
    tmp_path: Path, content: str
) -> None:
    (tmp_path / "nf-splice.yaml").write_text(content, encoding="utf-8")
    before = (tmp_path / "nf-splice.yaml").read_bytes()

    with pytest.raises(StateMigrationError):
        ApplicationService().apply_state_migration(tmp_path)

    inspected = inspect_repository(tmp_path).legacy_state[0]
    assert inspected.classification in {
        LegacyStateClassification.MALFORMED,
        LegacyStateClassification.INCOMPATIBLE,
    }
    assert (tmp_path / "nf-splice.yaml").read_bytes() == before
    assert not (tmp_path / "splice").exists()


def test_differing_destination_blocks_legacy_migration(tmp_path: Path) -> None:
    (tmp_path / "nf-splice.yaml").write_text(_document(), encoding="utf-8")
    (tmp_path / "splice").mkdir()
    destination = tmp_path / "splice" / "nf-splice.yaml"
    destination.write_text(
        _document().replace("pipeline", "other-pipeline"), encoding="utf-8"
    )
    before = destination.read_bytes()

    with pytest.raises(StateMigrationError, match="conflicts"):
        ApplicationService().apply_state_migration(tmp_path)

    assert destination.read_bytes() == before
