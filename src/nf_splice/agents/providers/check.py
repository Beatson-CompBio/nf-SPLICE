"""A small, real provider turn proving structured tool calling works.

Used by ``nf-splice provider test``. The model is offered one harmless
nf-splice tool and must call it with the expected argument; no repository
content is sent and nothing is changed.
"""

from __future__ import annotations

import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from nf_splice.agents.protocol import AgentProvider, EventKind, TurnRequest

TOOL = "report_ready"


class _Probe:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "name": TOOL,
                "description": "Report that the connection test reached you.",
                "input_schema": {
                    "type": "object",
                    "properties": {"word": {"type": "string"}},
                    "required": ["word"],
                    "additionalProperties": False,
                },
            }
        ]

    def call(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        if name != TOOL:
            return {"success": False, "denied": True, "error": f"{name} not offered"}
        self.calls.append(dict(arguments))
        return {"success": True}


async def tool_call_check(
    provider: AgentProvider, model: str | None = None
) -> dict[str, Any]:
    probe = _Probe()
    request = TurnRequest(
        purpose="help",
        instruction=f"Call the {TOOL} tool once with word set to 'splice'. "
        "Do not call any other tool.",
        system_prompt="You are testing a tool connection. Use only the offered tool.",
        tools=probe,
        max_turns=3,
        timeout_seconds=120,
        max_budget_usd=0.05,
        model=model,
    )
    denied: list[str] = []
    usage: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="nf-splice-provider-test-") as folder:
        session = provider.open(Path(folder))
        async for event in session.turn(request):
            if event.kind is EventKind.DENIED:
                denied.append(event.text)
            elif event.kind is EventKind.USAGE:
                usage.append(dict(event.data))
    passed = any(call.get("word") == "splice" for call in probe.calls) and not denied
    detail = (
        "the model called the nf-splice tool"
        if passed
        else f"tool calls {probe.calls!r}, refused {denied!r}"
    )
    return {
        "provider": provider.capabilities.name,
        "model": model,
        "passed": passed,
        "detail": detail,
        "denied": denied,
        "usage": usage,
    }
