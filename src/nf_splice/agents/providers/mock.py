"""Deterministic offline provider for tests and reproducible CI runs."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from nf_splice.agents.protocol import (
    AgentContext,
    AgentEvent,
    EventKind,
    ProviderCapabilities,
)


@dataclass(frozen=True, slots=True)
class ScriptedProvider:
    """Replays scripted messages and tool calls through the real toolbox.

    Each step is ``{"message": str}`` or ``{"tool": name, "arguments": {...}}``;
    unknown tools and invalid arguments fail closed through policy.
    """

    steps: Sequence[Mapping[str, Any]]
    name: str = "scripted"

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name=self.name,
            remote=False,
            streaming=True,
            cancellation=True,
            budgets=False,
        )

    def start(self, context: AgentContext) -> _ScriptedSession:
        return _ScriptedSession(context, list(self.steps))


class _ScriptedSession:
    def __init__(self, context: AgentContext, steps: list[Mapping[str, Any]]) -> None:
        self.context = context
        self.steps = steps
        self.cancelled = False

    async def run(self, prompt: str) -> AsyncIterator[AgentEvent]:
        yield AgentEvent(EventKind.MESSAGE, f"received: {prompt}")
        for step in self.steps[: self.context.limits.max_turns]:
            if self.cancelled:
                break
            if "message" in step:
                yield AgentEvent(EventKind.MESSAGE, str(step["message"]))
                continue
            name = str(step.get("tool"))
            arguments = dict(step.get("arguments") or {})
            yield AgentEvent(EventKind.TOOL_CALL, name, {"arguments": arguments})
            result = self.context.tools.call(name, arguments)
            kind = (
                EventKind.DENIED
                if result.get("denied")
                else EventKind.PROPOSAL
                if result.get("proposal_id")
                else EventKind.TOOL_RESULT
            )
            yield AgentEvent(kind, name, result)
        yield AgentEvent(EventKind.DONE, "scripted session finished")

    async def cancel(self) -> None:
        self.cancelled = True
