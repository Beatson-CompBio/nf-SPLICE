"""Scripted agents that drive real sessions through real nf-splice tools.

They stand in for a model: they read tool results and decide, but every
change goes through the session toolbox and the deterministic services, and
every outcome is decided by the validators. Nothing here fakes a result.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from layer_fixtures import STAGE_ANALYSIS, follow_scope, review_arguments
from multi_route import ACCESS, IDENTITY, OUTPUTS
from nf_splice.agents.protocol import ToolInvoker, TurnRequest


def _call(tools: ToolInvoker, name: str, **arguments: Any) -> dict[str, Any]:
    return tools.call(name, arguments)


def _pending(tools: ToolInvoker, layer: str) -> list[dict[str, Any]]:
    result = _call(tools, "list_pending", layer=layer)
    assert result["success"], result
    data: list[dict[str, Any]] = result["data"]
    return data


def _draft(tools: ToolInvoker, layer: str) -> dict[str, Any]:
    result = _call(tools, "read_draft", layer=layer)
    assert result["success"], result
    found: dict[str, Any] = result["data"]
    return found


def identity(tools: ToolInvoker) -> None:
    _call(tools, "read_source", path="nextflow.config")
    _call(tools, "set_identity", changes=dict(IDENTITY))
    assessment = _call(tools, "assess_assays")["data"]
    for candidate in assessment["candidates"]:
        if candidate["status"] != "documented":
            continue
        sources = sorted(
            {
                location
                for item in candidate["evidence"]
                if item["kind"] == "text"
                for location in item["locations"]
            }
        )
        _call(
            tools,
            "add_assay_capability",
            reference=candidate["reference"],
            evidence="documented",
            rationale=f"The documentation names {candidate['entity']['label']}.",
            sources=sources,
        )


def inputs(tools: ToolInvoker) -> None:
    _call(tools, "parameter_usage")
    _call(tools, "sync_identity")
    for name, principals in ACCESS.items():
        _call(tools, "set_parameter_access", parameters=[name], editable_by=principals)


def outputs(
    tools: ToolInvoker, *, skip: Sequence[str] = (), reject: Sequence[str] = ()
) -> None:
    """Rewrite the seeded catalogue in one revision, from the route evidence."""
    _call(tools, "analyse_routes")
    draft = _draft(tools, "outputs")
    catalogue: list[dict[str, Any]] = []
    candidates = _call(tools, "list_pending", layer="outputs", include_decided=True)[
        "data"
    ]
    for candidate in candidates:
        key = candidate["suggested_key"]
        reviewed = OUTPUTS.get(str(key))
        if (
            reviewed is None
            or key in skip
            or key in reject
            or candidate["path_pattern"] is None
            or reviewed["key"] in {item["key"] for item in catalogue}
        ):
            continue
        catalogue.append(
            reviewed
            | {"entity_types": ["file"], "path_patterns": [candidate["path_pattern"]]}
        )
    result = _call(
        tools,
        "replace_draft",
        layer="outputs",
        expected_sha256=draft["sha256"],
        section="/outputs",
        data=catalogue,
    )
    assert result["success"], result
    _call(tools, "set_output_contract_version", version="1.0.0")


def components(tools: ToolInvoker) -> None:
    _call(tools, "component_inventory")
    _call(tools, "set_image_policy", require_downloadable=False)


def profiles(tools: ToolInvoker) -> None:
    _call(tools, "read_config")
    candidates = _pending(tools, "execution-profiles")
    source = next(
        (item["config_sources"][0] for item in candidates if item["config_sources"]),
        "conf/local.config",
    )
    _call(tools, "read_source", path=source)
    draft = _draft(tools, "execution-profiles")
    result = _call(
        tools,
        "replace_draft",
        layer="execution-profiles",
        expected_sha256=draft["sha256"],
        section="/profiles",
        data=[
            {
                "id": "local",
                "name": "Local",
                "description": "Local development.",
                "type": "development",
                "engine": "nextflow",
                "executor": "local",
                "container_engine": "singularity",
                "config": {"adopt": source},
            }
        ],
    )
    assert result["success"], result
    _call(tools, "set_default_profile", profile_id="local")


def provenance(tools: ToolInvoker) -> None:
    _call(tools, "analyse_ro_crate")
    _call(tools, "provenance_strategy", strategy="regenerate")


STAGES: dict[str, Callable[[ToolInvoker], None]] = {
    "identity": identity,
    "inputs": inputs,
    "outputs": outputs,
    "components": components,
    "profiles": profiles,
    "provenance": provenance,
}


@dataclass(slots=True)
class RouteAgent:
    """Authors the multi-route fixture correctly, stage by stage."""

    overrides: dict[str, Callable[[TurnRequest, ToolInvoker], list[str]]] = field(
        default_factory=dict
    )
    seen: list[tuple[str, str | None]] = field(default_factory=list)

    def __call__(self, request: TurnRequest, tools: ToolInvoker) -> list[str]:
        self.seen.append((request.purpose, request.stage))
        key = f"{request.purpose}:{request.stage}"
        if key in self.overrides:
            return self.overrides[key](request, tools)
        if request.purpose in {"question", "help"}:
            status = _call(tools, "workspace_status")
            return [f"Layers: {status['data']['artifacts'][0]['state']}"]
        action = STAGES.get(request.stage or "")
        if action is None:
            return ["Nothing to do for this stage."]
        _call(tools, "workspace_status")
        action(tools)
        stage = str(request.stage)
        follow_scope(tools)
        if request.purpose == "plan":
            submitted = _call(
                tools,
                "submit_stage_proposal",
                summary=f"Review the {stage} layer.",
                evidence=[STAGE_ANALYSIS[stage]],
                uncertainties=[],
            )
            if submitted.get("staged_operations"):
                return [f"Prepared the {stage} stage."]
        _call(
            tools,
            "complete_review",
            **review_arguments(
                stage,
                summary=f"Reviewed the {stage} layer against the sources.",
            ),
        )
        return [f"Prepared the {stage} stage."]
