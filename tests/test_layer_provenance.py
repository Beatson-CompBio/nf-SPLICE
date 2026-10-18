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
    crate_origin,
    generate_minimal,
    generate_with_nf_core,
    prepare_enrichment,
    seed_provenance,
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


def _published(root: Path) -> dict[str, Any]:
    validation = validate_provenance_draft(root)
    assert validation.ready, validation.issues
    loaded: dict[str, Any] = json.loads(validation.files["ro-crate-metadata.json"])
    return loaded


def test_root_crate_is_adopted_as_a_copy_and_published_with_bundle_entities(
    tmp_path: Path,
) -> None:
    ready_identity(tmp_path)
    payload = _write(tmp_path, _crate())
    assert not analyse_ro_crate(tmp_path).blocking
    assert seed_provenance(tmp_path)
    assert crate_origin(tmp_path) == "adopted"
    crate = _published(tmp_path)
    by_id = {item["@id"]: item for item in crate["@graph"]}
    # The authored graph is kept; nf-splice adds the bundle, without hashes.
    assert by_id["./"]["name"] == "rnaquant"
    assert {"@id": "splice/"} in by_id["./"]["hasPart"]
    bundle = by_id["splice/"]
    assert bundle["@type"] == "Dataset" and bundle["about"] == {"@id": "main.nf"}
    parts = {item["@id"] for item in bundle["hasPart"]}
    assert {"splice/bundle.json", "splice/inputs.schema.json"} <= parts
    assert "splice/ro-crate-metadata.json" not in parts
    assert all("sha256" not in by_id[item] for item in parts)
    assert (tmp_path / "ro-crate-metadata.json").read_bytes() == payload
    assert (
        validate_provenance_draft(tmp_path).files
        == validate_provenance_draft(tmp_path).files
    )

    # A later change to the developer's file is reported, never applied.
    (tmp_path / "ro-crate-metadata.json").write_bytes(payload + b" ")
    issues = validate_provenance_draft(tmp_path).issues
    assert {"source_changed"} == {
        item.code for item in issues if item.code == "source_changed"
    }
    assert validate_provenance_draft(tmp_path).ready


def test_stale_crate_is_reported_and_reviewed_enrichment_is_stable(
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
    # The adopted copy is not accepted as current while it disagrees.
    seed_provenance(tmp_path)
    assert "stale_value" in {
        item.code for item in validate_provenance_draft(tmp_path).errors
    }

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


def test_missing_crate_is_generated_from_identity_and_edited_by_hand(
    tmp_path: Path,
) -> None:
    from layer_fixtures import edit_draft_file

    ready_identity(tmp_path)
    (tmp_path / "main.nf").write_text("workflow {}\n", encoding="utf-8")
    assert not analyse_ro_crate(tmp_path).present
    seed_provenance(tmp_path)
    assert crate_origin(tmp_path) == "generated"
    crate = _published(tmp_path)
    descriptor = crate["@graph"][0]
    assert {"@id": "https://w3id.org/workflowhub/workflow-ro-crate/1.0"} in descriptor[
        "conformsTo"
    ]
    assert not (tmp_path / "ro-crate-metadata.json").exists()
    assert not any("nf-co.re" in json.dumps(item) for item in crate["@graph"])

    def add_author(data: dict[str, Any]) -> None:
        graph = data["crate"]["@graph"]
        graph.append({"@id": "#grace", "@type": "Person", "name": "Grace Hopper"})
        root = next(item for item in graph if item["@id"] == "./")
        root["creator"] = [{"@id": "#grace"}]
        data["origin"] = "authored"

    edit_draft_file(tmp_path, "provenance", add_author)
    edited = _published(tmp_path)
    assert "Grace Hopper" in {item.get("name") for item in edited["@graph"]}
    generate_minimal(tmp_path, ADA, at=AT)
    assert _published(tmp_path)["@graph"][0] == descriptor


def test_nf_core_generator_runs_on_an_isolated_copy(tmp_path: Path) -> None:
    ready_identity(tmp_path)
    (tmp_path / "main.nf").write_text("workflow {}\n", encoding="utf-8")
    (tmp_path / "nextflow.config").write_text(
        "manifest { name = 'org/rnaquant' }\n", encoding="utf-8"
    )
    seed_provenance(tmp_path)
    with pytest.raises(LayerError, match="approval"):
        generate_with_nf_core(tmp_path, ADA, approve=False)
    calls: list[tuple[list[str], Path, dict[str, str]]] = []

    def runner(
        command: Sequence[str], cwd: Path, environment: Any, _timeout: float
    ) -> tuple[int, str]:
        calls.append((list(command), cwd, dict(environment)))
        if command[1:] == ["--version"]:
            return 0, "nf-core, version 4.0.2"
        generated = _crate()
        generated["@graph"][1]["url"] = "https://nf-co.re/rnaquant"
        Path(command[command.index("--json_path") + 1]).write_text(
            json.dumps(generated), encoding="utf-8"
        )
        return 0, "done"

    run = generate_with_nf_core(tmp_path, ADA, approve=True, runner=runner)
    command, _cwd, environment = calls[-1]
    copy = Path(command[3])
    assert (
        command[1:3] == ["pipelines", "rocrate"] and "--pipeline_version" not in command
    )
    assert tmp_path / ".splice-local" in copy.parents and copy != tmp_path
    assert environment["NFCORE_NO_VERSION_CHECK"] == "1"
    assert run.version == "4.0.2"
    assert "./.url" in run.removed_claims  # not an nf-core pipeline
    assert not (tmp_path / "ro-crate-metadata.json").exists()
    assert not (tmp_path / ".splice-local" / "tmp" / "nf-core-rocrate").exists()
    assert crate_origin(tmp_path) == "nf-core"
    crate = _published(tmp_path)
    assert "nf-co.re" not in json.dumps(crate)

    before = (tmp_path / ".splice-local/drafts/provenance.draft.yaml").read_bytes()

    def failing(
        command: Sequence[str], cwd: Path, environment: Any, _timeout: float
    ) -> tuple[int, str]:
        return (0, "nf-core, version 4.0.2") if "--version" in command else (1, "x")

    with pytest.raises(LayerError, match="draft is unchanged"):
        generate_with_nf_core(tmp_path, ADA, approve=True, runner=failing)
    after = (tmp_path / ".splice-local/drafts/provenance.draft.yaml").read_bytes()
    assert after == before


def test_structural_problems_are_reported(tmp_path: Path) -> None:
    ready_identity(tmp_path)
    crate = _crate()
    crate["@graph"].append({"@id": "./", "@type": "Dataset"})
    crate["@graph"][0]["about"] = {"@id": "other"}
    _write(tmp_path, crate)
    codes = {item.code for item in analyse_ro_crate(tmp_path).blocking}
    assert {"duplicate_id", "structure"} <= codes


def test_a_json_ld_array_with_the_reviewed_value_is_not_stale() -> None:
    """JSON-LD allows any property to be an array: ['3.27.0'] is '3.27.0'."""
    from nf_splice.domain.identity import PipelineMetadata
    from nf_splice.layers.provenance import identity_findings

    metadata = PipelineMetadata.model_construct(
        name="pipe",
        version="3.27.0",
        description=None,
        licence=None,
        licence_url=None,
        repository_url=None,
        authors=(),
    )
    crate = {
        "@graph": [
            {"@id": "./", "@type": "Dataset", "mainEntity": {"@id": "main.nf"}},
            {"@id": "main.nf", "version": ["3.27.0"]},
        ]
    }
    codes = {item.code for item in identity_findings(crate, metadata)}
    assert "stale_value" not in codes
    crate["@graph"][1]["version"] = ["3.26.0", "3.27.0"]
    assert "stale_value" in {item.code for item in identity_findings(crate, metadata)}
