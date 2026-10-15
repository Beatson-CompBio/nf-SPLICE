"""RO-Crate analysis, reviewed enrichment/generation and source preservation."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from layer_fixtures import ADA, ready_identity
from nf_splice.layers import LayerError
from nf_splice.layers.bundle import set_identity_fields
from nf_splice.layers.provenance import (
    analyse_ro_crate,
    choose_include,
    generate_minimal,
    generate_with_nf_core,
    prepare_enrichment,
    validate_provenance_draft,
)

AT = "2026-10-15T10:00:00Z"


def _crate(version: str = "1.2.0", author: str = "Ada Lovelace") -> dict[str, Any]:
    return {
        "@context": "https://w3id.org/ro/crate/1.1/context",
        "@graph": [
            {
                "@id": "ro-crate-metadata.json",
                "@type": "CreativeWork",
                "about": {"@id": "./"},
                "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"},
            },
            {
                "@id": "./",
                "@type": "Dataset",
                "name": "rnaquant",
                "version": version,
                "description": "Quantifies RNA-seq reads.",
                "mainEntity": {"@id": "main.nf"},
                "creator": [{"@id": "#author"}],
            },
            {
                "@id": "main.nf",
                "@type": ["File", "SoftwareSourceCode", "ComputationalWorkflow"],
                "name": "rnaquant",
                "version": version,
                "url": "https://github.com/org/rnaquant",
            },
            {"@id": "#author", "@type": "Person", "name": author},
        ],
    }


def _write(root: Path, crate: dict[str, Any]) -> bytes:
    payload = (json.dumps(crate, indent=4) + "\n").encode("utf-8")
    (root / "ro-crate-metadata.json").write_bytes(payload)
    (root / "main.nf").write_text("workflow {}\n", encoding="utf-8")
    return payload


def test_current_root_crate_is_included_unchanged(tmp_path: Path) -> None:
    ready_identity(tmp_path)
    payload = _write(tmp_path, _crate())
    assert not analyse_ro_crate(tmp_path).blocking
    choose_include(tmp_path, ADA)
    validation = validate_provenance_draft(tmp_path)
    assert validation.ready, validation.issues
    assert validation.files["ro-crate-metadata.json"] == payload

    (tmp_path / "ro-crate-metadata.json").write_bytes(payload + b" ")
    assert "stale_source" in {
        item.code for item in validate_provenance_draft(tmp_path).errors
    }


def test_stale_crate_blocks_inclusion_and_reviewed_enrichment_is_stable(
    tmp_path: Path,
) -> None:
    ready_identity(tmp_path)
    set_identity_fields(
        tmp_path,
        {"authors": [{"name": "Ada Lovelace"}, {"name": "Grace Hopper"}]},
        ADA,
    )
    payload = _write(tmp_path, _crate(version="1.0.0", author="TODO"))
    analysis = analyse_ro_crate(tmp_path)
    codes = {item.code for item in analysis.findings}
    assert {"stale_value", "placeholder", "missing_author"} <= codes
    stale = next(item for item in analysis.findings if item.code == "stale_value")
    assert (stale.crate_value, stale.reviewed_value) == ("1.0.0", "1.2.0")
    with pytest.raises(LayerError, match="blocking differences"):
        choose_include(tmp_path, ADA)

    prepare_enrichment(tmp_path, ADA, at=AT)
    first = validate_provenance_draft(tmp_path)
    assert first.ready, first.issues
    crate = json.loads(first.files["ro-crate-metadata.json"])
    by_id = {item["@id"]: item for item in crate["@graph"]}
    assert by_id["./"]["version"] == "1.2.0"
    assert by_id["main.nf"]["version"] == "1.2.0"
    assert {"Ada Lovelace", "Grace Hopper"} <= {
        item.get("name") for item in crate["@graph"]
    }
    action = by_id["#nf-splice-enrichment"]
    assert action["endTime"] == AT and action["instrument"] == {"@id": "#nf-splice"}
    assert by_id["#nf-splice"]["version"] == "0.3.0"
    assert (tmp_path / "ro-crate-metadata.json").read_bytes() == payload
    second = validate_provenance_draft(tmp_path)
    assert second.files == first.files


def test_minimal_generation_and_nf_core_adapter(tmp_path: Path) -> None:
    ready_identity(tmp_path)
    (tmp_path / "main.nf").write_text("workflow {}\n", encoding="utf-8")
    assert not analyse_ro_crate(tmp_path).present
    assert (
        "missing_required"
        in {item.code for item in validate_provenance_draft(tmp_path).issues}
        or not validate_provenance_draft(tmp_path).ready
    )
    generate_minimal(tmp_path, ADA, at=AT)
    validation = validate_provenance_draft(tmp_path)
    assert validation.ready, validation.issues
    crate = json.loads(validation.files["ro-crate-metadata.json"])
    descriptor = crate["@graph"][0]
    assert {"@id": "https://w3id.org/workflowhub/workflow-ro-crate/1.0"} in descriptor[
        "conformsTo"
    ]
    assert not (tmp_path / "ro-crate-metadata.json").exists()

    with pytest.raises(LayerError, match="approval"):
        generate_with_nf_core(tmp_path, approve=False)
    calls: list[list[str]] = []

    def runner(command: Sequence[str], cwd: Path) -> int:
        calls.append(list(command))
        (cwd / "ro-crate-metadata.json").write_text(
            json.dumps(_crate()), encoding="utf-8"
        )
        return 0

    generate_with_nf_core(tmp_path, approve=True, runner=runner)
    assert calls == [["nf-core", "pipelines", "rocrate", "."]]
    with pytest.raises(LayerError, match="already exists"):
        generate_with_nf_core(tmp_path, approve=True, runner=runner)


def test_structural_problems_are_reported(tmp_path: Path) -> None:
    ready_identity(tmp_path)
    crate = _crate()
    crate["@graph"].append({"@id": "./", "@type": "Dataset"})
    crate["@graph"][0]["about"] = {"@id": "other"}
    _write(tmp_path, crate)
    codes = {item.code for item in analyse_ro_crate(tmp_path).blocking}
    assert {"duplicate_id", "structure"} <= codes
