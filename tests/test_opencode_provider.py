"""OpenCode provider: classification, mediation and the real server lockdown.

Unit tests need no OpenCode. The integration test runs a real OpenCode 2.0.x
server (opt-in: ``opencode`` on PATH or ``NF_SPLICE_OPENCODE``) against a
local fake OpenAI-compatible model, through a recording proxy, and proves
that forged native tool calls fail, only nf-splice tools are offered and no
outbound connection is attempted when the model is local.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import socket
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from nf_splice.agents.protocol import EventKind, ProviderUnavailable, TurnRequest
from nf_splice.agents.providers import opencode
from nf_splice.agents.providers.base import ProviderError, ProviderErrorKind
from nf_splice.agents.providers.mcp_bridge import ToolBridge


class Tools:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "read_layer",
                "description": "Read a layer. Call it when asked.",
                "input_schema": {
                    "type": "object",
                    "properties": {"layer": {"type": "string"}},
                },
            }
        ]

    def call(self, name: str, arguments: Any) -> dict[str, Any]:
        self.calls.append((name, dict(arguments)))
        return {"success": True, "value": "inputs"}


def test_inference_location_is_local_only_for_loopback_endpoints() -> None:
    local = {"settings": {"baseURL": "http://127.0.0.1:11434/v1"}}
    assert opencode.inference_location(local) == "local"
    assert (
        opencode.inference_location({"settings": {"baseURL": "http://localhost:1/v1"}})
        == "local"
    )
    assert (
        opencode.inference_location({"settings": {"baseURL": "http://[::1]:8/v1"}})
        == "local"
    )
    remote = {"settings": {"baseURL": "https://api.example.org/v1"}}
    assert opencode.inference_location(remote) == "remote"
    assert opencode.inference_location({"settings": {}}) == "remote"
    assert (
        opencode.inference_location({"settings": {"baseURL": "http://10.0.0.5/v1"}})
        == "remote"
    )


@pytest.mark.parametrize(
    ("error", "kind"),
    [
        (
            {"type": "provider.auth", "message": "missing key"},
            ProviderErrorKind.AUTH_REQUIRED,
        ),
        (
            {"type": "provider.quota", "message": "quota"},
            ProviderErrorKind.USAGE_EXHAUSTED,
        ),
        ({"type": "x", "message": "x", "status": 429}, ProviderErrorKind.RATE_LIMITED),
        (
            {"type": "x", "message": "x", "status": 401},
            ProviderErrorKind.INVALID_CREDENTIALS,
        ),
        (
            {"type": "x", "message": "context length exceeded"},
            ProviderErrorKind.FAILED_TURN,
        ),
        (
            {"type": "x", "message": "ECONNREFUSED 127.0.0.1:11434"},
            ProviderErrorKind.PROVIDER_UNAVAILABLE,
        ),
    ],
)
def test_errors_are_typed(error: dict[str, Any], kind: ProviderErrorKind) -> None:
    assert opencode.classify(error).kind is kind


def test_model_names_and_server_addresses_are_checked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ProviderError):
        opencode.model_ref("no-provider")
    assert opencode.model_ref("ollama/qwen3:8b") == {
        "providerID": "ollama",
        "id": "qwen3:8b",
    }
    monkeypatch.setenv("NF_SPLICE_OPENCODE_URL", "http://192.0.2.10:4096")
    with pytest.raises(ProviderUnavailable, match="loopback"):
        opencode.connect()


def test_environment_passes_only_named_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-not-passed")
    monkeypatch.setenv("GROQ_API_KEY", "gsk-passed")
    monkeypatch.setenv("NF_SPLICE_OPENCODE_ENV", "GROQ_API_KEY")
    env = opencode.environment("pw")
    assert "OPENAI_API_KEY" not in env and env["GROQ_API_KEY"] == "gsk-passed"
    assert env["OPENCODE_DISABLE_PROJECT_CONFIG"] == "1"
    assert env["OPENCODE_SERVER_PASSWORD"] == "pw"


def test_unsupported_version_is_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(opencode, "executable", lambda: "/bin/echo")
    monkeypatch.setattr(opencode, "installed_version", lambda _c: "1.4.0")
    with pytest.raises(ProviderUnavailable, match=r"2\.0\.x"):
        opencode.connect()


def _rpc(bridge: ToolBridge, body: dict[str, Any], token: str | None) -> Any:
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    call = urllib.request.Request(
        bridge.url, data=json.dumps(body).encode(), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(call, timeout=5) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code


def test_bridge_needs_its_token_and_mediates_calls() -> None:
    tools = Tools()
    bridge = ToolBridge(tools)
    try:
        assert bridge.url.startswith("http://127.0.0.1:")
        listing = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        assert _rpc(bridge, listing, None) == 401
        assert _rpc(bridge, listing, "wrong") == 401
        names = [
            tool["name"]
            for tool in _rpc(bridge, listing, bridge.token)["result"]["tools"]
        ]
        assert names == ["read_layer"]
        forged = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "bash", "arguments": {"command": "id"}},
        }
        assert _rpc(bridge, forged, bridge.token)["result"]["isError"] is True
        good = forged | {"id": 3, "params": {"name": "read_layer", "arguments": {}}}
        assert _rpc(bridge, good, bridge.token)["result"]["isError"] is False
        assert tools.calls == [("read_layer", {})]
        kinds = [event.kind for event in bridge.drain()]
        assert kinds == [EventKind.DENIED, EventKind.TOOL_CALL, EventKind.TOOL_RESULT]
    finally:
        bridge.close()


# ---------------------------------------------------------- real OpenCode


def _real() -> bool:
    command = opencode.executable()
    if command is None:
        return False
    found = opencode.installed_version(command)
    return bool(found and opencode.SUPPORTED.match(found))


class FakeChat:
    """An OpenAI-compatible chat endpoint replaying scripted steps."""

    def __init__(self, script: list[dict[str, Any]]) -> None:
        self.bodies: list[dict[str, Any]] = []
        counter = itertools.count()
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args: Any) -> None:
                return

            def do_GET(self) -> None:
                body = json.dumps({"object": "list", "data": [{"id": "fake-model"}]})
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body.encode())

            def do_POST(self) -> None:
                raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                fake.bodies.append(json.loads(raw))
                number = next(counter)
                step = script[min(number, len(script) - 1)]
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()

                def chunk(delta: dict[str, Any], finish: str | None = None) -> None:
                    data = {
                        "id": f"c{number}",
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": "fake-model",
                        "choices": [
                            {"index": 0, "delta": delta, "finish_reason": finish}
                        ],
                    }
                    self.wfile.write(f"data: {json.dumps(data)}\n\n".encode())
                    self.wfile.flush()

                if "tool" in step:
                    call = {
                        "index": 0,
                        "id": f"call_{number}",
                        "type": "function",
                        "function": {
                            "name": step["tool"],
                            "arguments": json.dumps(step["arguments"]),
                        },
                    }
                    chunk({"role": "assistant", "tool_calls": [call]})
                    chunk({}, "tool_calls")
                else:
                    chunk({"role": "assistant", "content": step["text"]})
                    chunk({}, "stop")
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/v1"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


class RecordingProxy:
    """Accepts proxy connections and records them; forwards nothing."""

    def __init__(self) -> None:
        self.attempts: list[str] = []
        self.socket = socket.socket()
        self.socket.bind(("127.0.0.1", 0))
        self.socket.listen()
        self.url = f"http://127.0.0.1:{self.socket.getsockname()[1]}"
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self) -> None:
        while True:
            try:
                connection, _ = self.socket.accept()
            except OSError:
                return
            with connection:
                data = connection.recv(4096).decode("latin-1")
                self.attempts.append(data.splitlines()[0] if data else "?")

    def close(self) -> None:
        self.socket.close()


@pytest.mark.skipif(not _real(), reason="needs opencode 2.0.x (NF_SPLICE_OPENCODE)")
def test_real_opencode_local_model_is_locked_and_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "pwned"
    fake = FakeChat(
        [
            {
                "tool": "bash",
                "arguments": {"command": f"touch {target}", "description": "x"},
            },
            {"tool": "write", "arguments": {"filePath": str(target), "content": "x"}},
            {"tool": "read", "arguments": {"filePath": "/etc/hosts"}},
            {
                "tool": "webfetch",
                "arguments": {"url": "https://example.org", "format": "text"},
            },
            {"tool": "nfsplice_read_layer", "arguments": {"layer": "inputs"}},
            {"text": "Done."},
        ]
    )
    proxy = RecordingProxy()
    xdg = tmp_path / "xdg"
    config = xdg / "config" / "opencode"
    config.mkdir(parents=True)
    (config / "opencode.json").write_text(
        json.dumps(
            {
                "$schema": "https://opencode.ai/config.json",
                "provider": {
                    "localfake": {
                        "npm": "@ai-sdk/openai-compatible",
                        "name": "Local fake",
                        "options": {"baseURL": fake.url, "apiKey": "unused"},
                        "models": {"fake-model": {"name": "Fake", "tool_call": True}},
                    }
                },
            }
        ),
        "utf-8",
    )
    for part in ("config", "data", "state", "cache"):
        (xdg / part).mkdir(exist_ok=True)
        monkeypatch.setenv(f"XDG_{part.upper()}_HOME", str(xdg / part))
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        monkeypatch.setenv(name, proxy.url)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    provider = opencode.OpenCodeProvider(model="localfake/fake-model")
    try:
        capabilities = provider.capabilities
        assert capabilities.remote is False and capabilities.inference == "local"
        models = opencode.list_models()
        assert any(
            item.id == "localfake/fake-model" and item.location == "local"
            for item in models
        )
        tools = Tools()
        request = TurnRequest(
            purpose="plan",
            instruction="Plan the inputs layer.",
            system_prompt="You are nf-splice. NFSPLICE-SYSTEM-MARK",
            tools=tools,
            stage="inputs",
            max_turns=10,
            timeout_seconds=120,
        )

        async def run() -> list[Any]:
            session = provider.open(tmp_path)
            return [event async for event in session.turn(request)]

        events = asyncio.run(run())
    finally:
        provider.close()
        fake.close()
        proxy.close()
    assert tools.calls == [("read_layer", {"layer": "inputs"})]
    assert not target.exists()
    offered = {
        tool["function"]["name"]
        for body in fake.bodies
        for tool in body.get("tools", [])
    }
    assert offered == {"nfsplice_read_layer"}, offered
    assert "NFSPLICE-SYSTEM-MARK" in json.dumps(fake.bodies[0])
    denied = {event.text for event in events if event.kind is EventKind.DENIED}
    assert {"bash", "write", "read", "webfetch"} <= denied
    assert [e.text for e in events if e.kind is EventKind.MESSAGE][-1] == "Done."
    usage = [e.data for e in events if e.kind is EventKind.USAGE]
    assert usage and usage[0]["cost_usd"] is None
    assert proxy.attempts == [], proxy.attempts


@pytest.mark.skipif(not _real(), reason="needs opencode 2.0.x (NF_SPLICE_OPENCODE)")
def test_real_opencode_offers_tools_on_the_first_step(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Registering the bridge reloads OpenCode; the first step must see it."""
    fake = FakeChat(
        [
            {"tool": "nfsplice_read_layer", "arguments": {"layer": "inputs"}},
            {"text": "Ok."},
        ]
    )
    config = tmp_path / "xdg" / "config" / "opencode"
    config.mkdir(parents=True)
    (config / "opencode.json").write_text(
        json.dumps(
            {
                "provider": {
                    "localfake": {
                        "npm": "@ai-sdk/openai-compatible",
                        "name": "Local fake",
                        "options": {"baseURL": fake.url, "apiKey": "unused"},
                        "models": {"fake-model": {"name": "Fake", "tool_call": True}},
                    }
                }
            }
        ),
        "utf-8",
    )
    for part in ("config", "data", "state", "cache"):
        (tmp_path / "xdg" / part).mkdir(exist_ok=True)
        monkeypatch.setenv(f"XDG_{part.upper()}_HOME", str(tmp_path / "xdg" / part))
    provider = opencode.OpenCodeProvider(model="localfake/fake-model")
    tools = Tools()
    request = TurnRequest(
        purpose="plan",
        instruction="Read the inputs layer.",
        system_prompt="You are nf-splice.",
        tools=tools,
        max_turns=5,
        timeout_seconds=60,
    )

    async def run() -> list[Any]:
        session = provider.open(tmp_path)
        return [event async for event in session.turn(request)]

    try:
        asyncio.run(run())
    finally:
        provider.close()
        fake.close()
    assert tools.calls == [("read_layer", {"layer": "inputs"})]
    assert "nfsplice_read_layer" in {
        tool["function"]["name"] for tool in fake.bodies[-1].get("tools", [])
    }
