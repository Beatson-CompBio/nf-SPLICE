"""Assistant overlay: reachable from every step, never an authoring engine."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Input, Markdown, Select, Static

from nf_splice.agents import AgentMode, approve, reject, run_agent
from nf_splice.agents.tools import ProposalStatus
from nf_splice.services.audit import resolve_actor

if TYPE_CHECKING:
    from nf_splice.interfaces.tui.app import NfSpliceApp


class AgentScreen(ModalScreen[None]):
    """Ask, suggest or draft proposals; humans approve or reject them."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss", "Close")]

    def __init__(self, wizard: NfSpliceApp) -> None:
        super().__init__()
        self.wizard = wizard

    def compose(self) -> ComposeResult:
        with Vertical(id="agent-dialog"):
            if self.wizard.agent_provider is None:
                yield Markdown(
                    "## Assistant is off\n\nnf-splice works fully without AI. Start "
                    "`nf-splice tui --agent claude --allow-remote-model` (after "
                    "`pip install 'nf-splice[claude]'`) to enable suggestions. "
                    "Suggestions are proposals until you approve them here."
                )
                yield Button("Close", id="agent-close")
                return
            yield Static(
                f"Provider: {self.wizard.agent_provider.capabilities.name} "
                "(proposals only; nothing is applied without your approval)",
                id="agent-provider",
            )
            with Horizontal(classes="row"):
                yield Select(
                    [
                        (item.value, item.value)
                        for item in (AgentMode.ASK, AgentMode.SUGGEST, AgentMode.DRAFT)
                    ],
                    value=AgentMode.SUGGEST.value,
                    id="agent-mode",
                )
                yield Input(
                    placeholder="Ask the assistant about this step", id="agent-prompt"
                )
                yield Button("Run", id="agent-run", variant="primary")
            yield Static("", id="agent-log", classes="section")
            yield DataTable(id="agent-proposals")
            with Horizontal(classes="row"):
                yield Button("Approve selected", id="agent-approve", variant="success")
                yield Input(placeholder="reject reason", id="agent-reason")
                yield Button("Reject selected", id="agent-reject", variant="error")
                yield Button("Close", id="agent-close")

    def on_mount(self) -> None:
        if self.wizard.agent_provider is None:
            return
        table = self.query_one("#agent-proposals", DataTable)
        table.add_columns("proposal", "layer", "title", "status")
        table.cursor_type = "row"
        self._refresh()

    def _refresh(self) -> None:
        table = self.query_one("#agent-proposals", DataTable)
        table.clear()
        for item in self.wizard.agent_book.proposals.values():
            table.add_row(
                item.id, item.layer, item.title, item.status.value, key=item.id
            )

    def _selected(self) -> str | None:
        table = self.query_one("#agent-proposals", DataTable)
        if not table.row_count:
            return None
        return str(table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        wizard = self.wizard
        if event.button.id == "agent-close":
            self.dismiss(None)
        elif event.button.id == "agent-run" and wizard.agent_provider is not None:
            prompt = self.query_one("#agent-prompt", Input).value.strip() or (
                f"Help me with the {wizard.current} step."
            )
            mode = AgentMode(str(self.query_one("#agent-mode", Select).value))
            provider = wizard.agent_provider

            def work() -> None:
                result = asyncio.run(
                    run_agent(
                        wizard.repository,
                        provider,
                        prompt,
                        mode=mode,
                        book=wizard.agent_book,
                        allow_remote=True,
                    )
                )
                text = "\n".join(
                    f"{item.kind.value}: {item.text}" for item in result.events
                )
                self.app.call_from_thread(self._show_log, text)

            self.run_worker(work, thread=True, exclusive=True)
        elif event.button.id == "agent-approve":
            selected = self._selected()
            if selected is None:
                return
            identifier: str = selected
            actor = resolve_actor(wizard.actor_label)
            wizard.perform(
                "Applying approved proposal",
                lambda: approve(
                    wizard.repository, wizard.agent_book, identifier, actor
                ),
                then=lambda _result: self._refresh(),
            )
        elif event.button.id == "agent-reject":
            rejected = self._selected()
            reason = self.query_one("#agent-reason", Input).value.strip() or "rejected"
            if rejected is not None:
                reject(wizard.agent_book, rejected, reason)
                self._refresh()

    def _show_log(self, text: str) -> None:
        self.query_one("#agent-log", Static).update(text[:4000])
        self._refresh()

    def pending(self) -> int:
        return sum(
            item.status is ProposalStatus.PENDING
            for item in self.wizard.agent_book.proposals.values()
        )
