"""SPLICE-owned input contract: lossless nf-schema import and policies."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from layer_fixtures import ADA, ready_identity
from nf_splice.domain import Actor, ChangeOrigin
from nf_splice.domain.access import Principal
from nf_splice.layers import ChangeContext, LayerError
from nf_splice.layers.bundle import set_identity_fields
from nf_splice.layers.inputs import (
    apply_reimport,
    import_inputs,
    iter_parameters,
    plan_reimport,
    set_access,
    sync_identity,
    update_parameter,
    validate_inputs_draft,
)
from nf_splice.services.input_policy import (
    authorise_changes,
    engine_parameters,
    form_fields,
    validate_submission,
)

FIXTURE = Path(__file__).parent / "fixtures" / "nf-schema" / "nextflow_schema.json"
DRAFT = "splice/drafts/inputs.schema.draft.yaml"
AGENT = ChangeContext(
    actor=Actor(label="assistant"), origin=ChangeOrigin.AGENT_ASSISTED
)


def _repository(root: Path) -> dict[str, Any]:
    ready_identity(root)
    shutil.copy(FIXTURE, root / "nextflow_schema.json")
    assert import_inputs(root)
    upstream: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return upstream


def _review_all(root: Path) -> None:
    set_access(
        root,
        ["input", "genome", "min_mapped_reads", "aligners"],
        ["user", "agent"],
        ADA,
    )
    set_access(root, ["email", "skip_qc", "extra_args", "thresholds"], ["user"], ADA)
    set_access(root, ["outdir", "igenomes_base", "max_cpus"], ["platform"], ADA)
    set_access(root, ["trace_report_suffix"], [], ADA, visibility="hidden")


def _strip_splice(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_splice(item)
            for key, item in value.items()
            if not key.startswith("x-splice-")
        }
    if isinstance(value, list):
        return [_strip_splice(item) for item in value]
    return value


def _compiled(root: Path) -> dict[str, Any]:
    validation = validate_inputs_draft(root)
    assert validation.ready, validation.issues
    loaded: dict[str, Any] = json.loads(validation.files["inputs.schema.json"])
    return loaded


def test_import_preserves_every_nf_schema_construct(tmp_path: Path) -> None:
    upstream = _repository(tmp_path)
    codes = {item.code for item in validate_inputs_draft(tmp_path).issues}
    assert codes == {"access_unreviewed"}
    _review_all(tmp_path)
    compiled = _compiled(tmp_path)

    assert compiled["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert (
        compiled["$id"] == "https://github.com/org/rnaquant/splice/inputs.schema.json"
    )
    assert compiled["x-splice-contract"]["id"].endswith("/workflow-bundle/inputs")
    assert compiled["x-splice-pipeline"]["id"] == "rnaquant"
    lossless = _strip_splice(compiled)
    for key in ("$defs", "allOf", "properties", "if", "then", "title", "description"):
        assert lossless[key] == upstream[key], key
    group = compiled["$defs"]["input_output_options"]
    assert group["required"] == ["input", "outdir"]
    assert group["properties"]["input"]["x-splice-data"] == {
        "kind": "file",
        "samplesheet": True,
    }
    assert group["properties"]["input"]["x-splice-source"]["binding"] == "params.input"
    platform_only = compiled["$defs"]["analysis"]["properties"]["max_cpus"]
    assert platform_only["x-splice-access"] == {"editable_by": ["platform"]}
    assert platform_only["x-custom-ui"] == {"slider": True}
    nullable = compiled["$defs"]["reference_genome_options"]["properties"][
        "igenomes_base"
    ]
    assert nullable["type"] == ["string", "null"] and nullable["default"] is None
    names = [item.name for item in iter_parameters(compiled)]
    assert len(names) == len(set(names)) == 12
    assert _compiled(tmp_path) == compiled


def test_permissions_are_enforced_in_services_not_ui(tmp_path: Path) -> None:
    _repository(tmp_path)
    _review_all(tmp_path)
    schema = _compiled(tmp_path)

    assert authorise_changes(schema, Principal.USER, {"genome": "GRCm39"}) == ()
    denied = authorise_changes(schema, Principal.USER, {"max_cpus": 64})
    assert [item.code for item in denied] == ["not_permitted"]
    assert authorise_changes(schema, Principal.USER, {"max_cpus": 16}) == ()
    agent = authorise_changes(
        schema, Principal.AGENT, {"outdir": "s3://x", "email": "a"}
    )
    assert {item.parameter for item in agent} == {"outdir", "email"}
    assert authorise_changes(schema, Principal.PLATFORM, {"max_cpus": 64}) == ()
    assert [
        item.code for item in authorise_changes(schema, Principal.USER, {"nope": 1})
    ] == ["unknown_parameter"]

    problems = validate_submission(
        schema,
        {
            "input": "ftp://user:pw@host/x.csv",
            "outdir": "s3://bucket/out",
            "genome": "hg19",
        },
        principal=Principal.PLATFORM,
    )
    codes = {item.code for item in problems}
    assert {"schema", "unsupported_scheme", "not_permitted"} <= codes

    user_fields = {item.name: item for item in form_fields(schema, Principal.USER)}
    assert "trace_report_suffix" not in user_fields
    assert "max_cpus" not in user_fields  # hidden and not editable
    assert user_fields["outdir"].editable is False
    assert engine_parameters(schema, {"genome": "GRCh38"}) == {"genome": "GRCh38"}
    with pytest.raises(ValueError, match="snakemake"):
        engine_parameters(schema, {}, engine="snakemake")


def test_agents_cannot_change_access_without_a_human_approver(tmp_path: Path) -> None:
    _repository(tmp_path)
    before = (tmp_path / DRAFT).read_bytes()
    with pytest.raises(LayerError, match="user's approval"):
        set_access(tmp_path, ["max_cpus"], ["user", "agent"], AGENT)
    assert (tmp_path / DRAFT).read_bytes() == before
    proposal = set_access(tmp_path, ["genome"], ["user"], AGENT, write=False)
    assert "editable_by" in proposal.diff and not proposal.wrote
    approved = ChangeContext(
        actor=Actor(label="assistant"),
        origin=ChangeOrigin.AGENT_ASSISTED,
        approved_by=Actor(label="Ada"),
    )
    assert set_access(tmp_path, ["genome"], ["user"], approved).wrote
    with pytest.raises(LayerError, match="admin"):
        set_access(tmp_path, ["genome"], ["admin"], ADA)
    with pytest.raises(LayerError, match="set_access"):
        update_parameter(tmp_path, "genome", {"x-splice-access": {}}, ADA)


def test_reimport_merges_upstream_changes_without_resetting_edits(
    tmp_path: Path,
) -> None:
    upstream = _repository(tmp_path)
    _review_all(tmp_path)
    update_parameter(tmp_path, "genome", {"description": "Curated description."}, ADA)
    assert not plan_reimport(tmp_path).changed

    upstream["$defs"]["analysis"]["properties"]["min_mapped_reads"]["maximum"] = 50
    upstream["$defs"]["analysis"]["properties"]["new_flag"] = {
        "type": "boolean",
        "description": "New.",
    }
    (tmp_path / "nextflow_schema.json").write_text(
        json.dumps(upstream), encoding="utf-8"
    )
    plan = plan_reimport(tmp_path)
    assert plan.changed and plan.conflicts == ()
    apply_reimport(tmp_path, ADA)
    text = (tmp_path / DRAFT).read_text(encoding="utf-8")
    assert "Curated description." in text and "maximum: 50" in text
    codes = {item.pointer for item in validate_inputs_draft(tmp_path).issues}
    assert "/$defs/analysis/properties/new_flag/x-splice-access" in codes

    upstream["$defs"]["reference_genome_options"]["properties"]["genome"][
        "description"
    ] = "Upstream rewrite."
    (tmp_path / "nextflow_schema.json").write_text(
        json.dumps(upstream), encoding="utf-8"
    )
    conflicting = plan_reimport(tmp_path)
    assert any("genome/description" in item for item in conflicting.conflicts)
    with pytest.raises(LayerError, match="overlap manual edits"):
        apply_reimport(tmp_path, ADA)


def test_identity_envelope_drift_and_draft07_import(tmp_path: Path) -> None:
    _repository(tmp_path)
    _review_all(tmp_path)
    set_identity_fields(tmp_path, {"version": "1.3.0"}, ADA)
    codes = {item.code for item in validate_inputs_draft(tmp_path).issues}
    assert "identity_mismatch" in codes
    sync_identity(tmp_path, ADA)
    assert _compiled(tmp_path)["x-splice-pipeline"]["version"] == "1.3.0"

    draft07 = tmp_path / "draft07"
    draft07.mkdir()
    ready_identity(draft07)
    (draft07 / "nextflow_schema.json").write_text(
        json.dumps(
            {
                "$schema": "http://json-schema.org/draft-07/schema",
                "definitions": {
                    "g": {
                        "type": "object",
                        "properties": {
                            "pair": {"type": "array", "items": [{"type": "string"}]}
                        },
                    }
                },
                "allOf": [{"$ref": "#/definitions/g"}],
            }
        ),
        encoding="utf-8",
    )
    import_inputs(draft07)
    set_access(draft07, ["pair"], ["user"], ADA)
    compiled = _compiled(draft07)
    assert compiled["allOf"] == [{"$ref": "#/$defs/g"}]
    assert compiled["$defs"]["g"]["properties"]["pair"]["prefixItems"] == [
        {"type": "string"}
    ]


def test_collisions_unresolved_refs_and_secret_defaults_block(tmp_path: Path) -> None:
    _repository(tmp_path)
    _review_all(tmp_path)
    path = tmp_path / DRAFT
    text = path.read_text(encoding="utf-8")
    text = text.replace("'#/$defs/analysis'", "'#/$defs/missing'").replace(
        '"#/$defs/analysis"', '"#/$defs/missing"'
    )
    path.write_text(text, encoding="utf-8")
    from nf_splice.drafts import PatchOp
    from nf_splice.layers.base import edit_draft

    edit_draft(
        tmp_path,
        "inputs",
        [
            PatchOp(
                "add",
                "/$defs/analysis/properties/genome",
                {
                    "type": "string",
                    "description": "Duplicate.",
                    "x-splice-access": {"editable_by": []},
                },
            ),
            PatchOp(
                "add",
                "/properties/api_token",
                {
                    "type": "string",
                    "description": "Token.",
                    "default": "abc",
                    "x-splice-access": {"editable_by": ["platform"]},
                },
            ),
        ],
        ADA,
    )
    codes = {item.code for item in validate_inputs_draft(tmp_path).issues}
    assert {"unresolved_ref", "parameter_collision", "secret_default"} <= codes
    assert not validate_inputs_draft(tmp_path).ready
