"""Codex app-server provider: protocol mapping and enforced restrictions.

The first group drives a scripted fake app-server. The last test runs the
real Codex binary (0.162.x, opt-in through ``NF_SPLICE_CODEX`` or ``codex``
on PATH) against a local fake Responses endpoint and proves that forged
native tool calls cannot run.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from nf_splice.agents.protocol import EventKind, ProviderUnavailable, TurnRequest
from nf_splice.agents.providers import codex
from nf_splice.agents.providers.base import ProviderError, ProviderErrorKind
from nf_splice.agents.providers.openai import Credential

FAKE = Path(__file__).with_name("fake_codex_app_server.py")
TOKEN = "chatgpt-access-token-not-real"


class Tools:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "read_layer",
                "description": "Read a layer.",
                "input_schema": {
                    "type": "object",
                    "properties": {"layer": {"type": "string"}},
                },
            }
        ]

    def call(self, name: str, arguments: Any) -> dict[str, Any]:
        self.calls.append((name, dict(arguments)))
        return {"success": True, "value": "inputs"}


def run_turn(provider: codex.CodexProvider, tools: Tools) -> list[Any]:
    request = TurnRequest(
        purpose="plan",
        instruction="Plan the inputs layer.",
        system_prompt="You are nf-splice.",
        tools=tools,
        stage="inputs",
        max_turns=5,
        timeout_seconds=60,
        model="gpt-test",
    )

    async def run() -> list[Any]:
        session = provider.open(Path("."))
        return [event async for event in session.turn(request)]

    return asyncio.run(run())


def fake_provider(
    tmp_path: Path, steps: list[dict[str, Any]], version: str = "0.162.1"
) -> tuple[codex.CodexProvider, Path]:
    log = tmp_path / "codex.log"
    scenario = tmp_path / "scenario.json"
    scenario.write_text(
        json.dumps({"version": version, "log": str(log), "steps": steps}), "utf-8"
    )
    provider = codex.CodexProvider(
        command=[sys.executable, str(FAKE), str(scenario)],
        credential=Credential("chatgpt", TOKEN, "person", "chatgpt-plan"),
    )
    return provider, log


def logged(log: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in log.read_text("utf-8").splitlines()]


def completed(status: str = "completed", error: Any = None) -> dict[str, Any]:
    return {
        "notify": "turn/completed",
        "params": {"threadId": "thread-1", "turn": {"status": status, "error": error}},
    }


def test_locked_start_routes_tools_and_refuses_everything_else(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-not-leak")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-should-not-leak")
    steps = [
        {
            "request": "item/tool/call",
            "params": {
                "tool": "read_layer",
                "arguments": {"layer": "inputs"},
                "callId": "c1",
                "threadId": "thread-1",
                "turnId": "turn-1",
            },
        },
        {
            "request": "item/tool/call",
            "params": {
                "tool": "write_file",
                "arguments": {},
                "callId": "c2",
                "threadId": "thread-1",
                "turnId": "turn-1",
            },
        },
        {"request": "item/commandExecution/requestApproval", "params": {}},
        {"request": "item/fileChange/requestApproval", "params": {}},
        {"request": "execCommandApproval", "params": {}},
        {"request": "item/tool/requestUserInput", "params": {}},
        {"request": "item/permissions/requestApproval", "params": {}},
        {
            "notify": "item/completed",
            "params": {"item": {"type": "agentMessage", "text": "Planned."}},
        },
        {
            "notify": "thread/tokenUsage/updated",
            "params": {
                "tokenUsage": {
                    "total": {"inputTokens": 40, "outputTokens": 9},
                    "last": {},
                }
            },
        },
        completed(),
    ]
    provider, log = fake_provider(tmp_path, steps)
    tools = Tools()
    events = run_turn(provider, tools)
    assert tools.calls == [("read_layer", {"layer": "inputs"})]
    denied = [event.text for event in events if event.kind is EventKind.DENIED]
    assert denied[0] == "write_file"
    assert "item/commandExecution/requestApproval" in denied
    assert [e.text for e in events if e.kind is EventKind.MESSAGE] == ["Planned."]
    usage = [e.data for e in events if e.kind is EventKind.USAGE]
    assert usage == [{"input_tokens": 40, "output_tokens": 9, "cost_usd": None}]

    records = logged(log)
    argv = next(r["value"] for r in records if r["kind"] == "argv")
    for feature in codex.DISABLED_FEATURES:
        assert feature in argv
    assert 'web_search="disabled"' in argv and "project_doc_max_bytes=0" in argv
    environment = next(r["value"] for r in records if r["kind"] == "env")
    assert "OPENAI_API_KEY" not in environment
    assert "ANTHROPIC_API_KEY" not in environment
    assert {"CODEX_HOME", "ACCESS_TOKEN"} <= set(environment)
    received = [r["value"] for r in records if r["kind"] == "received"]
    start = next(m for m in received if m.get("method") == "thread/start")["params"]
    assert start["sandbox"] == "read-only" and start["ephemeral"] is True
    assert start["approvalPolicy"] == "untrusted"
    assert [tool["name"] for tool in start["dynamicTools"]] == ["read_layer"]
    assert start["allowProviderModelFallback"] is False
    replies = {m["id"]: m for m in received if "method" not in m}
    decisions = [m.get("result", {}).get("decision") for m in replies.values()]
    assert decisions.count("cancel") == 2 and "abort" in decisions
    assert any("error" in m for m in replies.values())  # permissions refused
    assert not any("accept" in json.dumps(m) for m in replies.values())


def test_native_tool_item_fails_closed(tmp_path: Path) -> None:
    steps = [
        {
            "notify": "item/started",
            "params": {"item": {"type": "commandExecution", "command": "cat ~/.ssh"}},
        },
        completed(),
    ]
    provider, log = fake_provider(tmp_path, steps)
    with pytest.raises(ProviderError) as caught:
        run_turn(provider, Tools())
    assert caught.value.kind is ProviderErrorKind.PERMISSION_DENIED
    received = [r["value"] for r in logged(log) if r["kind"] == "received"]
    assert any(m.get("method") == "turn/interrupt" for m in received)


@pytest.mark.parametrize(
    ("error", "kind"),
    [
        (
            {"message": "limit", "codexErrorInfo": "usageLimitExceeded"},
            ProviderErrorKind.USAGE_EXHAUSTED,
        ),
        (
            {"message": "slow", "codexErrorInfo": "rateLimitExceeded"},
            ProviderErrorKind.RATE_LIMITED,
        ),
        (
            {"message": "401", "codexErrorInfo": "unauthorized"},
            ProviderErrorKind.INVALID_CREDENTIALS,
        ),
        (
            {"message": "big", "codexErrorInfo": "contextWindowExceeded"},
            ProviderErrorKind.FAILED_TURN,
        ),
        (
            {"message": "gone", "codexErrorInfo": {"responseStreamDisconnected": {}}},
            ProviderErrorKind.CONNECTION_LOST,
        ),
        (
            {
                "message": "no",
                "codexErrorInfo": {"httpConnectionFailed": {"httpStatusCode": 429}},
                "additionalDetails": json.dumps(
                    {"error": {"code": "subscription_sharing_usage_limit_exceeded"}}
                ),
            },
            ProviderErrorKind.USAGE_EXHAUSTED,
        ),
    ],
)
def test_turn_failures_are_typed(
    tmp_path: Path, error: dict[str, Any], kind: ProviderErrorKind
) -> None:
    provider, _log = fake_provider(tmp_path, [completed("failed", error)])
    with pytest.raises(ProviderError) as caught:
        run_turn(provider, Tools())
    assert caught.value.kind is kind
    assert TOKEN not in str(caught.value) + json.dumps(caught.value.to_json())


def test_unverified_version_stays_disabled(tmp_path: Path) -> None:
    provider, _log = fake_provider(tmp_path, [completed()], version="0.170.0")
    with pytest.raises(ProviderUnavailable, match=r"0\.162"):
        run_turn(provider, Tools())


def test_stopped_server_is_a_lost_connection(tmp_path: Path) -> None:
    exits = tmp_path / "exits.py"
    exits.write_text(
        "import sys\nif '--version' in sys.argv:\n    print('codex-cli 0.162.1')\n",
        "utf-8",
    )
    provider = codex.CodexProvider(
        command=[sys.executable, str(exits)],
        credential=Credential("chatgpt", TOKEN, "person", "chatgpt-plan"),
    )
    with pytest.raises(ProviderError) as caught:
        run_turn(provider, Tools())
    assert caught.value.kind is ProviderErrorKind.CONNECTION_LOST


# ------------------------------------------------------------- real Codex


def _real_codex() -> list[str] | None:
    command = codex.executable()
    if command is None:
        return None
    found = codex.version(command)
    return command if found and codex.SUPPORTED.match(found) else None


class FakeResponses:
    """Replays Responses API streams to Codex and keeps every request body."""

    def __init__(self, script: list[list[dict[str, Any]]]) -> None:
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
                items = script[min(number, len(script) - 1)]
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()

                def event(name: str, **values: Any) -> None:
                    data = json.dumps({"type": name, **values})
                    self.wfile.write(f"event: {name}\ndata: {data}\n\n".encode())
                    self.wfile.flush()

                response = {"id": f"resp_{number}", "object": "response", "output": []}
                event("response.created", response=response | {"status": "in_progress"})
                for index, item in enumerate(items):
                    event("response.output_item.added", output_index=index, item=item)
                    event("response.output_item.done", output_index=index, item=item)
                usage = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
                event(
                    "response.completed",
                    response=response
                    | {"status": "completed", "output": items, "usage": usage},
                )

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/v1"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def _call(name: str, call_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "function_call",
        "id": f"fc_{call_id}",
        "call_id": call_id,
        "name": name,
        "arguments": json.dumps(arguments),
        "status": "completed",
    }


@pytest.mark.skipif(
    _real_codex() is None, reason="needs codex 0.162.x (NF_SPLICE_CODEX)"
)
def test_real_codex_cannot_bypass_nf_splice(tmp_path: Path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("do not read", "utf-8")
    message = {
        "type": "message",
        "id": "msg_1",
        "role": "assistant",
        "status": "completed",
        "content": [{"type": "output_text", "text": "Done.", "annotations": []}],
    }
    fake = FakeResponses(
        [
            [
                _call("read_layer", "c1", {"layer": "inputs"}),
                _call("exec_command", "c2", {"cmd": f"cat {secret}"}),
                _call("shell", "c3", {"command": ["cat", str(secret)]}),
                _call("apply_patch", "c4", {"input": "*** Begin Patch"}),
                _call("web_search", "c5", {"query": "x"}),
            ],
            [message],
        ]
    )
    try:
        provider = codex.CodexProvider(
            command=_real_codex(),
            base_url=fake.url,
            credential=Credential("chatgpt", TOKEN, "person", "chatgpt-plan"),
        )
        tools = Tools()
        events = run_turn(provider, tools)
    finally:
        fake.close()
    assert tools.calls == [("read_layer", {"layer": "inputs"})]
    offered = {
        tool.get("name") for body in fake.bodies for tool in body.get("tools", [])
    }
    assert offered <= {"read_layer", "request_user_input"}, offered
    outputs = {
        item["call_id"]: str(item.get("output"))
        for item in fake.bodies[-1]["input"]
        if item.get("type") == "function_call_output"
    }
    assert "do not read" not in json.dumps(fake.bodies)
    assert set(outputs) >= {"c1", "c2", "c3", "c4", "c5"}
    for forged in ("c2", "c3", "c4", "c5"):
        assert "inputs" not in outputs[forged]
    assert [e.text for e in events if e.kind is EventKind.MESSAGE] == ["Done."]
    assert all(body.get("store") is False for body in fake.bodies)
    assert os.environ.get("CODEX_HOME") is None  # never set for the parent
