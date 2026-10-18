"""Manual mode's "Ask AI": contextual help that never takes control.

A question about a field, an error, a candidate or a Nextflow module gets one
read-only provider turn. It cannot edit, stage or build anything, starts no
session and leaves no state behind except an optional local log.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nf_splice.agents.operations import READ_OPERATIONS
from nf_splice.agents.permissions import ExecutionPolicy
from nf_splice.agents.prompts import help_instruction, system_prompt
from nf_splice.agents.protocol import (
    AgentProvider,
    EventKind,
    TurnRequest,
    require_consent,
    require_tool_calling,
)
from nf_splice.agents.stages import Stage
from nf_splice.agents.state import Usage
from nf_splice.agents.toolbox import SessionToolbox, ToolMode
from nf_splice.domain.audit import Actor, ActorKind, ChangeOrigin
from nf_splice.layers import ChangeContext

#: Read operations offered to contextual help (no checks that run tools).
HELP_OPERATIONS = set(READ_OPERATIONS) - {"run_optional_checks"}


@dataclass(slots=True)
class HelpAnswer:
    """The answer and the read-only tool calls behind it."""

    text: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    denied: list[str] = field(default_factory=list)


#: Pages and layers a question may come from, and the stage they belong to.
_PAGES = {
    "identity": "identity",
    "assays": "identity",
    "bundle": "identity",
    "parameters": "inputs",
    "inputs": "inputs",
    "outputs": "outputs",
    "software": "components",
    "components": "components",
    "execution": "profiles",
    "execution-profiles": "profiles",
    "provenance": "provenance",
}


def _stage(context: Mapping[str, Any]) -> Stage | None:
    """The stage whose procedure answers a question asked on this page."""
    for key in ("page_id", "layer", "page"):
        value = str(context.get(key) or "").casefold()
        if value in _PAGES:
            return Stage(_PAGES[value])
    return None


async def ask_for_help(
    repository: str | Path,
    provider: AgentProvider,
    question: str,
    *,
    context: dict[str, Any] | None = None,
    allow_remote_model: bool = False,
    examples: list[Path] | None = None,
    timeout_seconds: float = 300.0,
    model: str | None = None,
) -> HelpAnswer:
    """Answer one question with read-only tools; nothing can change."""
    require_tool_calling(provider)
    require_consent(provider, allow_remote_model)
    root = Path(repository).resolve()
    calls: list[dict[str, Any]] = []
    policy = ExecutionPolicy(
        examples=[str(item) for item in examples or []],
        allow_remote_model=allow_remote_model,
    )
    toolbox = SessionToolbox(
        root=root,
        policy=policy,
        mode=ToolMode.OBSERVE,
        operations=HELP_OPERATIONS,
        controls=set(),
        change=ChangeContext(
            actor=Actor(label=provider.capabilities.name, kind=ActorKind.AGENT),
            origin=ChangeOrigin.AGENT_ASSISTED,
            approved=False,
        ),
        usage=Usage(),
        examples=list(examples or []),
        log=calls.append,
    )
    request = TurnRequest(
        purpose="help",
        instruction=help_instruction(question, context or {}),
        system_prompt=system_prompt("help", _stage(context or {})),
        tools=toolbox,
        max_turns=12,
        timeout_seconds=timeout_seconds,
        model=model,
    )
    session = provider.open(root)
    messages: list[str] = []
    async for event in session.turn(request):
        if event.kind is EventKind.MESSAGE and event.text:
            messages.append(event.text)
        elif event.kind is EventKind.ERROR:
            messages.append(f"[error] {event.text}")
    return HelpAnswer(
        text="\n\n".join(messages) or "No answer was returned.",
        tool_calls=calls,
        denied=list(toolbox.outcome.denied),
    )
