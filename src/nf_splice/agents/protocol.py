"""Provider-neutral agent protocol (no provider SDK is imported here).

The session engine owns stages, permissions, execution, validation and
persistence. A provider only runs *turns*: it receives an instruction and a
tool invoker, may call the offered tools, and streams events back. Claude is
the first concrete adapter; Codex, OpenCode or local models implement the
same protocol in ``nf_splice.agents.providers`` without touching the engine.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Protocol


class EventKind(str, Enum):
    """Kinds of streamed, provider-independent events."""

    MESSAGE = "message"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    DENIED = "denied"
    USAGE = "usage"
    #: Something the person should know about how the turn ran, such as a
    #: reasoning setting the provider could not apply.
    NOTICE = "notice"
    ERROR = "error"
    DONE = "done"


class ReasoningEffort(str, Enum):
    """Provider-neutral reasoning effort requested for a turn.

    Not a token, time or cost budget. Each adapter translates it to the real
    control of its provider and model, or says that it cannot.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"
    MAX = "max"


#: Scientific authoring defaults to high effort (ADR-0057).
DEFAULT_REASONING_EFFORT = ReasoningEffort.HIGH
_EFFORT_ORDER = tuple(item.value for item in ReasoningEffort)


def resolve_effort(
    requested: str | None,
    supported: tuple[str, ...],
    *,
    provider: str,
    control: str,
) -> tuple[str | None, str | None]:
    """The effort value to send, and a notice when it differs from the request.

    ``supported`` are the values the provider's real control accepts, in no
    particular order. An unsupported request is lowered to the highest
    supported value below it, never raised, and the person is told; with no
    control at all nothing is sent and the notice says so.
    """
    if requested is None:
        return None, None
    if not supported:
        return None, (
            f"{provider} has no reasoning-effort control ({control}); the "
            f"requested '{requested}' effort was not applied and the model's "
            "default is used"
        )
    if requested in supported:
        return requested, None
    position = _EFFORT_ORDER.index(requested) if requested in _EFFORT_ORDER else 2
    lower = [
        item for item in reversed(_EFFORT_ORDER[: position + 1]) if item in supported
    ]
    chosen = lower[0] if lower else sorted(supported)[0]
    return chosen, (
        f"{provider} does not offer '{requested}' reasoning effort ({control}); "
        f"'{chosen}' was used instead"
    )


@dataclass(frozen=True, slots=True)
class AgentEvent:
    """One streamed event."""

    kind: EventKind
    text: str = ""
    data: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    """What a provider supports; the engine checks these before relying on them.

    ``tool_calling`` is required for assisted and autonomous sessions and for
    contextual help. ``continuation`` means the provider can resume its own
    conversation across processes from a stored reference; without it the
    engine sends a summary of the session instead.
    """

    name: str
    remote: bool
    tool_calling: bool
    streaming: bool
    cancellation: bool
    budgets: bool
    continuation: bool
    inference: str = "remote"
    billing: str = "unknown"
    #: The provider's native reasoning control and the values it accepts
    #: (empty: none). Model-dependent controls are checked per turn.
    reasoning_control: str = "none"
    reasoning_efforts: tuple[str, ...] = ()


class ProviderUnavailable(RuntimeError):
    """The provider's optional dependency is missing or cannot start."""


class CapabilityError(RuntimeError):
    """The provider lacks a capability the requested mode needs."""


class ConsentRequired(PermissionError):
    """Repository context would go to a remote model without consent."""


class ToolInvoker(Protocol):
    """Deterministic nf-splice tool mediation offered to a provider turn."""

    def schemas(self) -> list[dict[str, Any]]: ...

    def call(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class TurnRequest:
    """One bounded unit of provider work.

    ``purpose`` is one of ``plan`` (stage changes for approval), ``execute``
    (apply routine decisions under an autonomous policy), ``objection``,
    ``question`` or ``help``. Limits apply to this turn only.
    """

    purpose: str
    instruction: str
    system_prompt: str
    tools: ToolInvoker
    stage: str | None = None
    max_turns: int = 30
    timeout_seconds: float = 600.0
    max_budget_usd: float | None = None
    model: str | None = None
    conversation_ref: str | None = None
    reasoning_effort: str | None = None


class ProviderSession(Protocol):
    """A provider conversation for one repository."""

    @property
    def conversation_ref(self) -> str | None: ...

    def turn(self, request: TurnRequest) -> AsyncIterator[AgentEvent]: ...

    async def cancel(self) -> None: ...


class AgentProvider(Protocol):
    """A model provider adapter; adding one never changes the engine."""

    @property
    def capabilities(self) -> ProviderCapabilities: ...

    def open(self, repository: Path) -> ProviderSession: ...


def require_tool_calling(provider: AgentProvider) -> None:
    """Fail clearly instead of silently dropping approval or validation."""
    capabilities = provider.capabilities
    if not capabilities.tool_calling:
        raise CapabilityError(
            f"provider {capabilities.name!r} cannot call structured tools, so it "
            "cannot run nf-splice sessions or contextual help"
        )


def require_consent(provider: AgentProvider, allow_remote_model: bool) -> None:
    """Refuse to send repository context to a remote model without consent."""
    capabilities = provider.capabilities
    if capabilities.remote and not allow_remote_model:
        raise ConsentRequired(
            f"{capabilities.name} sends repository context to a remote model; "
            "give explicit consent with --allow-remote-model"
        )
