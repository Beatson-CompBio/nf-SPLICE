"""Deterministic offline provider for tests, CI and reproducible runs.

It drives the same engine, toolbox and services as a real model, so tests
prove real artefacts and validator results rather than model messages. A
script is either a Python callable ``agent(request, tools) -> list[str]``
(it calls tools itself and returns messages), or a JSON-compatible list of
turns. Each turn is ``{"stage": ..., "purpose": ..., "steps": [...]}`` (stage
and purpose optional) and steps are ``{"message": text}`` or
``{"tool": name, "arguments": {...}}``. Turns are matched in order to the
first unused turn whose stage and purpose fit the request.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nf_splice.agents.protocol import (
    AgentEvent,
    EventKind,
    ProviderCapabilities,
    ToolInvoker,
    TurnRequest,
)

Agent = Callable[[TurnRequest, ToolInvoker], Sequence[str]]


@dataclass(slots=True)
class ScriptedProvider:
    """A provider whose decisions are written in advance."""

    script: Agent | Sequence[Mapping[str, Any]]
    name: str = "scripted"
    progress: Path | None = None
    requests: list[TurnRequest] = field(default_factory=list)
    _used: set[int] = field(default_factory=set)

    def __post_init__(self) -> None:
        if self.progress is not None and self.progress.is_file():
            self._used = set(json.loads(self.progress.read_text(encoding="utf-8")))

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name=self.name,
            remote=False,
            tool_calling=True,
            streaming=True,
            cancellation=True,
            budgets=False,
            continuation=False,
            reasoning_control="scripted (no model)",
            reasoning_efforts=(),
        )

    def open(self, repository: Path) -> _ScriptedSession:
        del repository
        return _ScriptedSession(self)

    def steps_for(self, request: TurnRequest) -> list[Mapping[str, Any]]:
        if callable(self.script):
            return []
        for index, turn in enumerate(self.script):
            if index in self._used:
                continue
            if turn.get("stage") not in {None, request.stage}:
                continue
            if turn.get("purpose") not in {None, request.purpose}:
                continue
            self._used.add(index)
            if self.progress is not None:
                self.progress.parent.mkdir(parents=True, exist_ok=True)
                self.progress.write_text(json.dumps(sorted(self._used)), "utf-8")
            return list(turn.get("steps") or [])
        return []


class _ScriptedSession:
    def __init__(self, provider: ScriptedProvider) -> None:
        self.provider = provider
        self.cancelled = False

    @property
    def conversation_ref(self) -> str | None:
        return None

    async def turn(self, request: TurnRequest) -> AsyncIterator[AgentEvent]:
        self.provider.requests.append(request)
        if callable(self.provider.script):
            for message in self.provider.script(request, request.tools):
                yield AgentEvent(EventKind.MESSAGE, message)
            yield AgentEvent(EventKind.DONE)
            return
        for step in self.provider.steps_for(request)[: request.max_turns]:
            if self.cancelled:
                break
            if "message" in step:
                yield AgentEvent(EventKind.MESSAGE, str(step["message"]))
                continue
            name = str(step.get("tool"))
            arguments = dict(step.get("arguments") or {})
            yield AgentEvent(EventKind.TOOL_CALL, name, {"arguments": arguments})
            result = request.tools.call(name, arguments)
            kind = EventKind.DENIED if result.get("denied") else EventKind.TOOL_RESULT
            yield AgentEvent(kind, name, result)
        yield AgentEvent(EventKind.DONE)

    async def cancel(self) -> None:
        self.cancelled = True
