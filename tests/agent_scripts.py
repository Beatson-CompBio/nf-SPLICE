"""Scripted agents that drive real sessions through real nf-splice tools.

They stand in for a model: they read tool results and decide, but every
change goes through the session toolbox and the deterministic services, and
every outcome is decided by the validators. Nothing here fakes a result.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from layer_fixtures import STAGE_ANALYSIS, follow_scope, review_arguments
from multi_route import ACCESS, ASSAYS, GLOBS, IDENTITY, OUTPUTS
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
    """Declare the assays the documentation states, citing where it says so."""
    _call(tools, "read_source", path="nextflow.config")
    _call(tools, "set_identity", changes=dict(IDENTITY))
    _call(tools, "search_assay_catalogue", text="RNA-seq")
    for code, phrase in ASSAYS.items():
        found = _call(tools, "search_source", pattern=re.escape(phrase))
        sources = sorted(
            {":".join(line.split(":", 2)[:2]) for line in found["data"]["matches"]}
        )
        if not sources:
            continue
        _call(
            tools,
            "add_assay_capability",
            reference=code,
            evidence="documented",
            rationale=f"The documentation names {phrase}.",
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
    """Write the catalogue in one revision from the published routes.

    ``OUTPUTS`` is what this scripted stand-in concludes from the routes; a
    model would read them. ``skip`` leaves a route uncatalogued; ``reject``
    excludes it with a reason.
    """
    _call(tools, "analyse_routes")
    coverage = _call(tools, "route_coverage")
    assert coverage["success"], coverage
    draft = _draft(tools, "outputs")
    catalogue = [
        reviewed | {"entity_types": ["file"]}
        for key, reviewed in OUTPUTS.items()
        if key not in skip and key not in reject
    ]
    result = _call(
        tools,
        "replace_draft",
        layer="outputs",
        expected_sha256=draft["sha256"],
        section="/outputs",
        data=catalogue,
    )
    assert result["success"], result
    if reject:
        draft = _draft(tools, "outputs")
        result = _call(
            tools,
            "replace_draft",
            layer="outputs",
            expected_sha256=draft["sha256"],
            section="/excluded_routes",
            data=[
                {
                    "glob": glob,
                    "kind": "out_of_scope",
                    "reason": "Not observed in the example run.",
                }
                for key in reject
                for glob in GLOBS.get(key, ())
            ],
        )
        assert result["success"], result
    _call(
        tools,
        "set_output_contract_version",
        version="1.0.0",
        basis="proposed_initial",
        rationale="No catalogue was published before; this is the first shape.",
    )


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
