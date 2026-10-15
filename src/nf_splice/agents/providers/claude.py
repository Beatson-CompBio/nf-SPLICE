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

Authentication is a Claude Platform (Console) API key only: from
``ANTHROPIC_API_KEY`` or the nf-splice credential store, passed to the SDK
through its ``env`` option together with a private ``CLAUDE_CONFIG_DIR``. The
person's own Claude Code login, settings and Claude.ai subscription are never
used: Anthropic does not allow third-party products to offer Claude.ai login
or subscription limits without approval (checked 15 October 2026). Team and
Max plans can fund the API key's Console organisation with their monthly API
credits; see docs/guide/providers.md.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

from nf_splice import credentials
from nf_splice.agents.protocol import (
    AgentEvent,
    EventKind,
    ProviderCapabilities,
    ProviderUnavailable,
    TurnRequest,
)
from nf_splice.agents.providers.base import (
    Check,
    Diagnosis,
    ModelInfo,
    ProviderError,
    ProviderErrorKind,
    classify_http,
)
from nf_splice.agents.providers.http import request_json

API_KEY_VARIABLE = "ANTHROPIC_API_KEY"
API_BASE = "https://api.anthropic.com/v1"
API_VERSION = "2023-06-01"
CREDITS_GUIDANCE = (
    "Use a Claude Platform (Console) API key. A Claude Team or Max plan does not "
    "sign in the Agent SDK by itself; an owner can link the plan's monthly API "
    "credits to a Console organisation and issue a key. See "
    "docs/guide/providers.md#claude."
)
#: The SDK's assistant-message error codes.
_SDK_ERRORS: dict[str, tuple[ProviderErrorKind, str]] = {
    "authentication_failed": (
        ProviderErrorKind.INVALID_CREDENTIALS,
        "Check the API key, or ask your Console organisation admin. "
        + CREDITS_GUIDANCE,
    ),
    "billing_error": (
        ProviderErrorKind.USAGE_EXHAUSTED,
        "The Console organisation's credit balance is used up. Ask the billing "
        "admin to add credits or link plan credits; nothing is retried.",
    ),
    "rate_limit": (
        ProviderErrorKind.RATE_LIMITED,
        "Anthropic asked nf-splice to slow down.",
    ),
    "server_error": (
        ProviderErrorKind.PROVIDER_UNAVAILABLE,
        "Anthropic is temporarily unavailable.",
    ),
    "invalid_request": (ProviderErrorKind.FAILED_TURN, "The request was rejected."),
}

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


def classify(status: int, body: str, headers: dict[str, str] | Any) -> ProviderError:
    """Anthropic HTTP errors, with credit exhaustion separated from 429."""
    error = classify_http(
        status,
        body,
        retry_after=headers.get("retry-after"),
        request_id=headers.get("request-id"),
        vendor="Anthropic",
    )
    lowered = body.lower()
    if "credit balance" in lowered or "billing" in lowered:
        error.kind = ProviderErrorKind.USAGE_EXHAUSTED
        error.guidance = _SDK_ERRORS["billing_error"][1]
    elif error.kind is ProviderErrorKind.INVALID_CREDENTIALS:
        error.guidance = _SDK_ERRORS["authentication_failed"][1]
    elif error.kind is ProviderErrorKind.PERMISSION_DENIED:
        error.guidance = (
            "The key's workspace or organisation does not allow this. Ask your "
            "Console organisation admin."
        )
    if status == 529:
        error.kind = ProviderErrorKind.PROVIDER_UNAVAILABLE
    return error


def api_key() -> tuple[str | None, str]:
    return credentials.api_key("claude", API_KEY_VARIABLE)


def isolated_home() -> Path:
    """A private Claude configuration folder (never the person's ~/.claude)."""
    path = credentials.config_directory() / "claude-home"
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def sdk_environment(key: str) -> dict[str, str]:
    return {
        API_KEY_VARIABLE: key,
        "CLAUDE_CONFIG_DIR": str(isolated_home()),
        # Never let a subscription login or another token stand in for the key.
        "CLAUDE_CODE_OAUTH_TOKEN": "",
        "ANTHROPIC_AUTH_TOKEN": "",
        "CLAUDE_CODE_USE_BEDROCK": "",
        "CLAUDE_CODE_USE_VERTEX": "",
        "DISABLE_AUTOUPDATER": "1",
        "DISABLE_TELEMETRY": "1",
    }


def _headers(key: str) -> dict[str, str]:
    return {"x-api-key": key, "anthropic-version": API_VERSION}


def list_models(key: str | None = None) -> list[ModelInfo]:
    found = key or api_key()[0]
    if not found:
        raise ProviderError(
            ProviderErrorKind.AUTH_REQUIRED, "no Claude API key", CREDITS_GUIDANCE
        )
    loaded = request_json(
        "GET",
        f"{API_BASE}/models?limit=100",
        headers=_headers(found),
        vendor="Anthropic",
        classifier=classify,
    )
    return [
        ModelInfo(
            id=str(item["id"]),
            name=str(item.get("display_name") or item["id"]),
            tool_calling=True,
        )
        for item in loaded.get("data", [])
        if isinstance(item, dict) and item.get("id")
    ]


def diagnose(online: bool = False) -> Diagnosis:
    """Missing SDK, missing CLI, missing or invalid key, credits, restrictions."""
    checks: list[Check] = []
    guidance: list[str] = []
    spec = importlib.util.find_spec("claude_agent_sdk")
    available = spec is not None
    if available:
        sdk = importlib.import_module("claude_agent_sdk")
        version = str(getattr(sdk, "__version__", "unknown"))
        checks.append(Check("sdk", True, f"claude-agent-sdk {version}"))
        bundled = Path(str(sdk.__file__)).parent / "_bundled" / "claude"
        cli = bundled.is_file()
        checks.append(
            Check(
                "cli",
                cli,
                "bundled Claude Code CLI present" if cli else "bundled CLI missing",
            )
        )
        available = cli
        if not cli:
            guidance.append("Reinstall the extra: pip install 'nf-splice[claude]'.")
    else:
        checks.append(Check("sdk", False, "claude-agent-sdk is not installed"))
        guidance.append("Install the extra: pip install 'nf-splice[claude]'.")
    key, source = api_key()
    checks.append(Check("api_key", key is not None, f"API key from {source}"))
    if key is None:
        guidance.append(
            "Set ANTHROPIC_API_KEY or run `nf-splice provider auth claude --api-key`. "
            + CREDITS_GUIDANCE
        )
    models: list[ModelInfo] = []
    authenticated = key is not None
    if key and online:
        try:
            models = list_models(key)
            checks.append(Check("api", True, f"key accepted; {len(models)} models"))
        except ProviderError as error:
            authenticated = error.kind not in {
                ProviderErrorKind.INVALID_CREDENTIALS,
                ProviderErrorKind.AUTH_REQUIRED,
            }
            checks.append(Check("api", False, f"{error.kind.value}: {error.message}"))
            guidance.append(error.guidance)
    elif key:
        checks.append(Check("api", True, "not contacted (use --online to verify)"))
    return Diagnosis(
        provider="claude",
        available=available,
        authenticated=authenticated,
        auth_method="Claude Platform API key" if key else "none",
        account=None,
        inference="remote",
        billing="anthropic-console-credits",
        checks=checks,
        guidance=guidance,
        models=models,
    )


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
            name="claude",
            remote=True,
            tool_calling=True,
            streaming=True,
            cancellation=True,
            budgets=True,
            continuation=True,
            inference="remote",
            billing="anthropic-console-credits",
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
    _reported_cost: float = 0.0

    @property
    def conversation_ref(self) -> str | None:
        return self._reference

    def options(
        self, sdk: ModuleType, request: TurnRequest, key: str | None = None
    ) -> Any:
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
        if key is not None:
            options["env"] = sdk_environment(key)
        return sdk.ClaudeAgentOptions(**options)

    async def turn(self, request: TurnRequest) -> AsyncIterator[AgentEvent]:
        sdk = _sdk()
        key, _source = api_key()
        if key is None:
            raise ProviderError(
                ProviderErrorKind.AUTH_REQUIRED,
                "no Claude Platform API key is configured",
                "Set ANTHROPIC_API_KEY or run "
                "`nf-splice provider auth claude --api-key`. " + CREDITS_GUIDANCE,
            )
        # Each turn is a new CLI process, whose reported cost starts at zero.
        self._reported_cost = 0.0
        try:
            async with sdk.ClaudeSDKClient(
                options=self.options(sdk, request, key)
            ) as client:
                self._client = client
                await client.query(request.instruction)
                async for message in client.receive_response():
                    for event in self._events(sdk, message):
                        yield event
        except (ProviderUnavailable, ProviderError):
            raise
        except Exception as error:
            raise self._classify_exception(sdk, error) from None
        finally:
            self._client = None
        for name in self.denied:
            yield AgentEvent(
                EventKind.DENIED, name, {"reason": "blocked by provider guard"}
            )
        self.denied.clear()
        yield AgentEvent(EventKind.DONE)

    @staticmethod
    def _classify_exception(sdk: ModuleType, error: Exception) -> Exception:
        if isinstance(error, sdk.CLINotFoundError):
            return ProviderUnavailable(
                "the Claude Code CLI bundled with the SDK was not found; reinstall "
                "pip install 'nf-splice[claude]'"
            )
        if isinstance(error, sdk.CLIConnectionError):
            return ProviderError(
                ProviderErrorKind.CONNECTION_LOST,
                "lost the connection to the Claude Code CLI",
                diagnostic=str(error),
            )
        status = getattr(error, "api_error_status", None)
        if isinstance(status, int):
            return classify(status, str(error), {})
        return ProviderError(
            ProviderErrorKind.FAILED_TURN,
            f"the Claude turn failed: {type(error).__name__}",
            diagnostic=str(error),
        )

    def _events(self, sdk: ModuleType, message: Any) -> list[AgentEvent]:
        events = []
        failure = getattr(message, "error", None)
        if isinstance(message, sdk.AssistantMessage) and failure:
            kind, guidance = _SDK_ERRORS.get(
                str(failure), (ProviderErrorKind.FAILED_TURN, "")
            )
            raise ProviderError(kind, f"Claude reported {failure}", guidance)
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
            status = getattr(message, "api_error_status", None)
            if getattr(message, "is_error", False) and isinstance(status, int):
                raise classify(status, "; ".join(message.errors or []), {})
            # The SDK reports the process's cumulative cost; count only the
            # increase, so a resumed or repeated result is never added twice.
            total = getattr(message, "total_cost_usd", None)
            delta = None
            if total is not None:
                delta = max(float(total) - self._reported_cost, 0.0)
                self._reported_cost = float(total)
            usage = getattr(message, "usage", None) or {}
            events.append(
                AgentEvent(
                    EventKind.USAGE,
                    "result",
                    {
                        "turns": getattr(message, "num_turns", None),
                        "cost_usd": delta,
                        "input_tokens": usage.get("input_tokens"),
                        "output_tokens": usage.get("output_tokens"),
                        "is_error": getattr(message, "is_error", False),
                    },
                )
            )
        return events

    async def cancel(self) -> None:
        if self._client is not None:
            await self._client.interrupt()
