"""Acceptance tests for reviewed input projection and rendering."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from nf_splice.domain import InputClassification
from nf_splice.services import (
    ApplicationService,
    InputReviewError,
    StaticChangeKind,
    StaticLayerBuildError,
    unresolved_input_candidates,
)


def _repository(root: Path) -> ApplicationService:
    service = ApplicationService()
    service.initialise(
        root,
        name="pipeline",
        version="1.0.0",
        repository_url="https://github.com/org/pipeline",
    )
    schema = {
        "$defs": {
            "analysis": {
                "title": "Analysis options",
                "description": "Reviewed scientific options.",
                "type": "object",
                "properties": {
                    "threshold": {
                        "type": "number",
                        "description": "Existing scientific threshold.",
                        "default": 0.8,
                    },
                    "ambiguous": {"help_text": "Needs review."},
                    "work_dir": {
                        "type": "string",
                        "description": "Execution work directory.",
                    },
                },
            }
        }
    }
    (root / "nextflow_schema.json").write_text(json.dumps(schema), encoding="utf-8")
    return service


def test_inputs_require_classification_and_render_only_reviewed_projection(
    tmp_path: Path,
) -> None:
    service = _repository(tmp_path)
    document = service.discover_inputs(tmp_path)

    assert {item.name for item in unresolved_input_candidates(document)} == {
        "ambiguous",
        "threshold",
        "work_dir",
    }
    service.review_input(
        tmp_path, "input:threshold", InputClassification.USER_CONFIGURABLE.value
    )
    service.review_input(
        tmp_path,
        "input:work_dir",
        InputClassification.EXECUTION_ENVIRONMENT_MANAGED.value,
    )
    with pytest.raises(InputReviewError, match="explicit type"):
        service.review_input(
            tmp_path, "input:ambiguous", InputClassification.USER_CONFIGURABLE.value
        )
    service.review_input(
        tmp_path,
        "input:ambiguous",
        InputClassification.USER_CONFIGURABLE.value,
        type_override="string",
        description_override="Developer-reviewed meaning.",
    )

    preview = service.plan_static_layer(tmp_path, "inputs")
    built = service.build_static_layer(tmp_path, "inputs")
    repeated = service.plan_static_layer(tmp_path, "inputs")
    rendered = json.loads((tmp_path / "splice" / "inputs.schema.json").read_text())
    properties = rendered["$defs"]["analysis"]["properties"]

    assert preview.change.kind is StaticChangeKind.CREATE
    assert preview.wrote is False
    assert built.wrote is True
    assert repeated.change.kind is StaticChangeKind.UNCHANGED
    assert properties["threshold"]["default"] == 0.8
    assert properties["ambiguous"]["description"] == "Developer-reviewed meaning."
    assert "work_dir" not in properties
    Draft202012Validator.check_schema(rendered)


def test_input_build_requires_reviewed_replacement_and_blocks_malformed_targets(
    tmp_path: Path,
) -> None:
    service = _repository(tmp_path)
    service.discover_inputs(tmp_path)
    for name in ("threshold", "ambiguous", "work_dir"):
        service.review_input(
            tmp_path,
            f"input:{name}",
            InputClassification.HIDDEN_OR_UNSUPPORTED.value,
        )
    service.build_static_layer(tmp_path, "inputs")
    target = tmp_path / "splice" / "inputs.schema.json"
    changed = json.loads(target.read_text())
    changed["title"] = "Direct edit"
    target.write_text(json.dumps(changed), encoding="utf-8")

    with pytest.raises(StaticLayerBuildError, match="replace-existing"):
        service.build_static_layer(tmp_path, "inputs")
    assert service.build_static_layer(tmp_path, "inputs", replace_existing=True).wrote

    target.write_text("not json\n", encoding="utf-8")
    with pytest.raises(StaticLayerBuildError, match="malformed"):
        service.build_static_layer(tmp_path, "inputs", replace_existing=True)
