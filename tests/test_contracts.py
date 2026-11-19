"""Five workflow-bundle contract families, release registry and validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from typer.testing import CliRunner

from nf_splice import __version__
from nf_splice.cli import app
from nf_splice.contracts import (
    BUNDLE_FAMILY,
    FAMILY_IDS,
    ContractRegistryError,
    breaking_changes,
    contract_extension,
    data_document_header,
    families,
    family,
    meta_schema,
    release,
    releases,
    validate_contract_document,
)

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs" / "schemas"
runner = CliRunner()

EXPECTED = {
    "bundle.json": "https://schemas.splice-data.io/workflow-bundle/bundle",
    "inputs.schema.json": "https://schemas.splice-data.io/workflow-bundle/inputs",
    "outputs.schema.json": "https://schemas.splice-data.io/workflow-bundle/outputs",
    "components.json": "https://schemas.splice-data.io/workflow-bundle/components",
    "execution-profiles.json": (
        "https://schemas.splice-data.io/workflow-bundle/execution-profiles"
    ),
}


def _example(key: str) -> dict[str, object]:
    loaded: dict[str, object] = json.loads(
        (DOCS / key / "v0.3.0" / "example.json").read_text(encoding="utf-8")
    )
    return loaded


def test_registry_enumerates_exactly_five_engine_neutral_families() -> None:
    assert {item.path: item.id for item in families()} == EXPECTED
    assert BUNDLE_FAMILY == "https://schemas.splice-data.io/workflow-bundle/bundle"
    for identifier in FAMILY_IDS:
        lowered = identifier.lower()
        assert "nextflow" not in lowered
        assert "nf-splice" not in lowered
        assert "manifest" not in lowered
        assert not identifier.startswith("splice.")


def test_every_tool_release_has_an_explicit_mapping() -> None:
    assert __version__ == "0.3.0"
    versions = [item.tool_version for item in releases()]
    assert versions == ["0.3.0"]
    assert dict(release().contracts) == dict.fromkeys(FAMILY_IDS, "0.3.0")
    with pytest.raises(ContractRegistryError, match=r"0\.2\.0"):
        release("0.2.0")


def test_packaged_definitions_are_valid_and_mirrored_in_docs() -> None:
    for item in families():
        definition = meta_schema(item.id)
        Draft202012Validator.check_schema(definition)
        assert definition["$id"] == f"{item.id}/v0.3.0/schema.json"
        mirrored = json.loads(
            (DOCS / item.key / "v0.3.0" / "schema.json").read_text(encoding="utf-8")
        )
        assert mirrored == definition


@pytest.mark.parametrize("key", [item.key for item in families()])
def test_documented_examples_validate_offline(key: str) -> None:
    report = validate_contract_document(_example(key))
    assert report.valid, report.issues
    assert report.family_id == family(key).id
    assert report.revision == "0.3.0"


def test_contract_metadata_never_abuses_json_schema_identity() -> None:
    inputs = _example("inputs")
    assert inputs["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert inputs["$id"] != family("inputs").id
    assert contract_extension("outputs") == {
        "id": family("outputs").id,
        "version": "0.3.0",
        "generated_by": {"name": "nf-splice", "version": "0.3.0"},
    }
    assert data_document_header("components")["schema_id"] == family("components").id


def test_undeclared_and_future_documents_fail_explicitly() -> None:
    undeclared = {
        key: value
        for key, value in _example("bundle").items()
        if key not in {"schema_id", "schema_version"}
    }
    report = validate_contract_document(undeclared, filename="bundle.json")
    assert not report.valid
    assert report.issues[0].rule == "declaration"

    future = _example("bundle") | {"schema_version": "9.0.0"}
    report = validate_contract_document(future)
    assert [item.rule for item in report.issues] == ["unsupported_revision"]


def test_inputs_contract_is_validated_as_a_schema_and_for_extensions() -> None:
    broken = _example("inputs")
    broken["type"] = 7
    report = validate_contract_document(broken)
    assert {item.rule for item in report.issues} >= {"schema"}

    missing_access = json.loads(json.dumps(_example("inputs")))
    del missing_access["$defs"]["input_output_options"]["properties"]["outdir"][
        "x-splice-access"
    ]
    report = validate_contract_document(missing_access)
    assert not report.valid
    assert any("x-splice-access" in item.message for item in report.issues)


def test_breaking_change_detection() -> None:
    old = meta_schema("execution-profiles")
    assert breaking_changes(old, old) == ()
    narrowed = json.loads(json.dumps(old))
    narrowed["$defs"]["profile"]["properties"]["type"]["enum"].remove("test")
    narrowed["required"].append("default_profile")
    del narrowed["properties"]["pipeline"]
    kinds = {item.kind for item in breaking_changes(old, narrowed)}
    assert kinds == {"enum_narrowed", "required_added", "property_removed"}


def test_schema_cli_lists_shows_validates_and_checks(tmp_path: Path) -> None:
    listed = runner.invoke(app, ["schema", "list", "--json"])
    assert listed.exit_code == 0, listed.output
    payload = json.loads(listed.output)
    assert payload["tool_version"] == "0.3.0"
    assert [item["id"] for item in payload["families"]] == list(FAMILY_IDS)
    assert {item["version"] for item in payload["families"]} == {"0.3.0"}

    shown = runner.invoke(app, ["schema", "show", "bundle"])
    assert json.loads(shown.output)["$id"].startswith(BUNDLE_FAMILY)
    assert runner.invoke(app, ["schema", "show", "nope"]).exit_code == 2

    example = DOCS / "components" / "v0.3.0" / "example.json"
    valid = runner.invoke(app, ["schema", "validate", str(example), "--json"])
    assert valid.exit_code == 0, valid.output
    undeclared = tmp_path / "components.json"
    undeclared.write_text('{"containers": [], "components": []}', encoding="utf-8")
    assert runner.invoke(app, ["schema", "validate", str(undeclared)]).exit_code == 2

    splice = tmp_path / "splice"
    splice.mkdir()
    for item in families():
        (splice / item.path).write_text(
            json.dumps(_example(item.key)), encoding="utf-8"
        )
    checked = runner.invoke(
        app, ["schema", "check", "--repository", str(tmp_path), "--json"]
    )
    assert checked.exit_code == 0, checked.output
    (splice / "components.json").unlink()
    assert (
        runner.invoke(app, ["schema", "check", "--repository", str(tmp_path)]).exit_code
        == 2
    )

    old = tmp_path / "old.json"
    widened = json.loads(json.dumps(meta_schema("bundle")))
    widened["properties"]["pipeline"]["properties"]["engine"]["enum"].append("other")
    old.write_text(json.dumps(widened), encoding="utf-8")
    compared = runner.invoke(
        app, ["schema", "check", "--against", str(old), "--family", "bundle"]
    )
    assert compared.exit_code == 2
    assert "enum_narrowed" in compared.output
