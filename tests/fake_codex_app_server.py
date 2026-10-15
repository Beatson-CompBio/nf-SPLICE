"""A scripted stand-in for `codex app-server` (JSON-RPC over stdio).

Usage: fake_codex_app_server.py SCENARIO.json [--version | app-server ...]
The scenario gives the version, a log path, and the steps to play after
``turn/start``: ``{"notify": method, "params": {...}}`` or
``{"request": method, "params": {...}}`` (waits for nf-splice's reply).
Everything received, the command line and the environment are logged.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

scenario = json.load(open(sys.argv[1], encoding="utf-8"))
if "--version" in sys.argv:
    print(f"codex-cli {scenario.get('version', '0.162.1')}")
    sys.exit(0)
log = open(scenario["log"], "a", encoding="utf-8")


def record(kind: str, value: object) -> None:
    log.write(json.dumps({"kind": kind, "value": value}) + "\n")
    log.flush()


def send(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def read() -> dict[str, Any]:
    line = sys.stdin.readline()
    if not line:
        sys.exit(0)
    message: dict[str, Any] = json.loads(line)
    record("received", message)
    return message


record("argv", sys.argv[2:])
record("env", sorted(os.environ))
record("cwd", os.getcwd())
counter = 1000
while True:
    message = read()
    method = message.get("method")
    if method == "initialize":
        send({"id": message["id"], "result": {"userAgent": "fake"}})
    elif method == "thread/start":
        send({"id": message["id"], "result": {"thread": {"id": "thread-1"}}})
    elif method == "turn/interrupt":
        send({"id": message["id"], "result": {}})
    elif method == "turn/start":
        send({"id": message["id"], "result": {"turn": {"id": "turn-1"}}})
        for step in scenario["steps"]:
            if "notify" in step:
                send({"method": step["notify"], "params": step.get("params", {})})
            else:
                counter += 1
                send(
                    {"id": counter, "method": step["request"], "params": step["params"]}
                )
                while True:
                    reply = read()
                    if reply.get("id") == counter and "method" not in reply:
                        break
                    if reply.get("method") == "turn/interrupt":
                        send({"id": reply["id"], "result": {}})
