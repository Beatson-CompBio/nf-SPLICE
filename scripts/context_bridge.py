#!/usr/bin/env python3
"""Offline bridge: let a person or an external agent act as the model.

It evaluates whether the context nf-splice prepares is enough to integrate a
pipeline, without any provider account. ``serve`` runs the real
:class:`~nf_splice.agents.SessionEngine` (production prompts, tool schemas,
permissions, staging, validation and gates) with a provider that, instead
of calling a model, writes each turn's exact request to a folder and runs
the tool calls an evaluator submits with ``call``. ``done`` ends the turn
with the evaluator's message. Nothing leaves the machine.

    python scripts/context_bridge.py serve --repository R --folder F \\
        --mode autonomous            # or: --mode assisted --stage outputs,
                                     #     or: --ask "question" --page outputs
    python scripts/context_bridge.py status F
    python scripts/context_bridge.py call F read_source '{"path": "main.nf"}'
    python scripts/context_bridge.py done F "Summary of what I did."

Keep the folder in an ignored location (``.nf-splice-local/``): it holds
the full transcripts. No credentials are involved.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nf_splice.agents import (
    ExecutionPolicy,
    InteractionMode,
    Permission,
    SessionEngine,
    ask_for_help,
)
from nf_splice.agents.protocol import (
    AgentEvent,
    EventKind,
    ProviderCapabilities,
    TurnRequest,
)
from nf_splice.agents.stages import Stage
from nf_splice.domain.audit import Actor

POLL = 0.2


def _write(path: Path, data: Any) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2, default=str) + "\n", "utf-8")
    temporary.replace(path)


@dataclass(slots=True)
class BridgeProvider:
    """A provider whose decisions come from files an evaluator writes."""

    folder: Path
    turns: list[str] = field(default_factory=list)

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name="context-bridge",
            remote=False,
            tool_calling=True,
            streaming=True,
            cancellation=True,
            budgets=False,
            continuation=False,
            reasoning_control="external evaluator",
            reasoning_efforts=(),
        )

    def open(self, repository: Path) -> _BridgeSession:
        del repository
        return _BridgeSession(self)


class _BridgeSession:
    def __init__(self, provider: BridgeProvider) -> None:
        self.provider = provider

    @property
    def conversation_ref(self) -> str | None:
        return None

    async def turn(self, request: TurnRequest) -> AsyncIterator[AgentEvent]:
        index = len(self.provider.turns) + 1
        name = f"turn-{index:02d}-{request.purpose}-{request.stage or 'none'}"
        self.provider.turns.append(name)
        turn = self.provider.folder / name
        (turn / "calls").mkdir(parents=True)
        schemas = request.tools.schemas()
        _write(
            turn / "request.json",
            {
                "purpose": request.purpose,
                "stage": request.stage,
                "system_prompt": request.system_prompt,
                "instruction": request.instruction,
                "tools": schemas,
                "sizes": {
                    "system_prompt_chars": len(request.system_prompt),
                    "instruction_chars": len(request.instruction),
                    "tool_schema_chars": len(json.dumps(schemas)),
                    "tools": len(schemas),
                },
                "max_turns": request.max_turns,
            },
        )
        _write(self.provider.folder / "active.json", {"turn": name})
        handled: set[str] = set()
        while True:
            pending = sorted(
                path
                for path in (turn / "calls").glob("*.call.json")
                if path.name not in handled
            )
            for path in pending:
                handled.add(path.name)
                command = json.loads(path.read_text("utf-8"))
                if "done" in command:
                    yield AgentEvent(EventKind.MESSAGE, str(command["done"]))
                    _write(path.with_name(path.name.replace(".call", ".result")), {})
                    _write(self.provider.folder / "active.json", {"turn": None})
                    yield AgentEvent(EventKind.DONE)
                    return
                tool = str(command["tool"])
                arguments = dict(command.get("arguments") or {})
                yield AgentEvent(EventKind.TOOL_CALL, tool, {"arguments": arguments})
                try:
                    result = request.tools.call(tool, arguments)
                except Exception as error:  # surfaced to the evaluator verbatim
                    result = {
                        "success": False,
                        "error": f"{type(error).__name__}: {error}",
                    }
                _write(path.with_name(path.name.replace(".call", ".result")), result)
                kind = (
                    EventKind.DENIED if result.get("denied") else EventKind.TOOL_RESULT
                )
                yield AgentEvent(kind, tool, result)
            await asyncio.sleep(POLL)

    async def cancel(self) -> None:
        return None


def serve(arguments: argparse.Namespace) -> int:
    folder = Path(arguments.folder).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    provider = BridgeProvider(folder)
    root = Path(arguments.repository).resolve()
    actor = Actor(label=arguments.user)
    if arguments.ask:

        async def ask() -> None:
            answer = await ask_for_help(
                root,
                provider,
                arguments.ask,
                context={"page": arguments.page} if arguments.page else {},
            )
            _write(folder / "answer.json", {"text": answer.text})

        asyncio.run(ask())
        return 0
    policy = ExecutionPolicy(
        grants=sorted(
            {
                Permission.READ,
                Permission.DRAFT_EDIT,
                *(Permission(item) for item in arguments.grant),
            },
            key=lambda item: item.value,
        )
    )
    policy.examples = list(arguments.example)
    engine = SessionEngine.create(
        root,
        mode=InteractionMode(arguments.mode),
        provider=provider,
        objective="Integrate this Nextflow pipeline with SPLICE.",
        policy=policy,
        actor=actor,
    )
    _write(folder / "session.json", {"session": engine.state.id})
    if arguments.mode == "assisted":
        asyncio.run(engine.assist(Stage(arguments.stage), actor, arguments.guidance))
    else:
        asyncio.run(engine.advance())
    state = engine.state
    _write(
        folder / "outcome.json",
        {
            "status": state.status.value,
            "stages": {
                stage.value: item.status.value for stage, item in state.stages.items()
            },
            "blockers": [item.model_dump(mode="json") for item in state.blockers],
            "pending": state.pending.model_dump(mode="json") if state.pending else None,
            "report": engine.report() if hasattr(engine, "report") else None,
        },
    )
    return 0


def _active(folder: Path, wait: float = 120.0) -> Path:
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        path = folder / "active.json"
        if path.is_file():
            name = json.loads(path.read_text("utf-8")).get("turn")
            if name:
                return folder / name
        if (folder / "outcome.json").is_file() or (folder / "answer.json").is_file():
            raise SystemExit("the session has finished: see outcome.json")
        time.sleep(POLL)
    raise SystemExit("no active turn")


def _submit(folder: Path, command: dict[str, Any], limit: int) -> int:
    turn = _active(folder)
    calls = turn / "calls"
    index = len(list(calls.glob("*.call.json"))) + 1
    path = calls / f"{index:03d}.call.json"
    _write(path, command)
    result_path = calls / f"{index:03d}.result.json"
    while not result_path.is_file():
        time.sleep(POLL)
    text = result_path.read_text("utf-8")
    print(text if len(text) <= limit else text[:limit] + f"\n… ({len(text)} chars)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("serve")
    run.add_argument("--repository", required=True)
    run.add_argument("--folder", required=True)
    run.add_argument("--mode", choices=["autonomous", "assisted"], default="autonomous")
    run.add_argument("--stage", default="identity")
    run.add_argument("--guidance", default="")
    run.add_argument("--grant", action="append", default=[])
    run.add_argument("--example", action="append", default=[])
    run.add_argument("--user", default="Context Evaluator")
    run.add_argument("--ask")
    run.add_argument("--page")
    status = commands.add_parser("status")
    status.add_argument("folder")
    call = commands.add_parser("call")
    call.add_argument("folder")
    call.add_argument("tool")
    call.add_argument("arguments", nargs="?", default="{}")
    call.add_argument("--limit", type=int, default=60_000)
    done = commands.add_parser("done")
    done.add_argument("folder")
    done.add_argument("message")
    arguments = parser.parse_args(argv)
    folder = Path(getattr(arguments, "folder", ".")).resolve()
    if arguments.command == "serve":
        return serve(arguments)
    if arguments.command == "status":
        turn = _active(folder, wait=10)
        request = json.loads((turn / "request.json").read_text("utf-8"))
        print(json.dumps({"turn": turn.name, **request["sizes"]}, indent=2))
        return 0
    if arguments.command == "call":
        return _submit(
            folder,
            {"tool": arguments.tool, "arguments": json.loads(arguments.arguments)},
            arguments.limit,
        )
    return _submit(folder, {"done": arguments.message}, 2_000)


if __name__ == "__main__":
    sys.exit(main())
