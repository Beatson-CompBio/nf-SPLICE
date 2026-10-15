"""Acceptance tests for reviewed inclusion of a developer-generated RO-Crate."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from nf_splice.renderers import ProvenanceRenderError
from nf_splice.services import (
    ApplicationService,
    StaticChangeKind,
    unresolved_provenance_candidates,
)

runner = CliRunner()


def _repository(root: Path) -> ApplicationService:
    service = ApplicationService()
    service.initialise(
        root,
        name="pipeline",
        version="1.0.0",
        repository_url="https://github.com/org/pipeline",
    )
    return service


def _crate_bytes() -> bytes:
    return (
        b'{\r\n  "@context": "https://w3id.org/ro/crate/1.1/context",\r\n'
        b'  "@graph": [\r\n'
        b'    {"@id":"ro-crate-metadata.json","@type":"CreativeWork",'
        b'"about":{"@id":"./"}},\r\n'
        b'    {"@id":"./","@type":"Dataset","name":"Pipeline"}\r\n'
        b"  ]\r\n}\r\n"
    )


def test_root_ro_crate_requires_review_and_is_copied_byte_for_byte(
    tmp_path: Path,
) -> None:
    service = _repository(tmp_path)
    source = _crate_bytes()
    (tmp_path / "ro-crate-metadata.json").write_bytes(source)
    document = service.discover_provenance(tmp_path)

    assert [item.id for item in unresolved_provenance_candidates(document)] == [
        "provenance:root-ro-crate"
    ]
    with pytest.raises(ProvenanceRenderError, match="not ready"):
        service.plan_provenance(tmp_path)

    service.review_provenance(tmp_path, "provenance:root-ro-crate")
    preview = service.plan_provenance(tmp_path)
    built = service.build_provenance(tmp_path)
    repeated = service.plan_provenance(tmp_path)

    assert preview.change.kind is StaticChangeKind.CREATE
    assert built.wrote
    assert repeated.change.kind is StaticChangeKind.UNCHANGED
    assert (tmp_path / "ro-crate-metadata.json").read_bytes() == source
    assert (tmp_path / "splice" / "ro-crate-metadata.json").read_bytes() == source


def test_invalid_root_ro_crate_is_not_rewritten_or_built(tmp_path: Path) -> None:
    service = _repository(tmp_path)
    source = b'{"@context": "x", "@graph": []}\n'
    (tmp_path / "ro-crate-metadata.json").write_bytes(source)
    service.discover_provenance(tmp_path)
    service.review_provenance(tmp_path, "provenance:root-ro-crate")

    with pytest.raises(ProvenanceRenderError, match="missing required entity"):
        service.plan_provenance(tmp_path)

    assert (tmp_path / "ro-crate-metadata.json").read_bytes() == source
    assert not (tmp_path / "splice" / "ro-crate-metadata.json").exists()
