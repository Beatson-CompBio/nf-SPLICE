"""CLI, wizard and provider-adapter parity for agentic sessions."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import types
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from layer_fixtures import ADA, ready_repository, review_turns
from multi_route import EXAMPLE, copy_fixture
from nf_splice.agents import (
    ExecutionPolicy,
    InteractionMode,
    ProviderUnavailable,
    SessionEngine,
    SessionStatus,
)
from nf_splice.agents.operations import READ_OPERATIONS
from nf_splice.agents.protocol import EventKind, TurnRequest
from nf_splice.agents.providers.claude import ClaudeProvider, ClaudeSession
from nf_splice.agents.stages import Stage
from nf_splice.agents.state import Usage, drafts_fingerprint
from nf_splice.agents.toolbox import SessionToolbox, ToolMode
from nf_splice.cli import app
from nf_splice.layers import ChangeContext
from nf_splice.services.lifecycle import validate_bundle

runner = CliRunner()


#: An output the scripted agent proposes to add (the catalogue is authored).
QC_SUMMARY = {
    "key": "qc_summary",
    "title": "QC summary",
    "description": "Per-job quality-control summary.",
    "category": "quality_control",
    "formats": ["json"],
    "scopes": ["job"],
    "entity_types": ["file"],
    "path_patterns": [r"^qc/summary\.json$"],
}


def _ready(root: Path) -> None:
    ready_repository(root)


def _cli(*arguments: str, actor: str | None = "Ada", **kwargs: Any) -> Any:
    prefix = ["--user", actor] if actor else []
    return runner.invoke(app, [*prefix, *arguments], **kwargs)


def test_cli_session_lifecycle(tmp_path: Path) -> None:
    root = tmp_path / "pipeline"
    root.mkdir()
    _ready(root)
    script = tmp_path / "script.json"
    script.write_text(
        json.dumps(
            [
                *review_turns("identity", "inputs"),
                {
                    "stage": "outputs",
                    "purpose": "plan",
                    "steps": [
                        {"tool": "analyse_routes", "arguments": {}},
                        {"tool": "route_coverage", "arguments": {}},
                        {"tool": "add_output", "arguments": {"output": QC_SUMMARY}},
                        {"follow": "review_scope"},
                        {
                            "tool": "submit_stage_proposal",
                            "arguments": {
                                "summary": "Add the QC summary output.",
                                "evidence": ["analyse_routes"],
                            },
                        },
                    ],
                },
                {
                    "purpose": "question",
                    "steps": [{"message": "qc/summary.json is the job QC summary."}],
                },
                *review_turns("components", "profiles", "provenance"),
            ]
        ),
        encoding="utf-8",
    )
    repository = ["--repository", str(root)]
    started = _cli(
        "session",
        "start",
        "--mode",
        "assisted",
        "--provider",
        "scripted",
        "--script",
        str(script),
        "--no-interactive",
        "--json",
        *repository,
    )
    assert started.exit_code == 0, started.output
    status = json.loads(started.output)
    assert status["status"] == "awaiting_approval"
    assert status["pending"]["stage"] == "outputs"
    assert status["stages"]["identity"] == "completed"

    asked = _cli("session", "ask", "What is it?", *repository)
    assert "job QC summary" in asked.output

    unattributed = _cli(
        "session", "approve", *repository, actor=None, env={"NF_SPLICE_USER": ""}
    )
    assert unattributed.exit_code == 2
    assert "person's name" in unattributed.output

    approved = _cli("session", "approve", "--json", *repository)
    assert approved.exit_code == 0, approved.output
    assert json.loads(approved.output)["pending"]["stage"] == "build"

    paused = _cli("session", "resume", "--mode", "manual", *repository)
    assert "paused for manual work" in paused.output
    resumed = _cli(
        "session",
        "resume",
        "--mode",
        "assisted",
        "--no-interactive",
        "--json",
        *repository,
    )
    assert json.loads(resumed.output)["pending"]["stage"] == "build"
    built = _cli("session", "approve", *repository)
    assert built.exit_code == 0, built.output
    assert validate_bundle(root).valid

    report = _cli("session", "report", *repository)
    assert "complete" in report.output and "Verified artefacts:" in report.output
    listed = _cli("session", "list", *repository)
    assert "assisted" in listed.output and "completed" in listed.output
    tools = json.loads(_cli("session", "tools", "--stage", "outputs").output)
    names = {item["name"] for item in tools}
    assert {
        "replace_draft",
        "add_output",
        "route_coverage",
        "read_source",
        "submit_stage_proposal",
        "complete_review",
    } <= names
    assert "build_bundle" not in names
    # The candidate queue is gone (ADR-0068).
    assert not names & {"accept_output", "reject_output", "merge_outputs"}

    remote = _cli("ask", "x", "--provider", "claude", *repository)
    assert remote.exit_code == 2 and "allow-remote-model" in remote.output
    # The workspace asks for this consent in its AI dock instead
    # (tests/test_tui_agents.py).


def test_cli_conversation_in_the_terminal(tmp_path: Path) -> None:
    root = tmp_path / "pipeline"
    root.mkdir()
    _ready(root)
    script = tmp_path / "script.json"
    script.write_text(
        json.dumps(
            [
                {"purpose": "plan", "steps": [{"message": "I need your view first."}]},
                {"purpose": "question", "steps": [{"message": "It is QC output."}]},
            ]
        ),
        encoding="utf-8",
    )
    result = _cli(
        "session",
        "start",
        "--provider",
        "scripted",
        "--script",
        str(script),
        "--interactive",
        "--repository",
        str(root),
        input="q\nWhat is qc/summary.json?\np\n",
    )
    assert result.exit_code == 0, result.output
    assert "I need your view first." in result.output
    assert "It is QC output." in result.output
    status = json.loads(
        _cli("session", "status", "--json", "--repository", str(root)).output
    )
    assert status["status"] == "paused"


def test_cli_ask_and_skills(tmp_path: Path) -> None:
    root = tmp_path / "pipeline"
    root.mkdir()
    ready_repository(root)
    script = tmp_path / "help.json"
    script.write_text(
        json.dumps(
            [
                {
                    "steps": [
                        {"tool": "inspect_draft", "arguments": {"layer": "outputs"}},
                        {"tool": "add_output", "arguments": {}},
                        {"message": "The outputs draft is ready."},
                    ]
                }
            ]
        ),
        encoding="utf-8",
    )
    before = drafts_fingerprint(root)
    answer = _cli(
        "ask",
        "Is my outputs draft ready?",
        "--provider",
        "scripted",
        "--script",
        str(script),
        "--layer",
        "outputs",
        "--json",
        "--repository",
        str(root),
    )
    assert answer.exit_code == 0, answer.output
    document = json.loads(answer.output)
    assert document["answer"] == "The outputs draft is ready."
    assert document["denied"]
    assert drafts_fingerprint(root) == before

    listed = _cli("skills", "list")
    assert "nf-splice-output-discovery" in listed.output
    destination = tmp_path / ".claude" / "skills"
    exported = _cli("skills", "export", "--dest", str(destination))
    assert exported.exit_code == 0
    canonical = Path(__file__).parent.parent / "skills"
    for path in canonical.glob("*/SKILL.md"):
        target = destination / path.parent.name / "SKILL.md"
        assert target.read_bytes() == path.read_bytes()


# ------------------------------------------------------------ Claude adapter


@dataclass
class _Calls:
    options: list[dict[str, Any]] = field(default_factory=list)
    steps: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    results: list[Any] = field(default_factory=list)
    denied: list[Any] = field(default_factory=list)


def _fake_sdk(calls: _Calls) -> types.ModuleType:
    sdk = types.ModuleType("claude_agent_sdk")

    @dataclass
    class TextBlock:
        text: str

    @dataclass
    class ToolUseBlock:
        name: str
        input: dict[str, Any]

    @dataclass
    class AssistantMessage:
        content: list[Any]

    @dataclass
    class ResultMessage:
        session_id: str = "claude-session-1"
        num_turns: int = 1
        total_cost_usd: float = 0.01
        is_error: bool = False

    @dataclass
    class PermissionResultAllow:
        behavior: str = "allow"

    @dataclass
    class PermissionResultDeny:
        message: str = ""
        behavior: str = "deny"

    @dataclass
    class HookMatcher:
        matcher: str | None = None
        hooks: list[Any] = field(default_factory=list)

    @dataclass
    class Tool:
        name: str
        handler: Any

    def tool(name: str, description: str, schema: dict[str, Any]) -> Any:
        return lambda handler: Tool(name, handler)

    def create_sdk_mcp_server(name: str, tools: list[Tool]) -> dict[str, Any]:
        return {"name": name, "tools": {item.name: item.handler for item in tools}}

    class ClaudeAgentOptions:
        def __init__(self, **kwargs: Any) -> None:
            calls.options.append(kwargs)
            self.__dict__.update(kwargs)

    class ClaudeSDKClient:
        def __init__(self, options: Any) -> None:
            self.options: Any = options

        async def __aenter__(self) -> ClaudeSDKClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def query(self, prompt: str) -> None:
            calls.denied.append(
                await self.options.can_use_tool("Bash", {"command": "ls"}, None)
            )
            calls.denied.append(
                await self.options.hooks["PreToolUse"][0].hooks[0](
                    {"tool_name": "WebFetch"}, None, None
                )
            )
            server = self.options.mcp_servers["nf_splice"]
            for name, arguments in calls.steps:
                handler = server["tools"].get(name)
                calls.results.append(
                    None if handler is None else await handler(arguments)
                )

        async def receive_response(self) -> AsyncIterator[Any]:
            yield AssistantMessage(
                [
                    TextBlock("Staged the identity."),
                    ToolUseBlock("mcp__nf_splice__x", {}),
                ]
            )
            yield ResultMessage()

        async def interrupt(self) -> None:
            return None

    for name, value in list(locals().items()):
        if not name.startswith("_") and name not in {"sdk", "calls"}:
            setattr(sdk, name, value)
    return sdk


def test_claude_adapter_is_least_privilege_and_resumes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = copy_fixture(tmp_path)
    calls = _Calls()
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", _fake_sdk(calls))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-not-real")
    from multi_route import IDENTITY

    engine = SessionEngine.create(
        root,
        mode=InteractionMode.ASSISTED,
        provider=ClaudeProvider(),
        objective="x",
        policy=ExecutionPolicy(allow_remote_model=True, examples=[str(EXAMPLE)]),
        actor=ADA.actor,
    )
    asyncio.run(engine.advance())
    asyncio.run(engine.approve(ADA.actor))  # deterministic discover
    calls.steps = [
        ("workspace_status", {}),
        ("set_identity", {"changes": dict(IDENTITY)}),
        ("build_bundle", {}),
        (
            "add_assay_capability",
            {
                "reference": "polya_rnaseq",
                "evidence": "documented",
                "rationale": "docs/usage.md documents poly(A) libraries.",
                "sources": ["docs/usage.md:3"],
            },
        ),
        ("submit_stage_proposal", {"summary": "Complete the identity."}),
    ]
    asyncio.run(engine.advance())
    options = calls.options[-1]
    assert options["tools"] == []
    assert {"Bash", "WebFetch", "Read", "Write", "Skill"} <= set(
        options["disallowed_tools"]
    )
    assert options["setting_sources"] == [] and options["strict_mcp_config"] is True
    # A Console API key only, with a private config folder; never a login.
    env = options["env"]
    assert env["ANTHROPIC_API_KEY"] == "sk-ant-test-not-real"
    assert env["CLAUDE_CODE_OAUTH_TOKEN"] == "" and env["ANTHROPIC_AUTH_TOKEN"] == ""
    assert Path(env["CLAUDE_CONFIG_DIR"]) != Path.home() / ".claude"
    assert all(name.startswith("mcp__nf_splice__") for name in options["allowed_tools"])
    assert "mcp__nf_splice__build_bundle" not in options["allowed_tools"]
    assert "nf-splice-agent-operations" in options["system_prompt"]
    assert calls.denied[0].behavior == "deny"
    assert calls.denied[1]["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert calls.results[2] is None  # build_bundle is not even offered here
    proposal = engine.state.pending
    assert proposal is not None and proposal.stage is Stage.IDENTITY
    assert engine.state.provider.conversation_ref == "claude-session-1"
    assert engine.state.usage.cost_usd > 0

    calls.steps = []
    asyncio.run(engine.ask("Why?", ADA.actor))
    assert calls.options[-1]["resume"] == "claude-session-1"
    asyncio.run(engine.approve(ADA.actor))
    assert engine.state.stages[Stage.IDENTITY].status.value == "completed"


def test_missing_sdk_is_reported_honestly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", None)
    toolbox = SessionToolbox(
        root=tmp_path,
        policy=ExecutionPolicy(allow_remote_model=True),
        mode=ToolMode.OBSERVE,
        operations=set(READ_OPERATIONS),
        controls=set(),
        change=ChangeContext(actor=ADA.actor),
        usage=Usage(),
    )
    session = ClaudeSession(tmp_path, None)
    request = TurnRequest(
        purpose="help", instruction="x", system_prompt="s", tools=toolbox
    )

    async def consume() -> None:
        async for _event in session.turn(request):
            pass

    with pytest.raises(ProviderUnavailable, match=r"nf-splice\[claude\]"):
        asyncio.run(consume())
    assert EventKind.USAGE.value == "usage"


@pytest.mark.live_agent
@pytest.mark.skipif(
    os.environ.get("NF_SPLICE_LIVE_AGENT") != "1",
    reason="opt-in: real Claude Agent SDK credentials and NF_SPLICE_LIVE_AGENT=1",
)
def test_live_claude_assisted_session_proposes_without_changing_files(
    tmp_path: Path,
) -> None:
    pytest.importorskip("claude_agent_sdk")
    root = copy_fixture(tmp_path)
    engine = SessionEngine.create(
        root,
        mode=InteractionMode.ASSISTED,
        provider=ClaudeProvider(),
        objective="Integrate this pipeline with SPLICE.",
        policy=ExecutionPolicy(allow_remote_model=True, examples=[str(EXAMPLE)]),
        actor=ADA.actor,
    )
    asyncio.run(engine.advance())
    asyncio.run(engine.approve(ADA.actor))
    before = drafts_fingerprint(root)
    asyncio.run(engine.advance())
    assert drafts_fingerprint(root) == before
    assert engine.state.status in {
        SessionStatus.AWAITING_APPROVAL,
        SessionStatus.AWAITING_INPUT,
    }
