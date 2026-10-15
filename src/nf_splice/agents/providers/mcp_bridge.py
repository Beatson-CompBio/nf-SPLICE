"""A loopback MCP server exposing one turn's nf-splice tools (standard library).

Used by providers that reach tools through MCP (OpenCode). It speaks the
streamable-HTTP transport with plain JSON responses, listens only on
``127.0.0.1`` on a free port, and requires a random bearer token for every
request, so no other local process or remote host can call the tools. The
tool list is exactly what the engine offered for the turn, and each call goes
through the engine's toolbox, which enforces permissions and records audit.

Calls are reported through :attr:`events` so the provider can stream them.
"""

from __future__ import annotations

import hmac
import json
import queue
import secrets
import threading
from collections.abc import Mapping
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from nf_splice.agents.protocol import AgentEvent, EventKind, ToolInvoker

PROTOCOL_VERSION = "2025-06-18"
MAX_BODY = 4 * 1024 * 1024


class ToolBridge:
    """Serve ``tools`` over MCP until :meth:`close`."""

    def __init__(self, tools: ToolInvoker, name: str = "nfsplice") -> None:
        self.tools = tools
        self.name = name
        self.token = secrets.token_urlsafe(32)
        self.events: queue.Queue[AgentEvent] = queue.Queue()
        self.calls = 0
        self._lock = threading.Lock()
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args: Any) -> None:
                return

            def _send(self, status: int, body: Any = None) -> None:
                self.send_response(status)
                if body is None:
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                data = json.dumps(body, default=str).encode("utf-8")
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _authorised(self) -> bool:
                supplied = self.headers.get("Authorization", "")
                return hmac.compare_digest(supplied, f"Bearer {bridge.token}")

            def do_GET(self) -> None:
                # No server-initiated stream is offered.
                self._send(405 if self._authorised() else 401)

            def do_DELETE(self) -> None:
                self._send(200 if self._authorised() else 401)

            def do_POST(self) -> None:
                if not self._authorised():
                    self._send(401)
                    return
                length = int(self.headers.get("Content-Length") or 0)
                if length > MAX_BODY:
                    self._send(413)
                    return
                try:
                    message = json.loads(self.rfile.read(length))
                except json.JSONDecodeError:
                    self._send(400)
                    return
                if not isinstance(message, dict) or "id" not in message:
                    self._send(202)  # notifications need no answer
                    return
                result = bridge.handle(
                    str(message.get("method")), message.get("params") or {}
                )
                reply: dict[str, Any] = {"jsonrpc": "2.0", "id": message["id"]}
                if "error" in result:
                    reply["error"] = result["error"]
                else:
                    reply["result"] = result["result"]
                self._send(200, reply)

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}/mcp"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def handle(self, method: str, params: Mapping[str, Any]) -> dict[str, Any]:
        if method == "initialize":
            return {
                "result": {
                    "protocolVersion": params.get("protocolVersion", PROTOCOL_VERSION),
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": self.name, "version": "1"},
                }
            }
        if method == "ping":
            return {"result": {}}
        if method == "tools/list":
            return {
                "result": {
                    "tools": [
                        {
                            "name": spec["name"],
                            "description": spec["description"],
                            "inputSchema": spec["input_schema"],
                        }
                        for spec in self.tools.schemas()
                    ]
                }
            }
        if method == "tools/call":
            return {"result": self._call(params)}
        return {"error": {"code": -32601, "message": f"{method} is not supported"}}

    def _call(self, params: Mapping[str, Any]) -> dict[str, Any]:
        name = str(params.get("name"))
        arguments = params.get("arguments") or {}
        offered = {spec["name"] for spec in self.tools.schemas()}
        if name not in offered or not isinstance(arguments, dict):
            result: dict[str, Any] = {
                "success": False,
                "denied": True,
                "error": f"{name} is not offered or its arguments are invalid",
            }
            self.events.put(AgentEvent(EventKind.DENIED, name, result))
        else:
            # One tool call at a time, in the order the model made them.
            with self._lock:
                self.calls += 1
                self.events.put(
                    AgentEvent(EventKind.TOOL_CALL, name, {"arguments": arguments})
                )
                result = self.tools.call(name, arguments)
            kind = EventKind.DENIED if result.get("denied") else EventKind.TOOL_RESULT
            self.events.put(AgentEvent(kind, name, result))
        return {
            "content": [{"type": "text", "text": json.dumps(result, default=str)}],
            "isError": not result.get("success", False),
        }

    def drain(self) -> list[AgentEvent]:
        found = []
        while True:
            try:
                found.append(self.events.get_nowait())
            except queue.Empty:
                return found

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
