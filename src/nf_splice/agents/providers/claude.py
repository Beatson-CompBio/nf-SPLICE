"""Claude Agent SDK provider (optional extra: ``pip install nf-splice[claude]``).

The SDK is imported only when a turn starts, never at CLI or wizard start-up.
Least privilege is enforced in depth: the built-in tool set is emptied
(``tools=[]``), every built-in is also listed in ``disallowed_tools``, user and
project settings are not loaded, only the in-process ``nf_splice`` MCP server
is configured, and both ``can_use_tool`` and a ``PreToolUse`` hook deny any
tool the engine did not offer for this turn. The engine's toolbox then
re-checks every call, so a misconfigured SDK still fails closed.

Sessions continue across turns and processes with the SDK's ``resume``
option, using the session id the SDK reports.
"""

from __future__ import annotations

import importlib
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

from nf_splice.agents.protocol import (
    AgentEvent,
    EventKind,
    ProviderCapabilities,
    ProviderUnavailable,
    TurnRequest,
)

SERVER = "nf_splice"
#: Built-in tools of the SDK that must never be available.
FORBIDDEN_TOOLS = (
    "Bash",
    "BashOutput",
    "KillShell",
    "Read",
    "Write",
    "Edit",
    "MultiEdit",
    "NotebookEdit",
    "Glob",
    "Grep",
    "LS",
    "WebFetch",
    "WebSearch",
    "Task",
    "TodoWrite",
    "Skill",
)


def _sdk() -> ModuleType:
    try:
        return importlib.import_module("claude_agent_sdk")
    except ImportError as error:
        raise ProviderUnavailable(
            "the Claude provider needs the optional extra: "
            "pip install 'nf-splice[claude]'"
        ) from error


def tool_allowed(name: str, offered: set[str]) -> bool:
    """Only the nf-splice tools offered for this turn may run."""
    return name in offered and name.startswith(f"mcp__{SERVER}__")


@dataclass(frozen=True, slots=True)
class ClaudeProvider:
    """Explicitly selected provider; nothing is chosen silently."""

    cli_path: str | None = None

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name="claude-agent-sdk",
            remote=True,
            tool_calling=True,
            streaming=True,
            cancellation=True,
            budgets=True,
            continuation=True,
        )

    def open(self, repository: Path) -> ClaudeSession:
        return ClaudeSession(repository, self.cli_path)


@dataclass(slots=True)
class ClaudeSession:
    """Turns of one Claude conversation, mediated by nf-splice tools."""

    repository: Path
    cli_path: str | None
    denied: list[str] = field(default_factory=list)
    _reference: str | None = None
    _client: Any = None

    @property
    def conversation_ref(self) -> str | None:
        return self._reference

    def options(self, sdk: ModuleType, request: TurnRequest) -> Any:
        """Build the restricted SDK options (also used by offline tests)."""
        offered = {f"mcp__{SERVER}__{spec['name']}" for spec in request.tools.schemas()}

        def make_handler(name: str) -> Any:
            async def handler(arguments: dict[str, Any]) -> dict[str, Any]:
                result = request.tools.call(name, arguments)
                return {
                    "content": [
                        {"type": "text", "text": json.dumps(result, default=str)}
                    ],
                    "is_error": not result.get("success", False),
                }

            return handler

        tools = [
            sdk.tool(spec["name"], spec["description"], spec["input_schema"])(
                make_handler(spec["name"])
            )
            for spec in request.tools.schemas()
        ]
        server = sdk.create_sdk_mcp_server(SERVER, tools=tools)

        async def can_use_tool(name: str, _input: dict[str, Any], _ctx: Any) -> Any:
            if tool_allowed(name, offered):
                return sdk.PermissionResultAllow()
            self.denied.append(name)
            return sdk.PermissionResultDeny(
                message=f"{name} is not offered; only nf-splice tools are available"
            )

        async def pre_tool_use(
            data: dict[str, Any], _tool_use_id: str | None, _ctx: Any
        ) -> dict[str, Any]:
            name = str(data.get("tool_name", ""))
            if tool_allowed(name, offered):
                return {}
            self.denied.append(name)
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": "only nf-splice tools are allowed",
                }
            }

        options: dict[str, Any] = {
            "tools": [],
            "allowed_tools": sorted(offered),
            "disallowed_tools": list(FORBIDDEN_TOOLS),
            "mcp_servers": {SERVER: server},
            "strict_mcp_config": True,
            "setting_sources": [],
            "permission_mode": "default",
            "can_use_tool": can_use_tool,
            "hooks": {
                "PreToolUse": [sdk.HookMatcher(matcher=None, hooks=[pre_tool_use])]
            },
            "cwd": str(self.repository),
            "system_prompt": request.system_prompt,
            "max_turns": request.max_turns,
            "max_budget_usd": request.max_budget_usd,
            "model": request.model,
        }
        reference = request.conversation_ref or self._reference
        if reference:
            options["resume"] = reference
        if self.cli_path:
            options["cli_path"] = self.cli_path
        return sdk.ClaudeAgentOptions(**options)

    async def turn(self, request: TurnRequest) -> AsyncIterator[AgentEvent]:
        sdk = _sdk()
        try:
            async with sdk.ClaudeSDKClient(
                options=self.options(sdk, request)
            ) as client:
                self._client = client
                await client.query(request.instruction)
                async for message in client.receive_response():
                    for event in self._events(sdk, message):
                        yield event
        except ProviderUnavailable:
            raise
        except Exception as error:
            yield AgentEvent(EventKind.ERROR, f"{type(error).__name__}: {error}")
        finally:
            self._client = None
        for name in self.denied:
            yield AgentEvent(
                EventKind.DENIED, name, {"reason": "blocked by provider guard"}
            )
        self.denied.clear()
        yield AgentEvent(EventKind.DONE)

    def _events(self, sdk: ModuleType, message: Any) -> list[AgentEvent]:
        events = []
        if isinstance(message, sdk.AssistantMessage):
            for block in message.content:
                if isinstance(block, sdk.TextBlock):
                    events.append(AgentEvent(EventKind.MESSAGE, block.text))
                elif isinstance(block, sdk.ToolUseBlock):
                    events.append(
                        AgentEvent(
                            EventKind.TOOL_CALL, block.name, {"arguments": block.input}
                        )
                    )
        elif isinstance(message, sdk.ResultMessage):
            reference = getattr(message, "session_id", None)
            if reference:
                self._reference = str(reference)
            events.append(
                AgentEvent(
                    EventKind.USAGE,
                    "result",
                    {
                        "turns": getattr(message, "num_turns", None),
                        "cost_usd": getattr(message, "total_cost_usd", None) or 0.0,
                        "is_error": getattr(message, "is_error", False),
                    },
                )
            )
        return events

    async def cancel(self) -> None:
        if self._client is not None:
            await self._client.interrupt()
