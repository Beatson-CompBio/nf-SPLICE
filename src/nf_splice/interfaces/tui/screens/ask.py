"""Ask AI: contextual, read-only help available on every step (Ctrl+A)."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Markdown, Static

from nf_splice.agents import ask_for_help
from nf_splice.interfaces.tui.steps import step

if TYPE_CHECKING:
    from nf_splice.interfaces.tui.app import NfSpliceApp

ASSISTANT_OFF = (
    "## Agentic AI is off\n\n"
    "nf-splice works fully without AI. To ask questions here, or to run an "
    "AI-assisted or autonomous session, install the optional extra and start "
    "the wizard with a provider:\n\n"
    "```\npip install 'nf-splice[claude] @ git+https://github.com/Beatson-CompBio/"
    "nf-SPLICE.git'\nnf-splice tui --provider claude --allow-remote-model\n```"
)


class AskScreen(ModalScreen[None]):
    """One question, answered with read-only tools; nothing can change."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss", "Close")]

    def __init__(self, wizard: NfSpliceApp) -> None:
        super().__init__()
        self.wizard = wizard

    def compose(self) -> ComposeResult:
        with Vertical(id="ask-dialog"):
            yield Static(
                "[b]Ask AI[/b]: contextual help. It reads your repository and "
                "drafts and cannot change anything.",
                id="ask-title",
            )
            if self.wizard.agent_provider is None:
                yield Markdown(ASSISTANT_OFF, id="ask-off")
                yield Button("Close", id="ask-close")
                return
            with Horizontal(classes="row"):
                yield Input(
                    placeholder=f"Ask about the {step(self.wizard.current).title} step",
                    id="ask-question",
                )
                yield Button("Ask", id="ask-run", variant="primary")
            with VerticalScroll(id="ask-scroll"):
                yield Markdown("", id="ask-answer")
            yield Button("Close", id="ask-close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "ask-close":
            self.dismiss(None)
            return
        provider = self.wizard.agent_provider
        if event.button.id != "ask-run" or provider is None:
            return
        wizard = self.wizard
        target = step(wizard.current)
        question = self.query_one("#ask-question", Input).value.strip() or (
            f"What should I check on the {target.title} step?"
        )
        context = {"wizard_step": target.title, "layer": target.layer}
        self.query_one("#ask-answer", Markdown).update("_Thinking..._")

        def work() -> None:
            try:
                answer = asyncio.run(
                    ask_for_help(
                        wizard.repository,
                        provider,
                        question,
                        context=context,
                        allow_remote_model=wizard.allow_remote_model,
                    )
                )
                text = answer.text
            except Exception as error:
                text = f"**Error:** {error}"
            self.app.call_from_thread(self._show, text)

        self.run_worker(work, thread=True, exclusive=True)

    def _show(self, text: str) -> None:
        self.query_one("#ask-answer", Markdown).update(text)
