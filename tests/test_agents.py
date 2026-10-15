"""Provider-neutral, approval-gated agent integration (offline)."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import types
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from layer_fixtures import ready_identity, write_pipeline
from nf_splice.agents import (
    AgentMode,
    AgentPolicy,
    AgentToolbox,
    ConsentRequired,
    PolicyViolation,
    ProposalBook,
    ProposalStatus,
    approve,
    reject,
    run_agent,
)
from nf_splice.agents.protocol import AgentContext, EventKind
from nf_splice.agents.providers.claude import (
    ClaudeProvider,
    ClaudeSession,
    ProviderUnavailable,
)
from nf_splice.agents.providers.mock import ScriptedProvider
from nf_splice.cli import app as cli
from nf_splice.domain import Actor, ActorKind
from nf_splice.layers.base import load_review_state
from nf_splice.layers.inputs import import_inputs
from nf_splice.layers.outputs import discover_outputs, pending_candidates

runner = CliRunner()
REPORT = {
    "key": "report",
    "title": "Report",
    "description": "Job report.",
    "category": "job_report",
    "formats": ["html"],
    "scopes": ["job"],
    "entity_types": ["file"],
    "path_patterns": [r"^reports/report\.html$"],
}


def _repository(root: Path) -> dict[str, str]:
    write_pipeline(root)
    ready_identity(root)
    import_inputs(root)
    discover_outputs(root, schema_version="1.0.0")
    return {item.suggested_key: item.id for item in pending_candidates(root)}


def _drafts(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted((root / "splice" / "drafts").glob("*.yaml"))
    }


def _run(
    root: Path,
    steps: list[dict[str, Any]],
    book: ProposalBook,
    mode: AgentMode = AgentMode.SUGGEST,
) -> Any:
    return asyncio.run(
        run_agent(
            root, ScriptedProvider(steps), "help with outputs", mode=mode, book=book
        )
    )


def test_package_starts_without_the_optional_sdk(tmp_path: Path) -> None:
    code = (
        "import sys; sys.modules['claude_agent_sdk'] = None\n"
        "import nf_splice.cli, nf_splice.agents, nf_splice.interfaces.tui\n"
        "from nf_splice.agents.providers.claude import ClaudeProvider\n"
        "loaded = [m for m in sys.modules if sys.modules[m]]\n"
        "print('ok', 'claude_agent_sdk' in loaded)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "ok False"


def test_suggestions_never_mutate_until_a_human_approves(tmp_path: Path) -> None:
    ids = _repository(tmp_path)
    before = _drafts(tmp_path)
    book = ProposalBook()
    result = _run(
        tmp_path,
        [
            {"tool": "list_output_candidates"},
            {"message": "The report looks like a job-level MultiQC-style report."},
            {
                "tool": "propose_output_review",
                "arguments": {
                    "candidate_id": ids["report"],
                    "action": "accept",
                    "output": REPORT,
                    "rationale": "Published HTML report.",
                },
            },
            {
                "tool": "propose_output_review",
                "arguments": {
                    "candidate_id": "output:invented",
                    "action": "accept",
                    "output": REPORT,
                    "rationale": "x",
                },
            },
            {
                "tool": "propose_access",
                "arguments": {
                    "parameters": ["threshold"],
                    "editable_by": ["user", "agent"],
                    "rationale": "Scientific choice.",
                },
            },
        ],
        book,
    )
    assert _drafts(tmp_path) == before
    kinds = [event.kind for event in result.events]
    assert kinds.count(EventKind.PROPOSAL) == 2
    failed = [entry for entry in result.log if entry["outcome"] == "failed"]
    assert (
        len(failed) == 1 and failed[0]["arguments"]["candidate_id"] == "output:invented"
    )
    assert {item.status for item in result.proposals} == {ProposalStatus.PENDING}

    output_proposal = next(
        item for item in result.proposals if item.kind == "output_review"
    )
    access_proposal = next(item for item in result.proposals if item.kind == "access")
    approved = approve(tmp_path, book, output_proposal.id, Actor(label="Ada"))
    assert approved.status is ProposalStatus.APPLIED
    events = load_review_state(tmp_path, "outputs").events
    assert events[-1]["origin"] == "agent_suggestion"
    assert events[-1]["actor"] == {"label": "scripted", "kind": "agent"}
    assert events[-1]["approved_by"]["label"] == "Ada"
    reject(book, access_proposal.id, "Platform decides")
    assert book.get(access_proposal.id).status is ProposalStatus.REJECTED
    assert ids["report"] not in {item.id for item in pending_candidates(tmp_path)}
    with pytest.raises(PermissionError, match="human"):
        approve(
            tmp_path, book, access_proposal.id, Actor(label="bot", kind=ActorKind.AGENT)
        )


def test_escalation_attempts_are_denied_and_audited(tmp_path: Path) -> None:
    _repository(tmp_path)
    audit = tmp_path.parent / f"{tmp_path.name}-audit"  # never inside the repo
    os.environ["NF_SPLICE_AUDIT_DIR"] = str(audit)
    try:
        toolbox = AgentToolbox(
            tmp_path,
            AgentPolicy(repository=tmp_path, mode=AgentMode.ASK),
            provider="scripted",
        )
        for name, arguments in (
            ("Bash", {"command": "cat ~/.ssh/id_rsa"}),
            ("propose_patch", {"layer": "bundle", "operations": [], "rationale": "x"}),
            ("apply_approved_proposal", {"proposal_id": "proposal-x"}),
        ):
            result = toolbox.call(name, arguments)
            assert result["success"] is False and result["denied"] is True, name
        apply_mode = AgentToolbox(
            tmp_path,
            AgentPolicy(repository=tmp_path, mode=AgentMode.APPLY),
            provider="scripted",
        )
        assert apply_mode.call(
            "apply_approved_proposal", {"proposal_id": "proposal-x"}
        )["denied"]
    finally:
        os.environ.pop("NF_SPLICE_AUDIT_DIR")
    records = [
        json.loads(line)
        for path in audit.iterdir()
        for line in path.read_text().splitlines()
    ]
    assert {record["event"]["action"] for record in records} >= {
        "denied:Bash",
        "denied:propose_patch",
    }
    policy = AgentPolicy(repository=tmp_path, mode=AgentMode.ASK)
    for path in ("/etc/passwd", "../outside", "splice/../../x"):
        with pytest.raises(PolicyViolation):
            policy.check_path(path)


def test_remote_providers_need_explicit_consent(tmp_path: Path) -> None:
    _repository(tmp_path)
    with pytest.raises(ConsentRequired, match="allow-remote-model"):
        asyncio.run(
            run_agent(
                tmp_path, ClaudeProvider(), "x", mode=AgentMode.ASK, book=ProposalBook()
            )
        )
    with pytest.raises(PermissionError, match="off"):
        asyncio.run(
            run_agent(
                tmp_path,
                ScriptedProvider([]),
                "x",
                mode=AgentMode.OFF,
                book=ProposalBook(),
            )
        )


def _fake_sdk(calls: dict[str, Any]) -> types.ModuleType:
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
        num_turns: int = 1
        total_cost_usd: float = 0.0
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
            calls["options"] = kwargs
            self.__dict__.update(kwargs)

    class ClaudeSDKClient:
        def __init__(self, options: Any) -> None:
            self.options: Any = options

        async def __aenter__(self) -> ClaudeSDKClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def query(self, prompt: str) -> None:
            calls["prompt"] = prompt
            calls["bash"] = await self.options.can_use_tool(
                "Bash", {"command": "ls"}, None
            )
            calls["hook"] = await self.options.hooks["PreToolUse"][0].hooks[0](
                {"tool_name": "WebFetch"}, None, None
            )
            server = self.options.mcp_servers["nf_splice"]
            calls["tool_result"] = await server["tools"]["list_output_candidates"]({})

        async def receive_response(self) -> AsyncIterator[Any]:
            yield AssistantMessage(
                [
                    TextBlock("Here is what I found."),
                    ToolUseBlock("mcp__nf_splice__list_output_candidates", {}),
                ]
            )
            yield ResultMessage()

        async def interrupt(self) -> None:
            calls["interrupted"] = True

    for name, value in list(locals().items()):
        if not name.startswith("_") and name not in {"sdk", "calls"}:
            setattr(sdk, name, value)
    return sdk


def test_claude_adapter_is_least_privilege_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _repository(tmp_path)
    calls: dict[str, Any] = {}
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", _fake_sdk(calls))
    result = asyncio.run(
        run_agent(
            tmp_path,
            ClaudeProvider(),
            "suggest outputs",
            mode=AgentMode.SUGGEST,
            book=ProposalBook(),
            allow_remote=True,
        )
    )
    options = calls["options"]
    assert options["tools"] == []
    assert (
        "Bash" in options["disallowed_tools"]
        and "WebFetch" in options["disallowed_tools"]
    )
    assert options["setting_sources"] == [] and options["strict_mcp_config"] is True
    assert options["cwd"] == str(tmp_path.resolve())
    assert all(name.startswith("mcp__nf_splice__") for name in options["allowed_tools"])
    assert "mcp__nf_splice__apply_approved_proposal" not in options["allowed_tools"]
    assert calls["bash"].behavior == "deny"
    assert calls["hook"]["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert json.loads(calls["tool_result"]["content"][0]["text"])["success"] is True
    kinds = [event.kind for event in result.events]
    assert EventKind.MESSAGE in kinds and EventKind.TOOL_CALL in kinds
    assert {
        event.text for event in result.events if event.kind is EventKind.DENIED
    } == {"Bash", "WebFetch"}
    assert result.log[0]["tool"] == "list_output_candidates"


def test_missing_sdk_is_reported_honestly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _repository(tmp_path)
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", None)
    toolbox = AgentToolbox(
        tmp_path, AgentPolicy(repository=tmp_path, mode=AgentMode.ASK)
    )
    session = ClaudeSession(
        AgentContext(tmp_path, AgentMode.ASK, toolbox, "rules"), None
    )

    async def consume() -> None:
        async for _event in session.run("x"):
            pass

    with pytest.raises(ProviderUnavailable, match=r"nf-splice\[claude\]"):
        asyncio.run(consume())


def test_cli_agent_commands_require_human_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = _repository(tmp_path)
    monkeypatch.setenv("NF_SPLICE_SESSION_DIR", str(tmp_path / "sessions"))
    tools = runner.invoke(
        cli, ["agent", "tools", "--repository", str(tmp_path), "--mode", "ask"]
    )
    assert {item["name"] for item in json.loads(tools.output)} >= {
        "read_draft",
        "explain_term",
    }
    assert "propose_patch" not in tools.output
    script = tmp_path / "script.json"
    script.write_text(
        json.dumps(
            [
                {
                    "tool": "propose_output_review",
                    "arguments": {
                        "candidate_id": ids["report"],
                        "action": "accept",
                        "output": REPORT,
                        "rationale": "r",
                    },
                }
            ]
        ),
        encoding="utf-8",
    )
    ran = runner.invoke(
        cli,
        [
            "agent",
            "run",
            "help",
            "--provider",
            "scripted",
            "--script",
            str(script),
            "--repository",
            str(tmp_path),
        ],
    )
    assert ran.exit_code == 0, ran.output
    proposal = json.loads(ran.output)["proposals"][0]["id"]
    remote = runner.invoke(
        cli,
        ["agent", "run", "help", "--provider", "claude", "--repository", str(tmp_path)],
    )
    assert remote.exit_code == 2 and "allow-remote-model" in remote.output
    unattributed = runner.invoke(
        cli,
        ["agent", "approve", proposal, "--repository", str(tmp_path)],
        env={"NF_SPLICE_ACTOR": ""},
    )
    assert unattributed.exit_code == 2 and "human actor" in unattributed.output
    approved = runner.invoke(
        cli,
        ["--actor", "Ada", "agent", "approve", proposal, "--repository", str(tmp_path)],
    )
    assert approved.exit_code == 0, approved.output
    assert json.loads(approved.output)["status"] == "applied"
    listed = runner.invoke(cli, ["agent", "proposals", "--repository", str(tmp_path)])
    assert json.loads(listed.output)[0]["approved_by"] == "Ada"


@pytest.mark.asyncio
async def test_tui_assistant_panel_is_optional_and_preserves_state(
    tmp_path: Path,
) -> None:
    from textual.widgets import DataTable, Input

    from nf_splice.interfaces.tui import NfSpliceApp, SessionStore
    from nf_splice.interfaces.tui.screens.agent import AgentScreen
    from tui_helpers import settle

    ids = _repository(tmp_path)
    off = NfSpliceApp(tmp_path)
    async with off.run_test(size=(160, 60)) as pilot:
        await settle(off, pilot)
        await pilot.press("ctrl+a")
        await pilot.pause()
        assert isinstance(off.screen, AgentScreen)
        markdown = off.screen.query_one("Markdown")
        assert "Assistant is off" in str(getattr(markdown, "source", ""))
    provider = ScriptedProvider(
        [
            {
                "tool": "propose_output_review",
                "arguments": {
                    "candidate_id": ids["report"],
                    "action": "reject",
                    "reason": "Not published",
                    "rationale": "r",
                },
            }
        ]
    )
    on = NfSpliceApp(
        tmp_path,
        sessions=SessionStore(tmp_path / "sessions"),
        actor="Ada",
        agent_provider=provider,
    )
    async with on.run_test(size=(160, 60)) as pilot:
        await settle(on, pilot)
        on.show_step("identity")
        await settle(on, pilot)
        await pilot.press("ctrl+a")
        await pilot.pause()
        screen = on.screen
        assert isinstance(screen, AgentScreen)
        screen.query_one("#agent-prompt", Input).value = "review outputs"
        screen.query_one("#agent-run").press()  # type: ignore[attr-defined]
        await screen.workers.wait_for_complete()
        await pilot.pause()
        table = screen.query_one("#agent-proposals", DataTable)
        assert table.row_count == 1
        screen.query_one("#agent-approve").press()  # type: ignore[attr-defined]
        await settle(on, pilot)
        await pilot.press("escape")
        await pilot.pause()
        assert on.current == "identity"
    assert (
        load_review_state(tmp_path, "outputs").candidates[ids["report"]]["status"]
        == "rejected"
    )


@pytest.mark.live_agent
@pytest.mark.skipif(
    os.environ.get("NF_SPLICE_LIVE_AGENT") != "1",
    reason="opt-in: real Claude Agent SDK credentials and NF_SPLICE_LIVE_AGENT=1",
)
def test_live_claude_session_only_proposes(tmp_path: Path) -> None:
    pytest.importorskip("claude_agent_sdk")
    _repository(tmp_path)
    before = _drafts(tmp_path)
    book = ProposalBook()
    result = asyncio.run(
        run_agent(
            tmp_path,
            ClaudeProvider(),
            "List the output candidates and propose a review for one of them.",
            mode=AgentMode.SUGGEST,
            book=book,
            allow_remote=True,
        )
    )
    assert _drafts(tmp_path) == before
    assert not any(event.kind is EventKind.ERROR for event in result.events)
