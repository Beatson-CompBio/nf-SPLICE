"""The workspace with AI: Ask, Assist and autonomy over real sessions (ADR-0067).

A scripted provider stands in for the model. It calls nf-splice's real tools,
so every draft change goes through the toolbox and the services and every
outcome is decided by the validators. The tests prove orchestration, safety
and the interface's states, never model reasoning.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from textual.widgets import Button, Checkbox, Input, Markdown, TextArea

from agent_scripts import RouteAgent, outputs
from layer_fixtures import ADA, follow_scope
from multi_route import copy_fixture
from nf_splice.agents import Permission, SessionStatus, SessionStore
from nf_splice.agents.protocol import ProviderCapabilities, ToolInvoker, TurnRequest
from nf_splice.agents.providers.scripted import ScriptedProvider
from nf_splice.interfaces.tui import NfSpliceApp
from nf_splice.interfaces.tui.coordinator import AgentState
from nf_splice.interfaces.tui.modals import ConfirmDialog, QuitDialog
from nf_splice.layers.base import read_layer
from nf_splice.services.workspace import initialise
from tui_helpers import press, screenshot, settle, wait_agent

pytestmark = pytest.mark.asyncio
WIDE = (180, 50)
DRAFTS = ".splice-local/drafts"


def _drafts(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted((root / DRAFTS).rglob("*"))
        if path.is_file()
    }


def _prepared(tmp_path: Path) -> Path:
    root = copy_fixture(tmp_path)
    initialise(root, ADA)
    return root


def _outputs(root: Path) -> list[dict[str, Any]]:
    state = read_layer(root, "outputs")
    assert state.draft is not None
    return list(state.draft.data.get("outputs") or [])


@dataclass(slots=True)
class Gate:
    """Holds an agent turn until the test releases it (a slow model)."""

    entered: threading.Event
    release: threading.Event

    @classmethod
    def new(cls) -> Gate:
        return cls(threading.Event(), threading.Event())

    def hold(self, request: TurnRequest, tools: ToolInvoker) -> list[str]:
        self.entered.set()
        assert self.release.wait(30), "the test never released the agent"
        return RouteAgent()(request, tools)


async def _until(app: NfSpliceApp, pilot: Any, event: threading.Event) -> None:
    for _ in range(600):
        if event.is_set():
            break
        await pilot.pause(0.02)
    assert event.is_set()
    await pilot.pause()
    app._agent_changed()


class _Remote(ScriptedProvider):
    """A scripted provider that declares remote inference (consent needed)."""

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name="remote-scripted",
            remote=True,
            tool_calling=True,
            streaming=True,
            cancellation=True,
            budgets=False,
            continuation=False,
            reasoning_control="scripted (no model)",
            reasoning_efforts=(),
        )


class _NoTools(ScriptedProvider):
    """A provider that cannot call structured tools."""

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name="chat-only",
            remote=False,
            tool_calling=False,
            streaming=True,
            cancellation=True,
            budgets=False,
            continuation=False,
            reasoning_control="none",
            reasoning_efforts=(),
        )


# ------------------------------------------------------------ off and Ask


async def test_ai_off_keeps_every_manual_path_and_says_how_to_configure(
    tmp_path: Path,
) -> None:
    root = _prepared(tmp_path)
    app = NfSpliceApp(root, user="Ada", start="outputs")
    async with app.run_test(size=WIDE) as pilot:
        await settle(app, pilot)
        snapshot = app.coordinator.snapshot()
        assert snapshot.state is AgentState.OFF
        assert "No AI provider is configured" in snapshot.unavailable
        app.open_dock("assist")
        await settle(app, pilot)
        assert app.query_one("#assist-start", Button).disabled
        assert app.query_one("#auto-start", Button).disabled
        assert "No AI provider" in str(
            app.query_one("#dock-access-text", Markdown).source
        )
        assert app.coordinator.engine is None
        assert app.query_one("#provider-configure").display
        # The manual editor is unaffected.
        assert app.screen.query_one("#outputs-add")


async def test_ask_answers_with_read_only_tools_and_changes_nothing(
    tmp_path: Path,
) -> None:
    root = _prepared(tmp_path)
    agent = RouteAgent()
    before = _drafts(root)
    app = NfSpliceApp(
        root, user="Ada", start="identity", agent_provider=ScriptedProvider(agent)
    )
    async with app.run_test(size=WIDE) as pilot:
        await settle(app, pilot)
        await press(app, pilot, "#ask-identity")
        dock = app.query_one("#dock")
        assert dock.display
        dock.query_one("#ask-question", TextArea).text = "What is missing?"
        await press(app, pilot, "#ask-send")
        await wait_agent(app, pilot)
        snapshot = app.coordinator.snapshot()
        assert snapshot.answer.startswith("Layers:")
        assert snapshot.answer_question == "What is missing?"
        assert app.coordinator.engine is None  # Ask never opens a session
    assert ("help", None) in agent.seen or ("question", None) in agent.seen
    assert _drafts(root) == before


# ------------------------------------------------------------ Assist


def _skip_star(request: TurnRequest, tools: ToolInvoker) -> list[str]:
    """Plan the outputs stage, but catalogue every route except STAR's."""
    outputs(tools, skip=["star_alignment", "star_log"])
    follow_scope(tools)
    tools.call(
        "submit_stage_proposal",
        {
            "summary": "Catalogue the QC outputs.",
            "evidence": ["analyse_routes"],
            "uncertainties": ["STAR alignment is not described yet."],
        },
    )
    return ["Prepared the outputs stage."]


async def test_assist_proposes_then_applies_only_after_approval(
    tmp_path: Path,
) -> None:
    root = _prepared(tmp_path)
    app = NfSpliceApp(
        root,
        user="Ada",
        start="outputs",
        agent_provider=ScriptedProvider(RouteAgent()),
    )
    async with app.run_test(size=WIDE) as pilot:
        await settle(app, pilot)
        assert _outputs(root) == []
        await press(app, pilot, "#assist-outputs")
        assert app.query_one("#assist-idle").display
        await press(app, pilot, "#assist-start")
        await wait_agent(app, pilot)
        snapshot = app.coordinator.snapshot()
        assert snapshot.state is AgentState.PROPOSAL
        assert snapshot.proposal is not None
        assert snapshot.proposal.stage == "outputs"
        assert ".splice-local/drafts/outputs.draft.yaml" in "\n".join(
            snapshot.proposal.changed_files
        )
        assert _outputs(root) == []  # nothing applied before approval
        assert app.query_one("#assist-proposal").display
        await press(app, pilot, "#proposal-approve")
        await wait_agent(app, pilot)
        assert _outputs(root), "the approved catalogue was not written"
        # The page shows the new catalogue without Ctrl+R.
        assert app.model.outputs and {row.key for row in app.model.outputs} == {
            item["key"] for item in _outputs(root)
        }
        engine = app.coordinator.engine
        assert engine is not None
        approval = engine.state.approvals[-1]
        assert (approval.decision, approval.actor) == ("approved", "Ada")


async def test_a_proposal_made_before_a_manual_edit_is_never_applied(
    tmp_path: Path,
) -> None:
    root = _prepared(tmp_path)
    app = NfSpliceApp(
        root,
        user="Ada",
        start="outputs",
        agent_provider=ScriptedProvider(RouteAgent()),
    )
    async with app.run_test(size=WIDE) as pilot:
        await settle(app, pilot)
        await press(app, pilot, "#assist-outputs")
        assert app.query_one("#assist-idle").display
        await press(app, pilot, "#assist-start")
        await wait_agent(app, pilot)
        assert app.coordinator.snapshot().state is AgentState.PROPOSAL
        draft = root / DRAFTS / "outputs.draft.yaml"
        draft.write_text(
            draft.read_text(encoding="utf-8") + "# edited by hand\n", encoding="utf-8"
        )
        edited = draft.read_bytes()
        await press(app, pilot, "#proposal-approve")
        await wait_agent(app, pilot)
        assert draft.read_bytes() == edited
        assert app.coordinator.snapshot().proposal is None


async def test_rejecting_a_proposal_withdraws_it_and_records_the_person(
    tmp_path: Path,
) -> None:
    root = _prepared(tmp_path)
    app = NfSpliceApp(
        root,
        user="Ada",
        start="outputs",
        agent_provider=ScriptedProvider(
            RouteAgent(overrides={"plan:outputs": _skip_star})
        ),
    )
    async with app.run_test(size=WIDE) as pilot:
        await settle(app, pilot)
        await press(app, pilot, "#assist-outputs")
        assert app.query_one("#assist-idle").display
        await press(app, pilot, "#assist-start")
        await wait_agent(app, pilot)
        proposal = app.coordinator.snapshot().proposal
        assert proposal is not None
        assert "STAR alignment is not described yet." in proposal.uncertainties
        app.query_one("#proposal-revision", TextArea).text = "Describe STAR too."
        await press(app, pilot, "#proposal-reject")
        assert app.coordinator.snapshot().proposal is None
        assert _outputs(root) == []
        engine = app.coordinator.engine
        assert engine is not None
        assert engine.state.approvals[-1].decision == "rejected"
        assert engine.state.approvals[-1].actor == "Ada"
        assert engine.state.approvals[-1].note == "Describe STAR too."


async def test_assist_needs_a_named_person(tmp_path: Path) -> None:
    root = _prepared(tmp_path)
    app = NfSpliceApp(
        root, start="outputs", agent_provider=ScriptedProvider(RouteAgent())
    )
    async with app.run_test(size=WIDE) as pilot:
        await settle(app, pilot)
        with pytest.MonkeyPatch.context() as patch:
            patch.delenv("NF_SPLICE_USER", raising=False)
            await press(app, pilot, "#assist-outputs")
            await press(app, pilot, "#assist-start")
            assert app.coordinator.engine is None
            assert "enter your name first" in str(
                app.query_one("#status-message").render()
            )
            person = app.query_one("#dock-person", Input)
            person.value = "Ada"
            await person.action_submit()
            await settle(app, pilot)
            await press(app, pilot, "#assist-start")
            await wait_agent(app, pilot)
            assert app.coordinator.snapshot().state is AgentState.PROPOSAL


# ------------------------------------------------------------ autonomy


def _blocked_outputs(request: TurnRequest, tools: ToolInvoker) -> list[str]:
    outputs(tools, skip=["quant"])
    tools.call(
        "record_blocker",
        {
            "decision": "Whether Salmon quantification is a platform output",
            "artefact": ".splice-local/drafts/outputs.draft.yaml",
            "pointer": "/outputs",
            "attempted_checks": ["analyse_routes", "route_coverage"],
            "suggested_resolution": "Describe quant.sf or exclude its route.",
        },
    )
    return ["I cannot decide about Salmon from the evidence."]


async def test_an_intervention_opens_the_field_and_resumes_the_same_session(
    tmp_path: Path,
) -> None:
    root = _prepared(tmp_path)
    agent = RouteAgent(overrides={"execute:outputs": _blocked_outputs})
    app = NfSpliceApp(
        root, user="Ada", start="overview", agent_provider=ScriptedProvider(agent)
    )
    async with app.run_test(size=WIDE) as pilot:
        await settle(app, pilot)
        app.open_dock("autonomous")
        await settle(app, pilot)
        assert not app.query_one("#grant-build", Checkbox).value  # never implied
        await press(app, pilot, "#auto-start")
        await wait_agent(app, pilot)
        snapshot = app.coordinator.snapshot()
        assert snapshot.state is AgentState.AWAITING_YOU
        assert Permission.BUILD.value not in snapshot.grants
        session = snapshot.session_id
        [intervention] = snapshot.interventions
        assert intervention.stage == "outputs"
        assert intervention.pointer == "/outputs"
        assert intervention.target.page == "outputs"
        assert app.query_one("#auto-intervention").display
        await press(app, pilot, "#intervention-open")
        assert app.current == "outputs"
        # The person describes the remaining output by hand, then resumes.
        agent.overrides.clear()
        app.query_one("#intervention-note", TextArea).text = "Salmon is out of scope."
        await press(app, pilot, "#intervention-resume")
        await wait_agent(app, pilot)
        snapshot = app.coordinator.snapshot()
        assert snapshot.session_id == session  # the same session continued
        engine = app.coordinator.engine
        assert engine is not None
        first = engine.state.blockers[0]
        assert first.resolved and first.resolution == "Salmon is out of scope."
        # Without the separate build grant the session stops before publishing
        # and says so, rather than publishing anyway.
        assert [item.stage.value for item in engine.open_interventions()] == ["build"]
        assert "build permission" in engine.open_interventions()[0].decision
        assert not (root / "splice" / "bundle.json").exists()
        assert engine.state.status is not SessionStatus.CANCELLED


async def test_pause_is_requested_until_the_agent_stops_and_locks_manual_writes(
    tmp_path: Path,
) -> None:
    root = _prepared(tmp_path)
    gate = Gate.new()
    agent = RouteAgent(overrides={"execute:identity": gate.hold})
    app = NfSpliceApp(
        root, user="Ada", start="identity", agent_provider=ScriptedProvider(agent)
    )
    async with app.run_test(size=WIDE) as pilot:
        await settle(app, pilot)
        app.open_dock("autonomous")
        await settle(app, pilot)
        await press(app, pilot, "#auto-start")
        await _until(app, pilot, gate.entered)
        assert app.coordinator.snapshot().state is AgentState.RUNNING
        assert app.coordinator.writes_locked()
        # Closing the dock is presentation only.
        app.action_close_dock()
        await pilot.pause()
        assert app.coordinator.busy
        # A manual save while the agent may write offers a takeover instead.
        app.screen.query_one("#identity-version", Input).value = "9.9.9"
        before = _drafts(root)
        app.screen.query_one("#identity-save", Button).press()
        await pilot.pause()
        assert isinstance(app.screen, ConfirmDialog)
        await press(app, pilot, "#confirm-ok")
        assert app.coordinator.snapshot().state is AgentState.PAUSE_REQUESTED
        assert _drafts(root) == before
        gate.release.set()
        await wait_agent(app, pilot)
        assert app.coordinator.snapshot().state is AgentState.PAUSED
        assert not app.coordinator.writes_locked()
        # The agent changed the draft before pausing, so the form is stale:
        # reload, then the person's edit is written.
        await press(app, pilot, "#identity-save")
        await press(app, pilot, "#list-reload")
        await settle(app, pilot)
        app.screen.query_one("#identity-version", Input).value = "9.9.9"
        await press(app, pilot, "#identity-save")
        state = read_layer(root, "bundle")
        assert state.draft is not None
        assert state.draft.data["pipeline"]["version"] == "9.9.9"


async def test_stop_is_final_and_a_restart_never_reopens_it(tmp_path: Path) -> None:
    root = _prepared(tmp_path)
    gate = Gate.new()
    agent = RouteAgent(overrides={"execute:identity": gate.hold})
    app = NfSpliceApp(
        root, user="Ada", start="overview", agent_provider=ScriptedProvider(agent)
    )
    async with app.run_test(size=WIDE) as pilot:
        await settle(app, pilot)
        app.open_dock("autonomous")
        await settle(app, pilot)
        await press(app, pilot, "#auto-start")
        await _until(app, pilot, gate.entered)
        await press(app, pilot, "#auto-stop")
        assert isinstance(app.screen, ConfirmDialog)
        await press(app, pilot, "#confirm-ok")
        gate.release.set()
        await wait_agent(app, pilot)
        assert app.coordinator.snapshot().state is AgentState.STOPPED
        session = app.coordinator.snapshot().session_id
    [record] = SessionStore(root).sessions()
    assert record.id == session and record.status is SessionStatus.CANCELLED
    again = NfSpliceApp(
        root,
        user="Ada",
        start="overview",
        agent_provider=ScriptedProvider(RouteAgent()),
    )
    async with again.run_test(size=WIDE) as pilot:
        await settle(again, pilot)
        assert again.coordinator.engine is None
        assert again.coordinator.snapshot().state is AgentState.READY


async def test_a_paused_session_is_reopened_after_a_restart(tmp_path: Path) -> None:
    root = _prepared(tmp_path)
    gate = Gate.new()
    agent = RouteAgent(overrides={"execute:identity": gate.hold})
    app = NfSpliceApp(
        root, user="Ada", start="overview", agent_provider=ScriptedProvider(agent)
    )
    async with app.run_test(size=WIDE) as pilot:
        await settle(app, pilot)
        app.open_dock("autonomous")
        await settle(app, pilot)
        await press(app, pilot, "#auto-start")
        await _until(app, pilot, gate.entered)
        await press(app, pilot, "#auto-pause")
        gate.release.set()
        await wait_agent(app, pilot)
        session = app.coordinator.snapshot().session_id
    again = NfSpliceApp(
        root,
        user="Ada",
        start="overview",
        agent_provider=ScriptedProvider(RouteAgent()),
    )
    async with again.run_test(size=WIDE) as pilot:
        await settle(again, pilot)
        snapshot = again.coordinator.snapshot()
        assert snapshot.session_id == session
        assert snapshot.state is AgentState.PAUSED
        assert "PAUSED" in str(again.query_one("#agent-status", Button).label)


async def test_quitting_while_the_agent_works_waits_for_a_safe_pause(
    tmp_path: Path,
) -> None:
    root = _prepared(tmp_path)
    gate = Gate.new()
    agent = RouteAgent(overrides={"execute:identity": gate.hold})
    app = NfSpliceApp(
        root, user="Ada", start="overview", agent_provider=ScriptedProvider(agent)
    )
    async with app.run_test(size=WIDE) as pilot:
        await settle(app, pilot)
        app.open_dock("autonomous")
        await settle(app, pilot)
        await press(app, pilot, "#auto-start")
        await _until(app, pilot, gate.entered)
        app.action_quit_safely()
        await pilot.pause()
        assert isinstance(app.screen, QuitDialog)
        app.screen.query_one("#quit-pause", Button).press()
        await pilot.pause()
        gate.release.set()
        for _ in range(600):
            if not app.is_running:
                break
            await pilot.pause(0.02)
    [record] = SessionStore(root).sessions()
    assert record.status is SessionStatus.PAUSED


# ------------------------------------------------------------ providers


async def test_a_remote_provider_needs_consent_in_the_dock(tmp_path: Path) -> None:
    root = _prepared(tmp_path)
    before = _drafts(root)
    app = NfSpliceApp(
        root, user="Ada", start="identity", agent_provider=_Remote(RouteAgent())
    )
    async with app.run_test(size=WIDE) as pilot:
        await settle(app, pilot)
        assert app.coordinator.snapshot().consent_needed
        app.open_dock("ask")
        await settle(app, pilot)
        assert app.query_one("#dock-access").display
        assert app.query_one("#ask-send", Button).disabled
        assert (
            "consent"
            in str(app.query_one("#dock-access-text", Markdown).source).lower()
        )
        app.query_one("#dock-consent", Checkbox).value = True
        await settle(app, pilot)
        assert not app.coordinator.snapshot().consent_needed
        await press(app, pilot, "#ask-send")
        await wait_agent(app, pilot)
        assert app.coordinator.snapshot().answer.startswith("Layers:")
    assert _drafts(root) == before


async def test_a_provider_without_tool_calling_is_refused(tmp_path: Path) -> None:
    root = _prepared(tmp_path)
    app = NfSpliceApp(
        root, user="Ada", start="identity", agent_provider=_NoTools(RouteAgent())
    )
    async with app.run_test(size=WIDE) as pilot:
        await settle(app, pilot)
        snapshot = app.coordinator.snapshot()
        assert "cannot call nf-splice's structured tools" in snapshot.unavailable
        app.open_dock("assist")
        await settle(app, pilot)
        assert app.query_one("#assist-start", Button).disabled
        assert app.coordinator.engine is None


# ------------------------------------------------------------ takeover sizes


def _needs_salmon_decision(request: TurnRequest, tools: ToolInvoker) -> list[str]:
    outputs(tools, skip=["quant"])
    tools.call(
        "record_blocker",
        {
            "decision": "Whether Salmon quantification is a platform output",
            "reason": "The workflow runs Salmon only when a parameter enables it, "
            "and the documentation does not say whether users need its files.",
            "uncertainties": ["Whether quant.sf is used downstream by the platform"],
            "artefact": ".splice-local/drafts/outputs.draft.yaml",
            "pointer": "/outputs",
            "attempted_checks": ["analyse_routes", "route_coverage", "main.nf:12"],
            "suggested_resolution": "Describe quant.sf or exclude its route.",
        },
    )
    return ["I cannot decide about Salmon from the evidence."]


@pytest.mark.parametrize("size", [(80, 30), (120, 40)], ids=["80x30", "120x40"])
async def test_a_narrow_takeover_edits_the_field_and_resumes_the_same_session(
    tmp_path: Path, size: tuple[int, int]
) -> None:
    from textual.widgets import Static

    root = _prepared(tmp_path)
    agent = RouteAgent(overrides={"execute:outputs": _needs_salmon_decision})
    app = NfSpliceApp(
        root, user="Ada", start="overview", agent_provider=ScriptedProvider(agent)
    )
    async with app.run_test(size=size) as pilot:
        await settle(app, pilot)
        assert app.stacked
        app.open_dock("autonomous")
        await settle(app, pilot)
        await press(app, pilot, "#auto-start")
        await wait_agent(app, pilot)
        snapshot = app.coordinator.snapshot()
        assert snapshot.state is AgentState.AWAITING_YOU
        session = snapshot.session_id
        # The AI panel takes the full width; the card reads as plain sentences.
        dock = app.query_one("#dock")
        assert dock.display and dock.size.width >= size[0] - 2
        text = str(app.query_one("#intervention-text", Static).render())
        for heading in (
            "What I need from you",
            "Why I cannot decide",
            "What I examined",
            "Still uncertain",
            "What to do next",
        ):
            assert heading in text
        assert "replace_draft" not in text and "{" not in text
        details = str(app.query_one("#intervention-diagnostics-text", Static).render())
        assert "operation:" in details or "agent check:" in details
        screenshot(app, f"takeover-card-{size[0]}x{size[1]}")
        # Open the field: the page takes the full width, the bar stays.
        await press(app, pilot, "#intervention-open")
        assert app.current == "outputs"
        assert not dock.display
        assert app.query_one("#takeover-bar").display
        screenshot(app, f"takeover-page-{size[0]}x{size[1]}")
        # Unsaved values are never lost, and never resumed over.
        app.show_page("identity")
        await settle(app, pilot)
        app.screen.query_one("#identity-version", Input).value = "9.9.9"
        await press(app, pilot, "#takeover-resume")
        assert "Save or discard" in str(app.query_one("#status-message").render())
        assert app.coordinator.snapshot().state is AgentState.AWAITING_YOU
        await pilot.press("f6")
        await pilot.pause()
        assert dock.display
        await pilot.press("f6")
        await pilot.pause()
        assert not dock.display
        assert app.screen.query_one("#identity-version", Input).value == "9.9.9"
        app.current_page().discard_unsaved()  # type: ignore[union-attr]
        app.action_reload()
        await settle(app, pilot)
        # The person decides; the agent continues the same session.
        agent.overrides.clear()
        await press(app, pilot, "#takeover-resume")
        await wait_agent(app, pilot)
        assert app.coordinator.snapshot().session_id == session
        engine = app.coordinator.engine
        assert engine is not None and engine.state.blockers[0].resolved
        assert not app.query_one("#takeover-bar").display or (
            app.coordinator.snapshot().interventions
        )


async def test_wide_terminals_keep_the_page_and_the_ai_side_by_side(
    tmp_path: Path,
) -> None:
    root = _prepared(tmp_path)
    app = NfSpliceApp(
        root, user="Ada", start="outputs", agent_provider=ScriptedProvider(RouteAgent())
    )
    async with app.run_test(size=(170, 45)) as pilot:
        await settle(app, pilot)
        assert not app.stacked
        app.open_dock("ask")
        await settle(app, pilot)
        page = app.current_page()
        assert page is not None and page.display
        assert app.query_one("#dock").display
        assert page.size.width >= 60
        await pilot.press("f6")
        await pilot.pause()
        assert app.query_one("#dock").display  # F6 moves focus, not the layout
