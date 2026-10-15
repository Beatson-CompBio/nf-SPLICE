"""Claude Agent SDK provider (optional extra: ``pip install nf-splice[claude]``).

The SDK is imported only when a session starts, never at CLI/TUI start-up.
Least privilege is enforced in depth: the built-in tool set is emptied
(``tools=[]``), every built-in is also listed in ``disallowed_tools``, user and
project settings are not loaded, only the in-process ``nf_splice`` MCP server
is configured, and both ``can_use_tool`` and a ``PreToolUse`` hook deny any
tool that is not an nf-splice structured tool. nf-splice's own policy then
re-checks every call, so a misconfigured SDK still fails closed.
"""

from __future__ import annotations

import importlib
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from types import ModuleType
from typing import Any

from nf_splice.agents.policy import FORBIDDEN_PROVIDER_TOOLS, provider_tool_allowed
from nf_splice.agents.protocol import (
    AgentContext,
    AgentEvent,
    EventKind,
    ProviderCapabilities,
)

SERVER = "nf_splice"


class ProviderUnavailable(RuntimeError):
    """The optional SDK is not installed or cannot start."""


def _sdk() -> ModuleType:
    try:
        return importlib.import_module("claude_agent_sdk")
    except ImportError as error:
        raise ProviderUnavailable(
            "the Claude provider needs the optional extra: "
            "pip install 'nf-splice[claude]'"
        ) from error


@dataclass(frozen=True, slots=True)
class ClaudeProvider:
    """Explicitly selected provider; nothing is chosen silently."""

    cli_path: str | None = None

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name="claude-agent-sdk",
            remote=True,
            streaming=True,
            cancellation=True,
            budgets=True,
        )

    def start(self, context: AgentContext) -> ClaudeSession:
        return ClaudeSession(context, self.cli_path)


@dataclass(slots=True)
class ClaudeSession:
    """One SDK client session mediated by nf-splice tools."""

    context: AgentContext
    cli_path: str | None
    denied: list[str] = field(default_factory=list)
    _client: Any = None

    def tool_names(self) -> list[str]:
        return [
            f"mcp__{SERVER}__{spec['name']}" for spec in self.context.tools.schemas()
        ]

    def options(self, sdk: ModuleType) -> Any:
        """Build the restricted SDK options (also used by offline tests)."""
        allowed = self.tool_names()

        def make_handler(name: str) -> Any:
            async def handler(arguments: dict[str, Any]) -> dict[str, Any]:
                result = self.context.tools.call(name, arguments)
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
            for spec in self.context.tools.schemas()
        ]
        server = sdk.create_sdk_mcp_server(SERVER, tools=tools)

        async def can_use_tool(name: str, _input: dict[str, Any], _ctx: Any) -> Any:
            if provider_tool_allowed(name, server=SERVER) and name in allowed:
                return sdk.PermissionResultAllow()
            self.denied.append(name)
            return sdk.PermissionResultDeny(
                message=f"{name} is not an nf-splice tool; only structured nf-splice "
                "tools are available"
            )

        async def pre_tool_use(
            data: dict[str, Any], _tool_use_id: str | None, _ctx: Any
        ) -> dict[str, Any]:
            name = str(data.get("tool_name", ""))
            if provider_tool_allowed(name, server=SERVER) and name in allowed:
                return {}
            self.denied.append(name)
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        "only nf-splice structured tools are allowed"
                    ),
                }
            }

        limits = self.context.limits
        options: dict[str, Any] = {
            "tools": [],
            "allowed_tools": allowed,
            "disallowed_tools": list(FORBIDDEN_PROVIDER_TOOLS),
            "mcp_servers": {SERVER: server},
            "strict_mcp_config": True,
            "setting_sources": [],
            "permission_mode": "default",
            "can_use_tool": can_use_tool,
            "hooks": {
                "PreToolUse": [sdk.HookMatcher(matcher=None, hooks=[pre_tool_use])]
            },
            "cwd": str(self.context.repository),
            "system_prompt": self.context.system_prompt,
            "max_turns": limits.max_turns,
            "max_budget_usd": limits.max_budget_usd,
            "model": limits.model,
        }
        if self.cli_path:
            options["cli_path"] = self.cli_path
        return sdk.ClaudeAgentOptions(**options)

    async def run(self, prompt: str) -> AsyncIterator[AgentEvent]:
        sdk = _sdk()
        try:
            async with sdk.ClaudeSDKClient(options=self.options(sdk)) as client:
                self._client = client
                await client.query(prompt)
                async for message in client.receive_response():
                    for event in self._events(sdk, message):
                        yield event
        except ProviderUnavailable:
            raise
        except Exception as error:
            yield AgentEvent(EventKind.ERROR, f"{type(error).__name__}: {error}")
        for name in self.denied:
            yield AgentEvent(
                EventKind.DENIED, name, {"reason": "blocked by provider guard"}
            )
        yield AgentEvent(EventKind.DONE, "claude session finished")

    @staticmethod
    def _events(sdk: ModuleType, message: Any) -> list[AgentEvent]:
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
            events.append(
                AgentEvent(
                    EventKind.MESSAGE,
                    "result",
                    {
                        "turns": getattr(message, "num_turns", None),
                        "cost_usd": getattr(message, "total_cost_usd", None),
                        "is_error": getattr(message, "is_error", False),
                    },
                )
            )
        return events

    async def cancel(self) -> None:
        if self._client is not None:
            await self._client.interrupt()
