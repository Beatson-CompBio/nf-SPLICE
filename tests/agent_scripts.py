"""Scripted agents that drive real sessions through real nf-splice tools.

They stand in for a model: they read tool results and decide, but every
change goes through the session toolbox and the deterministic services, and
every outcome is decided by the validators. Nothing here fakes a result.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from multi_route import ACCESS, IDENTITY, OUTPUTS
from nf_splice.agents.protocol import ToolInvoker, TurnRequest


def _call(tools: ToolInvoker, name: str, **arguments: Any) -> dict[str, Any]:
    return tools.call(name, arguments)


def _pending(tools: ToolInvoker, layer: str) -> list[dict[str, Any]]:
    result = _call(tools, "list_pending", layer=layer)
    assert result["success"], result
    data: list[dict[str, Any]] = result["data"]
    return data


def identity(tools: ToolInvoker) -> None:
    _call(tools, "set_identity", changes=dict(IDENTITY))


def inputs(tools: ToolInvoker) -> None:
    _call(tools, "sync_identity")
    for name, principals in ACCESS.items():
        _call(tools, "set_parameter_access", parameters=[name], editable_by=principals)


def outputs(
    tools: ToolInvoker, *, skip: Sequence[str] = (), reject: Sequence[str] = ()
) -> None:
    _call(tools, "set_output_contract_version", version="1.0.0")
    for candidate in _pending(tools, "outputs"):
        key = candidate["suggested_key"]
        if key in skip:
            continue
        reviewed = OUTPUTS.get(key)
        if reviewed is None or key in reject:
            _call(
                tools,
                "reject_output",
                candidate_id=candidate["id"],
                reason="Not observed in the example run"
                if key in reject
                else "Not a platform output",
            )
            continue
        _call(
            tools,
            "accept_output",
            candidate_id=candidate["id"],
            output=reviewed
            | {"entity_types": ["file"], "path_patterns": [candidate["path_pattern"]]},
        )


def components(tools: ToolInvoker) -> None:
    _call(tools, "accept_unambiguous_components")
    _call(tools, "set_image_policy", require_downloadable=False)


def profiles(tools: ToolInvoker) -> None:
    for candidate in _pending(tools, "execution-profiles"):
        _call(
            tools,
            "review_profile",
            candidate_id=candidate["id"],
            profile_type="development",
            description="Local development.",
            executor="local",
            container_engine="singularity",
            config_source=candidate["config_sources"][0],
        )
    status = _call(tools, "read_draft", layer="execution-profiles")
    profiles = status["data"].get("profiles") or []
    if profiles:
        _call(tools, "set_default_profile", profile_id=profiles[0]["id"])


def provenance(tools: ToolInvoker) -> None:
    _call(tools, "provenance_strategy", strategy="generated")


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
        if request.purpose == "plan":
            _call(
                tools,
                "submit_stage_proposal",
                summary=f"Review the {request.stage} layer.",
                evidence=["repository files"],
                uncertainties=[],
            )
        return [f"Prepared the {request.stage} stage."]
