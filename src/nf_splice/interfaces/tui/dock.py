"""The AI assistant dock: Ask, Assist and Autonomous on every page.

The dock is presentation only. It renders the coordinator's
:class:`~nf_splice.interfaces.tui.coordinator.AgentSnapshot` and turns
button presses into coordinator calls; closing it changes nothing about a
running session (ADR-0067). Inputs persist across refreshes: only status
text is updated, so a half-typed question or objection is never lost.
"""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Button,
    Checkbox,
    ContentSwitcher,
    Input,
    Label,
    Markdown,
    Static,
    TextArea,
)

from nf_splice.agents.permissions import Permission
from nf_splice.interfaces.tui.coordinator import (
    OPTIONAL_GRANTS,
    AgentSnapshot,
    AgentState,
    stage_status_glyph,
)
from nf_splice.interfaces.tui.navigation import page as page_spec
from nf_splice.interfaces.tui.widgets import Card, plain

TABS = ("ask", "assist", "autonomous")
CONFIGURE_HELP = (
    "nf-SPLICE works fully without AI. To use Ask, Assist or autonomy, install "
    "a provider and start the workspace with it, for example:\n\n"
    "```\nnf-splice provider list\nnf-splice provider select claude\n"
    "nf-splice tui --provider claude\n```\n\n"
    "Remote providers receive repository context only after you consent here."
)


class AgentDock(Vertical):
    """Right-hand assistant panel (an overlay on narrow terminals)."""

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self.tab = "ask"
        self.page_id = "welcome"
        self.selection = ""

    # ------------------------------------------------------------ layout

    def compose(self) -> ComposeResult:
        with Vertical(id="dock-header"):
            with Horizontal(classes="row"):
                yield Static("AI integration assistant", id="dock-title")
                yield Button("Close x", id="dock-close", classes="compact")
            yield Static("", id="dock-context", classes="muted")
            yield Static("", id="dock-provider", classes="muted")
            with Horizontal(id="dock-tabs"):
                yield Button("Ask", id="dock-tab-ask", classes="dock-tab")
                yield Button("Assist", id="dock-tab-assist", classes="dock-tab")
                yield Button("Autonomous", id="dock-tab-autonomous", classes="dock-tab")
        with VerticalScroll(id="dock-body"):
            with Card(id="dock-access", title="Before AI can help"):
                yield Markdown("", id="dock-access-text")
                yield Checkbox(
                    "I consent to send repository context to this remote model",
                    id="dock-consent",
                )
                yield Label("Your name (recorded with approvals and pauses)")
                yield Input(placeholder="e.g. Ada Lovelace", id="dock-person")
            with ContentSwitcher(initial="dock-ask", id="dock-panels"):
                with Vertical(id="dock-ask"):
                    with Card(title="Ask (read-only)"):
                        yield Static("", id="ask-intro", classes="muted")
                        yield TextArea("", id="ask-question")
                        with Horizontal(classes="row"):
                            yield Button("Ask AI", id="ask-send", variant="primary")
                            yield Button("Use example", id="ask-example")
                            yield Button("Cancel answer", id="ask-cancel")
                    with Card(title="Answer", id="ask-answer-card"):
                        yield Static("", id="ask-answer-question", classes="muted")
                        yield Markdown("", id="ask-answer")
                    with Card(title="Want edits instead?"):
                        yield Static(
                            "Assist proposes changes to this section; nothing is "
                            "written until you approve them.",
                            classes="muted",
                        )
                        yield Button("Assist with this section →", id="ask-to-assist")
                with Vertical(id="dock-assist"):
                    with Card(title="Assist", id="assist-idle"):
                        yield Static("", id="assist-intro", classes="muted")
                        yield Label("Guidance for the agent (optional)")
                        yield TextArea("", id="assist-guidance")
                        yield Checkbox(
                            "Focus on my current selection", id="assist-selection"
                        )
                        yield Button(
                            "Prepare a proposal", id="assist-start", variant="primary"
                        )
                    with Card(title="Working", id="assist-working"):
                        yield Static("", id="assist-progress")
                        yield Button("Request pause", id="assist-pause")
                    with Card(title="Proposal awaiting approval", id="assist-proposal"):
                        yield Static("", id="proposal-head")
                        yield Static("", id="proposal-body")
                        yield Static("", id="proposal-diff", classes="code")
                        with Horizontal(classes="row"):
                            yield Button(
                                "Approve changes",
                                id="proposal-approve",
                                variant="primary",
                            )
                            yield Button("View full diff", id="proposal-diff-view")
                        yield TextArea("", id="proposal-revision")
                        with Horizontal(classes="row"):
                            yield Button("Request revision", id="proposal-revise")
                            yield Button("Edit manually", id="proposal-manual")
                            yield Button(
                                "Reject", id="proposal-reject", variant="error"
                            )
                    with Card(title="The agent has a question", id="assist-question"):
                        yield Static("", id="question-text")
                        yield TextArea("", id="question-reply")
                        with Horizontal(classes="row"):
                            yield Button(
                                "Answer", id="question-answer", variant="primary"
                            )
                            yield Button("Edit directly", id="question-edit")
                            yield Button("Resume", id="question-resume")
                with Vertical(id="dock-autonomous"):
                    with Card(title="Start autonomous integration", id="auto-scope"):
                        yield Static(
                            "The agent works across the integration within the scope "
                            "you approve. You can watch each stage, request a safe "
                            "pause, take over a field and resume the same session.",
                            classes="muted",
                        )
                        yield Checkbox(
                            "Read approved pipeline sources (always)",
                            value=True,
                            disabled=True,
                        )
                        yield Checkbox(
                            "Make reversible, audited edits to the private drafts "
                            "(always)",
                            value=True,
                            disabled=True,
                        )
                        for permission, label in OPTIONAL_GRANTS:
                            yield Checkbox(
                                f"{label} (separate grant)",
                                id=f"grant-{permission.value}",
                            )
                        yield Label("Most tool calls the agent may make")
                        yield Input("1500", id="auto-budget", restrict=r"[0-9]*")
                        yield Button(
                            "Approve scope and start",
                            id="auto-start",
                            variant="primary",
                        )
                    with Card(title="Autonomous session", id="auto-running"):
                        yield Static("", id="auto-head")
                        yield Static("", id="auto-stages")
                        yield Static("", id="auto-activity", classes="code")
                        with Horizontal(classes="row"):
                            yield Button("Request pause", id="auto-pause")
                            yield Button("Stop", id="auto-stop", variant="error")
                    with Card(
                        title="Human intervention requested", id="auto-intervention"
                    ):
                        yield Static("", id="intervention-text")
                        with Horizontal(classes="row"):
                            yield Button(
                                "Open the affected field",
                                id="intervention-open",
                                variant="primary",
                            )
                            yield Button(
                                "Resume same session", id="intervention-resume"
                            )
                        yield TextArea("", id="intervention-note")
                        with Horizontal(classes="row"):
                            yield Button("Answer", id="intervention-answer")
                            yield Button("Skip with reason", id="intervention-skip")
                            yield Button("Inspect evidence", id="intervention-evidence")
                            yield Button(
                                "Stop", id="intervention-stop", variant="error"
                            )
                    with Card(title="Session paused", id="auto-paused"):
                        yield Static("", id="paused-text")
                        with Horizontal(classes="row"):
                            yield Button(
                                "Resume", id="paused-resume", variant="primary"
                            )
                            yield Button("Continue manually", id="paused-manual")
                            yield Button("Assist instead", id="paused-assist")
                        with Horizontal(classes="row"):
                            yield Button("Change scope", id="paused-scope")
                            yield Button("Stop", id="paused-stop", variant="error")
                    with Card(title="Finished", id="auto-finished"):
                        yield Static("", id="finished-text")
                        with Horizontal(classes="row"):
                            yield Button(
                                "Review changes",
                                id="finished-review",
                                variant="primary",
                            )
                            yield Button("Validate", id="finished-validate")
                            yield Button("Publish", id="finished-publish")
            with Card(title="Provider", id="dock-provider-card"):
                yield Static("", id="provider-details", classes="muted")
                yield Markdown(CONFIGURE_HELP, id="provider-configure")
        yield Static("", id="dock-footer", classes="muted")

    # ------------------------------------------------------------ state

    def set_context(self, page_id: str, selection: str = "") -> None:
        self.page_id = page_id
        self.selection = selection
        spec = page_spec(page_id)
        text = f"Current section: {spec.title}"
        if selection:
            text += f" · selected: {selection}"
        self.query_one("#dock-context", Static).update(plain(text))
        self.query_one("#ask-intro", Static).update(
            plain(
                f"Ask about {spec.title}: the current form, the selected item or "
                "the pipeline's sources. Nothing is changed."
            )
        )
        self.query_one("#ask-question", TextArea).placeholder = spec.ask_example
        self.query_one("#assist-intro", Static).update(
            plain(
                f"{spec.assist_label}. The agent investigates the sources, proposes "
                "evidence-grounded edits with a diff and validation, and applies "
                "nothing until you approve."
            )
        )

    def show_tab(self, tab: str) -> None:
        self.tab = tab if tab in TABS else "ask"
        self.query_one("#dock-panels", ContentSwitcher).current = f"dock-{self.tab}"
        for name in TABS:
            self.query_one(f"#dock-tab-{name}", Button).set_class(
                name == self.tab, "active"
            )

    def render_snapshot(self, snapshot: AgentSnapshot) -> None:
        """Update status text and which cards show; never reset inputs."""
        provider = snapshot.provider
        if provider is None:
            details = "No AI provider is configured. Manual editing is fully available."
            line = "◇ AI OFF · manual work only"
        else:
            details = (
                f"{provider.name} · model {provider.model} · inference "
                f"{provider.inference} · billing {provider.billing} · structured "
                f"tools {'yes' if provider.tool_calling else 'no'} · reasoning "
                f"control {provider.reasoning} · continuation "
                f"{'yes' if provider.continuation else 'no'}"
            )
            line = (
                f"◇ {provider.name} ({provider.model}) · "
                + ("remote" if provider.remote else "local")
                + (
                    " · consent given"
                    if provider.remote and not snapshot.consent_needed
                    else ""
                )
            )
        self.query_one("#dock-provider", Static).update(plain(line))
        self.query_one("#provider-details", Static).update(plain(details))
        self.query_one("#provider-configure").display = provider is None
        blocked = bool(snapshot.unavailable) or snapshot.consent_needed
        needs_person = not snapshot.person
        access = self.query_one("#dock-access")
        access.display = blocked or needs_person
        messages = []
        if snapshot.unavailable:
            messages.append(snapshot.unavailable)
        if snapshot.consent_needed:
            messages.append(
                f"**{provider.name if provider else 'This provider'} runs remotely.** "
                "Asking, assisting or running autonomously sends repository "
                "context (sources and drafts) to it. Nothing is sent until you "
                "consent below."
            )
        if needs_person:
            messages.append(
                "Enter your name: approvals, pauses and resumes are recorded with "
                "the person who made them."
            )
        self.query_one("#dock-access-text", Markdown).update("\n\n".join(messages))
        self.query_one("#dock-consent").display = snapshot.consent_needed
        self.query_one("#dock-person").display = needs_person
        unavailable = blocked
        # Ask
        for selector in ("#ask-send", "#ask-example"):
            self.query_one(selector, Button).disabled = unavailable or snapshot.asking
        self.query_one("#ask-cancel", Button).display = snapshot.asking
        answer_card = self.query_one("#ask-answer-card")
        answer_card.display = bool(snapshot.answer or snapshot.asking)
        self.query_one("#ask-answer-question", Static).update(
            plain(f"Q: {snapshot.answer_question}" if snapshot.answer_question else "")
        )
        self.query_one("#ask-answer", Markdown).update(
            snapshot.answer
            or ("_Reading the sources (read-only)…_" if snapshot.asking else "")
        )
        self._assist(snapshot, unavailable)
        self._autonomous(snapshot, unavailable)
        footer = {
            AgentState.RUNNING: "The agent is working. Browse freely; editing a "
            "draft first needs a confirmed pause.",
            AgentState.PAUSE_REQUESTED: "Waiting for a safe checkpoint; nothing is "
            "paused yet.",
            AgentState.AWAITING_YOU: "The agent is waiting for you to resolve the "
            "named field.",
        }.get(
            snapshot.state,
            "Same YAML drafts in every mode. Closing this panel does not cancel a "
            "session.",
        )
        if snapshot.error:
            footer = f"Error: {snapshot.error}"
        elif snapshot.notice:
            footer = snapshot.notice
        self.query_one("#dock-footer", Static).update(plain(footer))

    def _assist(self, snapshot: AgentSnapshot, unavailable: bool) -> None:
        state = snapshot.state
        working = (
            state in {AgentState.THINKING, AgentState.PAUSE_REQUESTED} and snapshot.busy
        )
        proposal = snapshot.proposal
        question = (
            state is AgentState.AWAITING_YOU
            and snapshot.mode == "assisted"
            and bool(snapshot.interventions)
        )
        self.query_one("#assist-working").display = working
        self.query_one("#assist-proposal").display = (
            proposal is not None and not working
        )
        self.query_one("#assist-question").display = question and not working
        idle = not working and proposal is None and not question
        self.query_one("#assist-idle").display = idle
        self.query_one("#assist-start", Button).disabled = unavailable or snapshot.busy
        if working:
            self.query_one("#assist-progress", Static).update(
                plain(
                    f"{snapshot.task or 'Working'}… "
                    + (
                        "Waiting for a safe checkpoint before pausing."
                        if state is AgentState.PAUSE_REQUESTED
                        else "The interface stays usable; no draft changes until "
                        "you approve."
                    )
                )
            )
        if proposal is not None:
            files = ", ".join(proposal.changed_files) or "no file changes"
            self.query_one("#proposal-head", Static).update(
                plain(
                    f"{proposal.stage_title} · {proposal.id} · {proposal.operations} "
                    f"operation(s) · changes: {files}\nNo files changed yet."
                )
            )
            lines = [proposal.summary, ""]
            if proposal.evidence:
                lines.append("Evidence: " + "; ".join(proposal.evidence[:6]))
            if proposal.uncertainties:
                lines.append("Uncertainty: " + "; ".join(proposal.uncertainties[:4]))
            lines.append(
                "Preflight validation: "
                + (
                    "; ".join(proposal.preview_issues[:4])
                    if proposal.preview_issues
                    else "the changed draft validates"
                )
            )
            self.query_one("#proposal-body", Static).update(plain("\n".join(lines)))
            diff_lines = proposal.diff.splitlines()
            preview = "\n".join(diff_lines[:30])
            if len(diff_lines) > 30:
                preview += f"\n… {len(diff_lines) - 30} more line(s): View full diff"
            self.query_one("#proposal-diff", Static).update(
                plain(preview or "(no diff)")
            )
            for selector in (
                "#proposal-approve",
                "#proposal-revise",
                "#proposal-reject",
            ):
                self.query_one(selector, Button).disabled = snapshot.busy
        if question:
            item = snapshot.interventions[0]
            self.query_one("#question-text", Static).update(
                plain(f"{item.stage_title}: {item.decision}")
            )

    def _autonomous(self, snapshot: AgentSnapshot, unavailable: bool) -> None:
        state = snapshot.state
        autonomous = snapshot.mode == "autonomous"
        running = state in {AgentState.RUNNING, AgentState.PAUSE_REQUESTED} and (
            autonomous or snapshot.busy
        )
        intervention = state in {
            AgentState.AWAITING_YOU,
            AgentState.BLOCKED,
            AgentState.FAILED,
        } and (autonomous or state is not AgentState.AWAITING_YOU)
        paused = state is AgentState.PAUSED
        finished = state in {AgentState.COMPLETED, AgentState.STOPPED}
        self.query_one("#auto-running").display = running
        self.query_one("#auto-intervention").display = intervention and not running
        self.query_one("#auto-paused").display = paused
        self.query_one("#auto-finished").display = finished
        scope_visible = not (running or intervention or paused) or getattr(
            self, "_show_scope", False
        )
        self.query_one("#auto-scope").display = scope_visible and not running
        self.query_one("#auto-start", Button).disabled = unavailable or snapshot.busy
        if running or paused or intervention or finished:
            timeline = "\n".join(
                f"{stage_status_glyph(status)} {title}"
                for title, status in snapshot.stages
            )
            head = (
                f"Session {snapshot.session_id} · stage: "
                f"{snapshot.stage_title or '—'}\nScope: "
                + ", ".join(snapshot.grants)
                + f"\nTool calls: {snapshot.tool_calls} of {snapshot.max_tool_calls}"
                + (
                    "\nPause requested: waiting for a safe checkpoint."
                    if state is AgentState.PAUSE_REQUESTED
                    else ""
                )
            )
            self.query_one("#auto-head", Static).update(plain(head))
            self.query_one("#auto-stages", Static).update(plain(timeline))
            self.query_one("#auto-activity", Static).update(
                plain("\n".join(snapshot.activity[-6:]))
            )
            self.query_one("#auto-pause", Button).disabled = (
                state is AgentState.PAUSE_REQUESTED
            )
        if intervention:
            if snapshot.interventions:
                item = snapshot.interventions[0]
                more = len(snapshot.interventions) - 1
                text = (
                    f"Section: {page_spec(item.target.page).title}\n"
                    f"Entry: {item.pointer or item.artefact or item.stage_title}\n"
                    f"Decision: {item.decision}\n"
                    + (f"Why: {item.reason}\n" if item.reason else "")
                    + (
                        f"Evidence: {'; '.join(item.evidence[:3])}\n"
                        if item.evidence
                        else ""
                    )
                    + (f"Suggestion: {item.suggestion}\n" if item.suggestion else "")
                    + "No guess has been written. Use the normal editor to resolve "
                    "it, then resume the same session."
                    + (f"\n({more} more decision(s) after this one.)" if more else "")
                )
            else:
                text = snapshot.error or (
                    "The session stopped without a named decision. Inspect the "
                    "evidence, retry, or take over manually."
                )
            self.query_one("#intervention-text", Static).update(plain(text))
            self.query_one(
                "#intervention-open", Button
            ).disabled = not snapshot.interventions
        if paused:
            self.query_one("#paused-text", Static).update(
                plain(
                    (snapshot.notice + "\n" if snapshot.notice else "")
                    + "Drafts are free for your edits. This is the same session and "
                    "checkpoint; resuming re-reads the drafts and revalidates."
                )
            )
        if finished:
            self.query_one("#finished-text", Static).update(
                plain(
                    "The session was stopped. Start a new one to continue with AI; "
                    "a stopped session is never resumed."
                    if state is AgentState.STOPPED
                    else "Agent and human changes are in the same drafts. "
                    "Publishing needs its own grant and validation; nothing was "
                    "published unless the build grant was given."
                )
            )

    def grants(self) -> list[Permission]:
        return [
            permission
            for permission, _label in OPTIONAL_GRANTS
            if self.query_one(f"#grant-{permission.value}", Checkbox).value
        ]

    def budget(self) -> int:
        try:
            return max(
                1, min(20000, int(self.query_one("#auto-budget", Input).value or 1500))
            )
        except ValueError:
            return 1500

    def text(self, selector: str, *, clear: bool = False) -> str:
        area = self.query_one(selector, TextArea)
        value = area.text.strip()
        if clear:
            area.text = ""
        return value

    def show_scope(self, visible: bool) -> None:
        self._show_scope = visible

    def context(self) -> dict[str, Any]:
        spec = page_spec(self.page_id)
        found: dict[str, Any] = {"wizard_step": spec.title, "layer": spec.layer}
        if self.selection:
            found["selection"] = self.selection
        return found
