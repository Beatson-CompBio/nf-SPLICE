"""Inspection of the published lock file in an existing splice/ tree."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from nf_splice.contracts import families
from nf_splice.domain import PathClassification
from nf_splice.inspectors import inspect_splice_tree


def _lock(**overrides: Any) -> str:
    document: dict[str, Any] = {
        "schema_version": "2.0",
        "generator": {"name": "nf-splice", "version": "0.3.0"},
        "repository": {"url": "https://github.com/org/pipeline", "revision": None},
        "contracts": {item.id: "0.3.0" for item in families()},
        "sources": {},
        "managed_files": {},
    }
    return json.dumps(document | overrides)


def _inspect(tmp_path: Path, content: str) -> tuple[PathClassification, str | None]:
    splice = tmp_path / "splice"
    splice.mkdir()
    (splice / "nf-splice.lock.json").write_text(content, encoding="utf-8")
    result = inspect_splice_tree(tmp_path)
    lock = {item.path: item for item in result.paths}["nf-splice.lock.json"]
    return lock.classification, lock.detail


def test_lock_file_is_recognised(tmp_path: Path) -> None:
    classification, detail = _inspect(tmp_path, _lock())
    assert classification is PathClassification.RECOGNIZED, detail
    assert inspect_splice_tree(tmp_path).collisions == ()


def test_lock_inspection_rejects_invalid_hash_inventory(tmp_path: Path) -> None:
    content = _lock(sources={"nextflow_schema.json": {"sha256": "not-a-hash"}})
    classification, detail = _inspect(tmp_path, content)
    assert classification is PathClassification.MALFORMED
    assert "lowercase SHA-256" in (detail or "")


def test_unsupported_lock_format_is_reported(tmp_path: Path) -> None:
    classification, detail = _inspect(tmp_path, _lock(schema_version="1.0"))
    assert classification is PathClassification.MALFORMED
    assert "expected '2.0'" in (detail or "")
