"""Provider-neutral agent interface (no provider SDK is imported here)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Protocol


class AgentMode(str, Enum):
    """What an agent session may do. ``off`` is the default everywhere."""

    OFF = "off"
    ASK = "ask"
    SUGGEST = "suggest"
    DRAFT = "draft"
    APPLY = "apply"


class EventKind(str, Enum):
    """Kinds of streamed session events."""

    MESSAGE = "message"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    PROPOSAL = "proposal"
    DENIED = "denied"
    ERROR = "error"
    DONE = "done"


@dataclass(frozen=True, slots=True)
class AgentEvent:
    """One streamed, provider-independent event."""

    kind: EventKind
    text: str = ""
    data: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    """What a provider implementation supports."""

    name: str
    remote: bool
    streaming: bool
    cancellation: bool
    budgets: bool


@dataclass(frozen=True, slots=True)
class SessionLimits:
    """Resource controls; providers enforce what they support."""

    max_turns: int = 12
    max_budget_usd: float | None = None
    timeout_seconds: float = 300.0
    model: str | None = None


class ToolInvoker(Protocol):
    """Deterministic nf-splice tool mediation used by every provider."""

    def schemas(self) -> list[dict[str, Any]]: ...

    def call(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class AgentContext:
    """Bounded context handed to a provider session."""

    repository: Path
    mode: AgentMode
    tools: ToolInvoker
    system_prompt: str
    limits: SessionLimits = field(default_factory=SessionLimits)


class AgentSession(Protocol):
    """A running conversation that streams events and can be cancelled."""

    def run(self, prompt: str) -> AsyncIterator[AgentEvent]: ...

    async def cancel(self) -> None: ...


class AgentProvider(Protocol):
    """A model provider adapter; adding one never changes core services."""

    @property
    def capabilities(self) -> ProviderCapabilities: ...

    def start(self, context: AgentContext) -> AgentSession: ...
