"""Codex provider over the Codex app-server (JSON-RPC on stdio).

Codex is never installed by nf-splice; it is found as ``$NF_SPLICE_CODEX`` or
``codex`` on ``PATH`` and must be a version whose lockdown nf-splice has
verified (:data:`SUPPORTED`). Anything else is reported unavailable rather
than run with unproven restrictions.

Authentication follows OpenAI's documented route for open-source apps
(checked 15 October 2026, developers.openai.com/siwc/token-sharing-open-
source/codex-app-server): the app-server is started with a Responses model
provider whose bearer token comes from the ``ACCESS_TOKEN`` environment
variable. The token is the person's Sign in with ChatGPT access token (or
their API key when they chose API-key mode for OpenAI); no Codex login,
Codex auth file or user configuration is used.

Least privilege, enforced in depth:

- a private ``CODEX_HOME`` under the nf-splice configuration folder, so the
  person's Codex configuration, MCP servers, skills, plugins and history are
  never loaded; an allowlisted process environment with no other secrets;
- shell, apps, browser and computer use, image tools, multi-agent, plugins,
  skills, goals and code mode disabled; web search disabled; project
  instruction files ignored; read-only sandbox in an empty folder;
- the only model-callable tools are nf-splice's, offered per turn as dynamic
  tools and executed by the engine's toolbox; every approval request is
  cancelled, user-input requests are refused, and any native tool item that
  still appears interrupts the turn and pauses the session.

Threads are ephemeral and started per turn (dynamic tools are fixed when a
thread starts), so the engine supplies its own session summary instead of a
provider continuation.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nf_splice import credentials
from nf_splice.agents.protocol import (
    AgentEvent,
    EventKind,
    ProviderCapabilities,
    ProviderUnavailable,
    TurnRequest,
    resolve_effort,
)
from nf_splice.agents.providers import openai as openai_provider
from nf_splice.agents.providers import openai_auth, selected_model
from nf_splice.agents.providers.base import (
    Check,
    Diagnosis,
    ModelInfo,
    ProviderError,
    ProviderErrorKind,
)

#: Codex versions whose restrictions nf-splice's negative tests have verified.
SUPPORTED = re.compile(r"^0\.162\.\d+$")
PROVIDER_ID = "nf_splice_responses"
#: The app-server's per-turn reasoning control (``turn/start`` ``effort``).
#: ``xhigh`` is model-dependent; a model that refuses it fails the turn with
#: a classified error rather than silently running at another level.
REASONING_CONTROL = "Codex app-server turn/start effort"
REASONING_EFFORTS = ("low", "medium", "high", "xhigh")
#: Codex features that would give the model a native capability.
DISABLED_FEATURES = (
    "shell_tool",
    "apps",
    "browser_use",
    "browser_use_external",
    "computer_use",
    "image_generation",
    "view_image",
    "multi_agent",
    "plugins",
    "skill_search",
    "goals",
    "in_app_browser",
    "remote_plugin",
    "skill_mcp_dependency_install",
    "shell_snapshot",
    "code_mode_host",
    "browser_annotation_api",
    "browser_use_full_cdp_access",
)
#: Thread items that only native tools produce; seeing one fails closed.
NATIVE_ITEMS = frozenset(
    {
        "commandExecution",
        "fileChange",
        "mcpToolCall",
        "collabAgentToolCall",
        "subAgentActivity",
        "webSearch",
        "imageView",
        "imageGeneration",
    }
)
_ENVIRONMENT_ALLOWLIST = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT")
_ERROR_KINDS: dict[str, ProviderErrorKind] = {
    "usageLimitExceeded": ProviderErrorKind.USAGE_EXHAUSTED,
    "rateLimitExceeded": ProviderErrorKind.RATE_LIMITED,
    "serverOverloaded": ProviderErrorKind.PROVIDER_UNAVAILABLE,
    "internalServerError": ProviderErrorKind.PROVIDER_UNAVAILABLE,
    "flexUnavailable": ProviderErrorKind.PROVIDER_UNAVAILABLE,
    "unauthorized": ProviderErrorKind.INVALID_CREDENTIALS,
    "sessionBudgetExceeded": ProviderErrorKind.BUDGET_EXHAUSTED,
    "contextWindowExceeded": ProviderErrorKind.FAILED_TURN,
    "badRequest": ProviderErrorKind.FAILED_TURN,
    "cyberPolicy": ProviderErrorKind.PERMISSION_DENIED,
    "misalignmentPolicyViolation": ProviderErrorKind.PERMISSION_DENIED,
    "tooManyDenials": ProviderErrorKind.PERMISSION_DENIED,
    "sandboxError": ProviderErrorKind.PERMISSION_DENIED,
}


def executable() -> list[str] | None:
    configured = os.environ.get("NF_SPLICE_CODEX")
    if configured:
        return [configured]
    found = shutil.which("codex")
    return [found] if found else None


def version(command: Sequence[str]) -> str | None:
    try:
        result = subprocess.run(
            [*command, "--version"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r"(\d+\.\d+\.\d+)", result.stdout)
    return match.group(1) if match else None


def home() -> Path:
    path = credentials.config_directory() / "codex-home"
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path, 0o700)
    return path


def arguments(command: Sequence[str], base_url: str) -> list[str]:
    """The locked-down app-server command line (also checked by tests)."""
    settings = [
        f'model_provider="{PROVIDER_ID}"',
        f'model_providers.{PROVIDER_ID}.name="nf-splice via OpenAI Responses"',
        f'model_providers.{PROVIDER_ID}.base_url="{base_url}"',
        f'model_providers.{PROVIDER_ID}.env_key="ACCESS_TOKEN"',
        f'model_providers.{PROVIDER_ID}.wire_api="responses"',
        f"model_providers.{PROVIDER_ID}.requires_openai_auth=false",
        f"model_providers.{PROVIDER_ID}.supports_websockets=false",
        'web_search="disabled"',
        "project_doc_max_bytes=0",
        "mcp_servers={}",
    ]
    result = [*command, "app-server", "--listen", "stdio://"]
    for item in settings:
        result += ["-c", item]
    for feature in DISABLED_FEATURES:
        result += ["--disable", feature]
    return result


def environment(token: str) -> dict[str, str]:
    """Only what Codex needs; never another provider's or the person's secrets."""
    kept = {key: os.environ[key] for key in _ENVIRONMENT_ALLOWLIST if key in os.environ}
    return kept | {"CODEX_HOME": str(home()), "ACCESS_TOKEN": token}


def turn_error(error: dict[str, Any] | None) -> ProviderError:
    """Map a Codex ``TurnError`` to a typed error."""
    error = error or {}
    info = error.get("codexErrorInfo")
    details = str(error.get("additionalDetails") or "")
    message = str(error.get("message") or "the Codex turn failed")
    if isinstance(info, dict) and info:
        name, body = next(iter(info.items()))
        status = (body or {}).get("httpStatusCode")
        if isinstance(status, int):
            mapped = openai_provider.classify(status, details or message, {})
            mapped.message = f"Codex: {message}"
            return mapped
        return ProviderError(
            ProviderErrorKind.CONNECTION_LOST,
            f"Codex: {message} ({name})",
            diagnostic=details,
        )
    kind = _ERROR_KINDS.get(str(info), ProviderErrorKind.FAILED_TURN)
    if "subscription_sharing" in details:
        coded = openai_provider.classify(400, details, {})
        if coded.kind is not ProviderErrorKind.FAILED_TURN:
            kind = coded.kind
    guidance = openai_provider._GUIDANCE.get(kind, "")
    return ProviderError(kind, f"Codex: {message}", guidance, diagnostic=details)


def list_models() -> list[ModelInfo]:
    """Codex uses the OpenAI account's catalogue (model/list is not an entitlement)."""
    return openai_provider.list_models()


def diagnose(online: bool = False) -> Diagnosis:
    checks: list[Check] = []
    guidance: list[str] = []
    command = executable()
    available = False
    if command is None:
        checks.append(
            Check("codex", False, "codex not found (PATH or NF_SPLICE_CODEX)")
        )
        guidance.append(
            "Install Codex yourself (nf-splice never installs it), for example "
            "npm install -g @openai/codex@0.162, or set NF_SPLICE_CODEX."
        )
    else:
        found = version(command)
        available = bool(found and SUPPORTED.match(found))
        checks.append(
            Check(
                "version",
                available,
                f"codex {found or 'unknown'}; verified: 0.162.x",
            )
        )
        if not available:
            guidance.append(
                "This Codex version's tool restrictions are not verified by "
                "nf-splice, so it is disabled. Use codex 0.162.x or the openai "
                "provider."
            )
    account = openai_provider.diagnose(online=online)
    checks.extend(item for item in account.checks if item.name != "auth_mode")
    guidance.extend(account.guidance)
    return Diagnosis(
        provider="codex",
        available=available,
        authenticated=account.authenticated,
        auth_method=f"{account.auth_method} (passed to app-server as a bearer token)",
        account=account.account,
        inference="remote",
        billing=account.billing,
        checks=[Check("auth_mode", True, openai_provider.auth_mode()), *checks],
        guidance=guidance,
        models=account.models,
    )


@dataclass(slots=True)
class CodexProvider:
    """Codex app-server under nf-splice's lockdown; explicitly selected."""

    model: str | None = None
    command: Sequence[str] | None = None
    base_url: str = openai_auth.ENDPOINTS.resource
    credential: openai_provider.Credential | None = None

    @property
    def capabilities(self) -> ProviderCapabilities:
        mode = openai_provider.auth_mode()
        return ProviderCapabilities(
            name="codex",
            remote=True,
            tool_calling=True,
            streaming=True,
            cancellation=True,
            budgets=False,
            continuation=False,
            inference="remote",
            billing="openai-api-usage" if mode == "api-key" else "chatgpt-plan",
            reasoning_control=REASONING_CONTROL,
            reasoning_efforts=REASONING_EFFORTS,
        )

    def open(self, repository: Path) -> CodexSession:
        del repository
        return CodexSession(self)


@dataclass(slots=True)
class CodexSession:
    provider: CodexProvider
    _process: asyncio.subprocess.Process | None = None
    _pending: dict[int, asyncio.Future[Any]] = field(default_factory=dict)
    _queue: asyncio.Queue[dict[str, Any]] | None = None
    _next: int = 0
    _thread: str | None = None
    _turn: str | None = None
    _cancelled: bool = False

    @property
    def conversation_ref(self) -> str | None:
        return None

    def _command(self) -> list[str]:
        command = list(self.provider.command or executable() or [])
        if not command:
            raise ProviderUnavailable(
                "Codex is not installed; set NF_SPLICE_CODEX or put codex on PATH "
                "(nf-splice never installs it)"
            )
        found = version(command)
        if not (found and SUPPORTED.match(found)):
            raise ProviderUnavailable(
                f"codex {found or 'of unknown version'} is not a version whose "
                "restrictions nf-splice has verified (0.162.x); it stays disabled"
            )
        return command

    async def _write(self, message: dict[str, Any]) -> None:
        assert self._process is not None and self._process.stdin is not None
        self._process.stdin.write((json.dumps(message) + "\n").encode("utf-8"))
        await self._process.stdin.drain()

    async def _call(self, method: str, params: dict[str, Any], timeout: float) -> Any:
        self._next += 1
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._pending[self._next] = future
        await self._write({"id": self._next, "method": method, "params": params})
        return await asyncio.wait_for(future, timeout)

    async def _reader(self) -> None:
        assert self._process is not None and self._process.stdout is not None
        assert self._queue is not None
        async for raw in self._process.stdout:
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if "method" not in message and message.get("id") in self._pending:
                future = self._pending.pop(message["id"])
                if "error" in message:
                    future.set_exception(
                        ProviderError(
                            ProviderErrorKind.FAILED_TURN,
                            "Codex refused a request: "
                            f"{message['error'].get('message')}",
                        )
                    )
                else:
                    future.set_result(message.get("result"))
                continue
            await self._queue.put(message)
        for future in self._pending.values():
            if not future.done():
                future.set_exception(
                    ProviderError(
                        ProviderErrorKind.CONNECTION_LOST,
                        "the Codex app-server stopped unexpectedly",
                    )
                )
        self._pending.clear()
        await self._queue.put({"method": "_closed"})

    async def _respond(self, message: dict[str, Any], result: Any) -> None:
        await self._write({"id": message["id"], "result": result})

    async def _refuse(self, message: dict[str, Any], reason: str) -> None:
        await self._write(
            {"id": message["id"], "error": {"code": -32000, "message": reason}}
        )

    async def cancel(self) -> None:
        self._cancelled = True
        if self._process is not None and self._thread and self._turn:
            with contextlib.suppress(Exception):
                await self._call(
                    "turn/interrupt",
                    {"threadId": self._thread, "turnId": self._turn},
                    timeout=10,
                )

    async def _close(self) -> None:
        process, self._process = self._process, None
        if process is None:
            return
        if process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                process.terminate()
            try:
                await asyncio.wait_for(process.wait(), 5)
            except asyncio.TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    process.kill()
                await process.wait()

    async def turn(self, request: TurnRequest) -> AsyncIterator[AgentEvent]:
        self._cancelled = False
        command = self._command()
        model = request.model or self.provider.model or selected_model("codex")
        if not model:
            raise ProviderError(
                ProviderErrorKind.MODEL_INCOMPATIBLE,
                "no model is selected for Codex",
                "Choose one: `nf-splice provider select codex --model ...`.",
            )
        credential = self.provider.credential
        if credential is None:
            credential = await asyncio.to_thread(
                openai_provider.resolve_credential,
                None,
                min_seconds=request.timeout_seconds + 120,
            )
        offered = {spec["name"]: spec for spec in request.tools.schemas()}
        with tempfile.TemporaryDirectory(prefix="nf-splice-codex-") as empty:
            self._process = await asyncio.create_subprocess_exec(
                *arguments(command, self.provider.base_url),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                env=environment(credential.token),
                cwd=empty,
                limit=16 * 1024 * 1024,
            )
            self._queue = asyncio.Queue()
            reader = asyncio.create_task(self._reader())
            try:
                async for event in self._run(request, str(model), offered, empty):
                    yield event
            finally:
                reader.cancel()
                await self._close()
                self._thread = self._turn = None
        yield AgentEvent(EventKind.DONE)

    async def _run(
        self,
        request: TurnRequest,
        model: str,
        offered: dict[str, dict[str, Any]],
        folder: str,
    ) -> AsyncIterator[AgentEvent]:
        assert self._queue is not None
        await self._call(
            "initialize",
            {
                "clientInfo": {
                    "name": "nf-splice",
                    "title": "nf-splice",
                    "version": _version(),
                },
                "capabilities": {"experimentalApi": True},
            },
            timeout=60,
        )
        await self._write({"method": "initialized"})
        started = await self._call(
            "thread/start",
            {
                "model": model,
                "cwd": folder,
                "approvalPolicy": "untrusted",
                "sandbox": "read-only",
                "baseInstructions": request.system_prompt,
                "dynamicTools": [
                    {
                        "type": "function",
                        "name": spec["name"],
                        "description": spec["description"],
                        "inputSchema": spec["input_schema"],
                    }
                    for spec in offered.values()
                ],
                "ephemeral": True,
                "allowProviderModelFallback": False,
            },
            timeout=60,
        )
        self._thread = str(started["thread"]["id"])
        effort, notice = resolve_effort(
            request.reasoning_effort,
            REASONING_EFFORTS,
            provider="codex",
            control=REASONING_CONTROL,
        )
        if notice:
            yield AgentEvent(EventKind.NOTICE, notice)
        begun = await self._call(
            "turn/start",
            {
                "threadId": self._thread,
                "input": [{"type": "text", "text": request.instruction}],
            }
            | ({"effort": effort} if effort else {}),
            timeout=60,
        )
        self._turn = str((begun or {}).get("turn", {}).get("id") or "") or None
        usage: dict[str, Any] = {}
        last_error: dict[str, Any] | None = None
        calls = 0
        while True:
            message = await self._queue.get()
            method = str(message.get("method"))
            params = message.get("params") or {}
            if method == "_closed":
                raise ProviderError(
                    ProviderErrorKind.CONNECTION_LOST,
                    "the Codex app-server stopped before the turn completed",
                )
            if "id" in message:
                async for event in self._server_request(
                    message, method, params, request, offered
                ):
                    yield event
                if method == "item/tool/call":
                    calls += 1
                    if calls > request.max_turns * 10:
                        await self.cancel()
                continue
            if method == "turn/started":
                self._turn = str(params.get("turn", {}).get("id") or self._turn)
            elif method in {"item/started", "item/completed"}:
                item = params.get("item") or {}
                kind = str(item.get("type"))
                if kind in NATIVE_ITEMS:
                    await self.cancel()
                    yield AgentEvent(
                        EventKind.DENIED, kind, {"reason": "native Codex tool item"}
                    )
                    raise ProviderError(
                        ProviderErrorKind.PERMISSION_DENIED,
                        f"Codex produced a native {kind} item; nf-splice stopped the "
                        "turn because only nf-splice tools are allowed",
                    )
                if method == "item/completed" and kind == "agentMessage":
                    text = str(item.get("text") or "")
                    if text:
                        yield AgentEvent(EventKind.MESSAGE, text)
            elif method == "thread/tokenUsage/updated":
                usage = dict(params.get("tokenUsage", {}).get("total") or {})
            elif method == "error" and not params.get("willRetry"):
                last_error = params.get("error")
            elif method == "turn/completed":
                turn = params.get("turn") or {}
                status = turn.get("status")
                if usage:
                    yield AgentEvent(
                        EventKind.USAGE,
                        "codex",
                        {
                            "input_tokens": usage.get("inputTokens"),
                            "output_tokens": usage.get("outputTokens"),
                            "cost_usd": None,
                        },
                    )
                if status == "completed":
                    return
                if status == "interrupted" and self._cancelled:
                    return
                if status == "interrupted":
                    raise ProviderError(
                        ProviderErrorKind.CANCELLED, "Codex interrupted the turn"
                    )
                raise turn_error(turn.get("error") or last_error)

    async def _server_request(
        self,
        message: dict[str, Any],
        method: str,
        params: dict[str, Any],
        request: TurnRequest,
        offered: dict[str, dict[str, Any]],
    ) -> AsyncIterator[AgentEvent]:
        if method == "item/tool/call":
            name = str(params.get("tool"))
            arguments_ = params.get("arguments")
            if (
                name not in offered
                or params.get("namespace")
                or not isinstance(arguments_, dict)
            ):
                result: dict[str, Any] = {
                    "success": False,
                    "denied": True,
                    "error": f"{name} is not offered or its arguments are invalid",
                }
                yield AgentEvent(EventKind.DENIED, name, result)
            else:
                yield AgentEvent(EventKind.TOOL_CALL, name, {"arguments": arguments_})
                result = request.tools.call(name, arguments_)
                kind = (
                    EventKind.DENIED if result.get("denied") else EventKind.TOOL_RESULT
                )
                yield AgentEvent(kind, name, result)
            await self._respond(
                message,
                {
                    "contentItems": [
                        {"type": "inputText", "text": json.dumps(result, default=str)}
                    ],
                    "success": bool(result.get("success")),
                },
            )
            return
        yield AgentEvent(EventKind.DENIED, method, {"reason": "refused by nf-splice"})
        if method in {
            "item/commandExecution/requestApproval",
            "item/fileChange/requestApproval",
        }:
            await self._respond(message, {"decision": "cancel"})
        elif method in {"applyPatchApproval", "execCommandApproval"}:
            await self._respond(message, {"decision": "abort"})
        elif method == "mcpServer/elicitation/request":
            await self._respond(message, {"action": "cancel", "content": None})
        elif method == "item/tool/requestUserInput":
            await self._respond(message, {"answers": {}})
        else:
            await self._refuse(message, f"{method} is not supported by nf-splice")


def _version() -> str:
    from nf_splice import __version__

    return __version__
