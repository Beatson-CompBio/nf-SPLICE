"""OpenCode provider over the OpenCode v2 server API.

OpenCode is an intermediary: the person configures model providers and
credentials in OpenCode itself (cloud providers, or local OpenAI-compatible
servers such as Ollama, LM Studio, llama.cpp, MLX or SGLang). nf-splice never
installs OpenCode, providers, packages or models.

Server: nf-splice starts ``opencode serve`` on ``127.0.0.1`` on a free port
with a random server password (``OPENCODE_SERVER_PASSWORD``), project
configuration disabled, no model catalogue fetch or auto-update, an empty
private working folder, and an allowlisted environment (variables holding
provider keys are passed only when named in ``NF_SPLICE_OPENCODE_ENV``).
Alternatively it attaches to a running loopback server given by
``NF_SPLICE_OPENCODE_URL`` and ``NF_SPLICE_OPENCODE_PASSWORD``; non-loopback
addresses are refused. Only OpenCode 2.0.x, whose ``permissions`` model was
verified, is supported; 1.x (``permission``) is reported unavailable.

Tools: each turn registers a loopback MCP bridge (:mod:`.mcp_bridge`) named
``nfsplice`` with a fresh bearer token and code mode off, and creates a
session whose permission ruleset denies everything except ``nfsplice_*``.
Native tools (shell, file reading and editing, web, subagents, skills, other
MCP servers) are therefore unavailable; a native tool that nevertheless
succeeds interrupts the turn and pauses the session, and every permission
request is rejected.

Inference location is classified from the selected model's endpoint: a
loopback ``baseURL`` is local; anything else, or unknown, is remote and needs
remote-model consent.
"""

from __future__ import annotations

import asyncio
import atexit
import base64
import contextlib
import ipaddress
import json
import os
import queue
import re
import secrets
import shutil
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from nf_splice import credentials
from nf_splice.agents.protocol import (
    AgentEvent,
    EventKind,
    ProviderCapabilities,
    ProviderUnavailable,
    TurnRequest,
)
from nf_splice.agents.providers import selected_model
from nf_splice.agents.providers.base import (
    Check,
    Diagnosis,
    ModelInfo,
    ProviderError,
    ProviderErrorKind,
    classify_http,
)
from nf_splice.agents.providers.http import request_json
from nf_splice.agents.providers.mcp_bridge import ToolBridge

SUPPORTED = re.compile(r"^2\.0\.\d+$")
BRIDGE = "nfsplice"
PERMISSIONS = [
    {"action": "*", "resource": "*", "effect": "deny"},
    {"action": f"{BRIDGE}_*", "resource": "*", "effect": "allow"},
]
_ENVIRONMENT_ALLOWLIST = (
    "PATH",
    "HOME",
    "LANG",
    "LC_ALL",
    "TMPDIR",
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
    "XDG_STATE_HOME",
    "XDG_CACHE_HOME",
    "OPENCODE_CONFIG",
    "OPENCODE_CONFIG_DIR",
    "SYSTEMROOT",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "no_proxy",
)
_LOCAL_HOSTS = {"localhost"}


def executable() -> str | None:
    return os.environ.get("NF_SPLICE_OPENCODE") or shutil.which("opencode")


def installed_version(command: str) -> str | None:
    try:
        result = subprocess.run(
            [command, "--version"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r"(\d+\.\d+\.\d+)", result.stdout + result.stderr)
    return match.group(1) if match else None


def is_loopback(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    if host in _LOCAL_HOSTS:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def inference_location(model: dict[str, Any]) -> str:
    """``local`` only when the model's endpoint is provably on this computer."""
    settings = model.get("settings") or {}
    url = settings.get("baseURL") or settings.get("baseUrl") or settings.get("url")
    return "local" if isinstance(url, str) and is_loopback(url) else "remote"


def model_ref(value: str) -> dict[str, str]:
    provider, _, model = value.partition("/")
    if not provider or not model:
        raise ProviderError(
            ProviderErrorKind.MODEL_INCOMPATIBLE,
            f"OpenCode models are named provider/model, not {value!r}",
            "List them with `nf-splice provider models opencode`.",
        )
    return {"providerID": provider, "id": model}


def classify(error: dict[str, Any] | None) -> ProviderError:
    """Map OpenCode's ``Session.StructuredError`` to a typed error."""
    error = error or {}
    kind_text = str(error.get("type") or "")
    message = str(error.get("message") or "the OpenCode turn failed")
    status = error.get("status")
    body = str((error.get("response") or {}).get("body") or "")
    if isinstance(status, int):
        mapped = classify_http(status, body or message, vendor="the OpenCode model")
        mapped.message = f"OpenCode: {message}"
        return mapped
    lowered = f"{kind_text} {message}".lower()
    if "auth" in kind_text or "api key" in lowered or "unauthor" in lowered:
        kind = ProviderErrorKind.AUTH_REQUIRED
        guidance = "Configure the model provider's credentials in OpenCode."
    elif "quota" in lowered or "credit" in lowered or "insufficient" in lowered:
        kind = ProviderErrorKind.USAGE_EXHAUSTED
        guidance = "The model provider's quota or credit is used up."
    elif "rate" in lowered and "limit" in lowered:
        kind = ProviderErrorKind.RATE_LIMITED
        guidance = "The model provider asked to slow down."
    elif "context" in lowered or "too long" in lowered:
        kind = ProviderErrorKind.FAILED_TURN
        guidance = "The conversation exceeded the model's context window."
    elif any(word in lowered for word in ("econnrefused", "connect", "fetch failed")):
        kind = ProviderErrorKind.PROVIDER_UNAVAILABLE
        guidance = "The model endpoint is not reachable; is the local model running?"
    elif "not found" in lowered or "model" in kind_text:
        kind = ProviderErrorKind.MODEL_INCOMPATIBLE
        guidance = "Choose another model: `nf-splice provider models opencode`."
    else:
        kind, guidance = ProviderErrorKind.FAILED_TURN, ""
    return ProviderError(kind, f"OpenCode: {message}", guidance, diagnostic=body)


@dataclass(slots=True)
class Server:
    """A loopback OpenCode server: launched by nf-splice, or attached to."""

    url: str
    password: str
    version: str
    process: subprocess.Popen[bytes] | None = None

    def headers(self) -> dict[str, str]:
        token = base64.b64encode(f"opencode:{self.password}".encode()).decode()
        return {"Authorization": f"Basic {token}"}

    def call(self, method: str, path: str, body: Any = None) -> dict[str, Any]:
        return request_json(
            method,
            f"{self.url}{path}",
            headers=self.headers(),
            json_body=body,
            timeout=60,
            vendor="OpenCode",
        )

    def close(self) -> None:
        process, self.process = self.process, None
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(10)
            except subprocess.TimeoutExpired:
                process.kill()


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def workspace() -> Path:
    path = credentials.config_directory() / "opencode-workspace"
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def environment(password: str) -> dict[str, str]:
    kept = {key: os.environ[key] for key in _ENVIRONMENT_ALLOWLIST if key in os.environ}
    for name in os.environ.get("NF_SPLICE_OPENCODE_ENV", "").split(","):
        name = name.strip()
        if name and name in os.environ:
            kept[name] = os.environ[name]
    return kept | {
        "OPENCODE_SERVER_PASSWORD": password,
        "OPENCODE_DISABLE_AUTOUPDATE": "1",
        "OPENCODE_DISABLE_MODELS_FETCH": "1",
        "OPENCODE_DISABLE_PROJECT_CONFIG": "1",
        "OPENCODE_DISABLE_FILEWATCHER": "1",
    }


def connect(timeout: float = 60.0) -> Server:
    """Attach to the configured loopback server, or launch a private one."""
    attach = os.environ.get("NF_SPLICE_OPENCODE_URL")
    if attach:
        if not is_loopback(attach):
            raise ProviderUnavailable(
                "NF_SPLICE_OPENCODE_URL must be a loopback address; nf-splice "
                "never talks to a remote OpenCode server"
            )
        password = os.environ.get("NF_SPLICE_OPENCODE_PASSWORD", "")
        server = Server(attach.rstrip("/"), password, "")
        try:
            info = server.call("GET", "/api/info")
        except ProviderError as error:
            raise ProviderUnavailable(
                f"could not use the OpenCode server at {attach}: {error.message}"
            ) from error
        server.version = str(info.get("version", ""))
        _require_version(server.version)
        return server
    command = executable()
    if command is None:
        raise ProviderUnavailable(
            "OpenCode is not installed; install it yourself or set "
            "NF_SPLICE_OPENCODE (nf-splice never installs it)"
        )
    found = installed_version(command) or ""
    _require_version(found)
    password = secrets.token_urlsafe(32)
    port = _free_port()
    process = subprocess.Popen(
        [command, "serve", "--hostname", "127.0.0.1", "--port", str(port)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=environment(password),
        cwd=workspace(),
    )
    server = Server(f"http://127.0.0.1:{port}", password, found, process)
    deadline = time.monotonic() + timeout
    while True:
        try:
            server.call("GET", "/api/info")
            break
        except ProviderError:
            if process.poll() is not None or time.monotonic() > deadline:
                server.close()
                raise ProviderUnavailable("the OpenCode server did not start") from None
            time.sleep(0.25)
    atexit.register(server.close)
    return server


def _require_version(found: str) -> None:
    if not SUPPORTED.match(found):
        raise ProviderUnavailable(
            f"OpenCode {found or 'of unknown version'} is not supported: nf-splice "
            "verified the 2.0.x server and permissions API (1.x uses a different "
            "permission model)"
        )


def _models(server: Server) -> list[dict[str, Any]]:
    found = server.call("GET", "/api/model").get("data") or []
    return [
        item for item in found if isinstance(item, dict) and item.get("enabled", True)
    ]


def list_models() -> list[ModelInfo]:
    server = connect()
    try:
        return [
            ModelInfo(
                id=f"{item['providerID']}/{item['id']}",
                name=str(item.get("name") or item["id"]),
                tool_calling=bool((item.get("capabilities") or {}).get("tools")),
                location=inference_location(item),
            )
            for item in _models(server)
        ]
    finally:
        server.close()


def diagnose(online: bool = False) -> Diagnosis:
    checks: list[Check] = []
    guidance: list[str] = []
    command = executable()
    attach = os.environ.get("NF_SPLICE_OPENCODE_URL")
    available = False
    if attach:
        checks.append(Check("server", is_loopback(attach), f"attach to {attach}"))
        available = is_loopback(attach)
    elif command is None:
        checks.append(Check("opencode", False, "opencode not found"))
        guidance.append(
            "Install OpenCode 2.0.x yourself (nf-splice never installs it), or "
            "set NF_SPLICE_OPENCODE_URL to a running loopback server."
        )
    else:
        found = installed_version(command)
        available = bool(found and SUPPORTED.match(found))
        checks.append(Check("version", available, f"opencode {found}; verified: 2.0.x"))
        if not available:
            guidance.append("Use OpenCode 2.0.x; other versions stay disabled.")
    chosen = selected_model("opencode")
    models: list[ModelInfo] = []
    inference = "unknown"
    if available and online:
        try:
            models = list_models()
            checks.append(Check("models", bool(models), f"{len(models)} configured"))
            match = next((item for item in models if item.id == chosen), None)
            if match is not None:
                inference = match.location
                checks.append(
                    Check("tool_calling", bool(match.tool_calling), f"{chosen}")
                )
        except (ProviderError, ProviderUnavailable) as error:
            checks.append(Check("server", False, str(error)))
    if not chosen:
        guidance.append(
            "Choose a model: `nf-splice provider models opencode`, then "
            "`nf-splice provider select opencode --model provider/model`."
        )
    return Diagnosis(
        provider="opencode",
        available=available,
        authenticated=available,
        auth_method="OpenCode's own provider configuration",
        account=None,
        inference=inference,
        billing="the configured model provider (none for local models)",
        checks=checks,
        guidance=guidance,
        models=models,
    )


@dataclass(slots=True)
class OpenCodeProvider:
    """An explicitly selected OpenCode model, classified local or remote."""

    model: str | None = None
    _server: Server | None = None
    _location: str | None = None

    def server(self) -> Server:
        if self._server is None:
            self._server = connect()
        return self._server

    def model_info(self, name: str) -> dict[str, Any]:
        reference = model_ref(name)
        for item in _models(self.server()):
            if (
                item.get("providerID") == reference["providerID"]
                and item.get("id") == reference["id"]
            ):
                return item
        raise ProviderError(
            ProviderErrorKind.MODEL_INCOMPATIBLE,
            f"OpenCode has no enabled model {name}",
            "List them with `nf-splice provider models opencode`.",
        )

    def location(self) -> str:
        if self._location is None:
            chosen = self.model or selected_model("opencode")
            try:
                self._location = (
                    inference_location(self.model_info(chosen)) if chosen else "remote"
                )
            except (ProviderError, ProviderUnavailable):
                self._location = "remote"
        return self._location

    @property
    def capabilities(self) -> ProviderCapabilities:
        local = self.location() == "local"
        return ProviderCapabilities(
            name="opencode",
            remote=not local,
            tool_calling=True,
            streaming=True,
            cancellation=True,
            budgets=False,
            continuation=False,
            inference="local" if local else "remote",
            billing="none (local model)" if local else "opencode-configured-provider",
        )

    def open(self, repository: Path) -> OpenCodeSession:
        del repository
        return OpenCodeSession(self)

    def close(self) -> None:
        if self._server is not None:
            self._server.close()
            self._server = None


def _events(server: Server, stop: threading.Event, sink: queue.Queue[Any]) -> None:
    """Read the server's event stream into ``sink`` until ``stop``."""
    call = urllib.request.Request(
        f"{server.url}/api/event",
        headers=server.headers() | {"Accept": "text/event-stream"},
    )
    try:
        with urllib.request.urlopen(call, timeout=3600) as response:
            sink.put({"type": "_connected"})
            for raw in response:
                if stop.is_set():
                    return
                line = raw.decode("utf-8", errors="replace").strip()
                if line.startswith("data:"):
                    with contextlib.suppress(json.JSONDecodeError):
                        sink.put(json.loads(line[5:]))
    except (urllib.error.URLError, OSError) as error:
        if not stop.is_set():
            sink.put({"type": "_lost", "error": str(error)})


@dataclass(slots=True)
class OpenCodeSession:
    provider: OpenCodeProvider
    _session: str | None = None
    _cancelled: bool = False
    _stop: threading.Event = field(default_factory=threading.Event)

    @property
    def conversation_ref(self) -> str | None:
        return None

    async def cancel(self) -> None:
        self._cancelled = True
        if self._session is not None and self.provider._server is not None:
            with contextlib.suppress(Exception):
                await asyncio.to_thread(
                    self.provider._server.call,
                    "POST",
                    f"/api/session/{self._session}/interrupt",
                )

    async def turn(self, request: TurnRequest) -> AsyncIterator[AgentEvent]:
        self._cancelled = False
        chosen = request.model or self.provider.model or selected_model("opencode")
        if not chosen:
            raise ProviderError(
                ProviderErrorKind.MODEL_INCOMPATIBLE,
                "no OpenCode model is selected",
                "Choose one: `nf-splice provider select opencode --model "
                "provider/model`.",
            )
        server = await asyncio.to_thread(self.provider.server)
        info = await asyncio.to_thread(self.provider.model_info, chosen)
        if not (info.get("capabilities") or {}).get("tools"):
            raise ProviderError(
                ProviderErrorKind.MODEL_INCOMPATIBLE,
                f"{chosen} cannot call tools, so it cannot run nf-splice sessions",
                "Choose a tool-capable model, or continue manually.",
            )
        bridge = ToolBridge(request.tools, BRIDGE)
        sink: queue.Queue[Any] = queue.Queue()
        self._stop = threading.Event()
        reader = threading.Thread(
            target=_events, args=(server, self._stop, sink), daemon=True
        )
        try:
            await asyncio.to_thread(
                server.call,
                "PUT",
                f"/api/experimental/mcp/{BRIDGE}",
                {
                    "config": {
                        "type": "remote",
                        "url": bridge.url,
                        "headers": {"Authorization": f"Bearer {bridge.token}"},
                        "oauth": False,
                        "codemode": False,
                    }
                },
            )
            reader.start()
            first = await asyncio.to_thread(sink.get, True, 30)
            if first.get("type") != "_connected":
                raise ProviderError(
                    ProviderErrorKind.CONNECTION_LOST,
                    "could not follow the OpenCode event stream",
                )
            created = await asyncio.to_thread(
                server.call,
                "POST",
                "/api/session",
                {
                    "title": "nf-splice",
                    "model": model_ref(chosen),
                    "permissions": PERMISSIONS,
                },
            )
            self._session = str(created["data"]["id"])
            await asyncio.to_thread(
                server.call,
                "PUT",
                f"/api/experimental/session/{self._session}/instructions/entries/"
                "nf-splice",
                {"value": request.system_prompt},
            )
            await asyncio.to_thread(
                server.call,
                "POST",
                f"/api/session/{self._session}/prompt",
                {"text": request.instruction},
            )
            async for event in self._follow(server, sink, bridge, request, info):
                yield event
        finally:
            self._stop.set()
            session, self._session = self._session, None
            with contextlib.suppress(Exception):
                await asyncio.to_thread(
                    server.call, "DELETE", f"/api/experimental/mcp/{BRIDGE}"
                )
            if session is not None:
                with contextlib.suppress(Exception):
                    await asyncio.to_thread(
                        server.call, "DELETE", f"/api/session/{session}"
                    )
            bridge.close()
        yield AgentEvent(EventKind.DONE)

    async def _follow(
        self,
        server: Server,
        sink: queue.Queue[Any],
        bridge: ToolBridge,
        request: TurnRequest,
        info: dict[str, Any],
    ) -> AsyncIterator[AgentEvent]:
        local = inference_location(info) == "local"
        tokens = {"input": 0, "output": 0}
        cost = 0.0
        step_error: dict[str, Any] | None = None
        steps = 0
        names: dict[str, str] = {}
        while True:
            try:
                event = await asyncio.to_thread(sink.get, True, 0.5)
            except queue.Empty:
                event = None
            for item in bridge.drain():
                yield item
            if event is None:
                continue
            kind = str(event.get("type"))
            data = event.get("data") or {}
            if kind == "_lost":
                raise ProviderError(
                    ProviderErrorKind.CONNECTION_LOST,
                    "the OpenCode event stream ended during the turn",
                )
            if data.get("sessionID") != self._session:
                continue
            call = str(data.get("id") or "")
            if data.get("name"):
                names[call] = str(data["name"])
            name = names.get(call, "")
            if kind == "session.text.ended" and data.get("text"):
                yield AgentEvent(EventKind.MESSAGE, str(data["text"]))
            elif kind == "session.tool.called" and not name.startswith(f"{BRIDGE}_"):
                yield AgentEvent(
                    EventKind.DENIED, name, {"reason": "native OpenCode tool"}
                )
            elif kind == "session.tool.success" and not name.startswith(f"{BRIDGE}_"):
                # Fail closed: an unknown or native tool must never succeed.
                await self.cancel()
                raise ProviderError(
                    ProviderErrorKind.PERMISSION_DENIED,
                    f"OpenCode ran a tool other than nf-splice's ({name or call}); "
                    "nf-splice stopped the turn",
                )
            elif kind == "permission.asked" or kind == "session.permission.create":
                request_id = data.get("id") or data.get("requestID")
                yield AgentEvent(
                    EventKind.DENIED,
                    str(data.get("action") or "permission"),
                    {"reason": "permission requests are always rejected"},
                )
                if request_id:
                    with contextlib.suppress(Exception):
                        await asyncio.to_thread(
                            server.call,
                            "POST",
                            f"/api/session/{self._session}/permission/{request_id}"
                            "/reply",
                            {"decision": "reject"},
                        )
            elif kind == "session.step.ended":
                steps += 1
                used = data.get("tokens") or {}
                tokens["input"] += int(used.get("input") or 0)
                tokens["output"] += int(used.get("output") or 0)
                cost += float(data.get("cost") or 0.0)
                if steps >= request.max_turns * 4:
                    await self.cancel()
            elif kind == "session.step.failed":
                step_error = data.get("error")
            elif kind in {
                "session.execution.succeeded",
                "session.execution.failed",
                "session.execution.interrupted",
            }:
                for item in bridge.drain():
                    yield item
                yield AgentEvent(
                    EventKind.USAGE,
                    "opencode",
                    {
                        "input_tokens": tokens["input"],
                        "output_tokens": tokens["output"],
                        # OpenCode's figure is an estimate from public prices;
                        # local inference has no cost.
                        "cost_usd": None if local or not cost else cost,
                    },
                )
                if kind == "session.execution.succeeded":
                    return
                if kind == "session.execution.interrupted":
                    if self._cancelled:
                        return
                    raise ProviderError(
                        ProviderErrorKind.CANCELLED,
                        f"OpenCode interrupted the turn ({data.get('reason')})",
                    )
                raise classify(data.get("error") or step_error)
