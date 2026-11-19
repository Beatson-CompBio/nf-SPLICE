"""The workspace shell's widgets: top bar, step rail, cards and strips.

Every widget takes its colours from the active theme's variables. States are
shown with a glyph and a word as well as a colour.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, Static

from nf_splice.interfaces.tui.coordinator import AgentSnapshot
from nf_splice.interfaces.tui.navigation import (
    GLYPHS,
    GROUPS,
    LABELS,
    PAGES,
    StepState,
)

if TYPE_CHECKING:
    from nf_splice.interfaces.tui.app import NfSpliceApp

BANNER = """\
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃                                                                              ┃
┃       █████████  ███████████  █████       █████   █████████  ██████████      ┃
┃      ███░░░░░███░░███░░░░░███░░███       ░░███   ███░░░░░███░░███░░░░░█      ┃
┃     ░███    ░░░  ░███    ░███ ░███        ░███  ███     ░░░  ░███  █ ░       ┃
┃     ░░█████████  ░██████████  ░███        ░███ ░███          ░██████         ┃
┃      ░░░░░░░░███ ░███░░░░░░   ░███        ░███ ░███          ░███░░█         ┃
┃      ███    ░███ ░███         ░███      █ ░███ ░░███     ███ ░███ ░   █      ┃
┃     ░░█████████  █████        ███████████ █████ ░░█████████  ██████████      ┃
┃      ░░░░░░░░░  ░░░░░        ░░░░░░░░░░░ ░░░░░   ░░░░░░░░░  ░░░░░░░░░░       ┃
┃                                                                              ┃
┃                 nf-SPLICE  |  Nextflow Integration Toolkit                   ┃
┃                                                                              ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛"""
#: Columns the full banner needs; narrower terminals get a one-line heading.
BANNER_WIDTH = 82
HINTS = (
    ("F1", "Help"),
    ("Ctrl+P", "Commands & theme"),
    ("Ctrl+R", "Reload"),
    ("Ctrl+A", "AI dock"),
    ("F6", "Page ⇄ AI"),
    ("Ctrl+Q", "Quit"),
)

#: Rail labels for compact layouts, where the full titles would be clipped.
SHORT_TITLES = {
    "overview": "Overview",
    "assays": "Assays",
    "software": "Software",
}
SHORT_GROUPS = {
    "GET STARTED": "START",
    "CREATE YOUR INTEGRATION": "AUTHOR",
    "FINISH": "FINISH",
}
TOOLS = (
    ("tool-drafts", "▤ View drafts", "▤ Drafts"),
    ("tool-sources", "⌕ Browse sources", "⌕ Sources"),
    ("tool-theme", "◑ Theme", "◑ Theme"),
    ("tool-help", "? Help / shortcuts", "? Help"),
)


def plain(text: Any) -> Text:
    """Text that is never parsed as markup (file content, messages)."""
    return Text(str(text))


class Chip(Static):
    """A short, bordered state label: glyph and words, never colour alone."""

    DEFAULT_CLASSES = "chip"

    def show(self, text: str, tone: str = "") -> None:
        self.update(plain(text))
        for name in ("good", "warn", "bad", "info"):
            self.set_class(tone == name, f"chip-{name}")


class TopBar(Horizontal):
    """Wordmark, pipeline, truthful status and the persistent AI controls."""

    def compose(self) -> ComposeResult:
        yield Static("▣ nf-SPLICE", id="wordmark")
        yield Static("WORKFLOW INTEGRATION", id="subtitle")
        yield Static("", id="pipeline-name")
        yield Chip("", id="mode-chip")
        yield Chip("", id="state-chip")
        yield Button("◇ AI", id="agent-status", classes="agent-status")
        yield Button("Ask AI", id="top-ask", classes="compact")
        yield Button("Assist this step", id="top-assist", classes="compact")
        yield Button("Autonomous", id="top-autonomous", classes="compact")

    def show(
        self,
        pipeline: str,
        mode: str,
        state: tuple[str, str],
        agent: AgentSnapshot,
    ) -> None:
        self.query_one("#pipeline-name", Static).update(plain(pipeline))
        self.query_one("#mode-chip", Chip).show(mode, "info")
        self.query_one("#state-chip", Chip).show(*state)
        button = self.query_one("#agent-status", Button)
        button.label = f"{agent.glyph} {agent.label}"
        button.set_class(agent.attention, "attention")
        provider = f"Provider: {agent.provider.name}. " if agent.provider else ""
        button.tooltip = (
            provider
            + "Open the AI assistant. "
            + (agent.unavailable or "Closing it never cancels a session.")
        )


class RailItem(Button):
    """One page in the step rail."""

    class Chosen(Message):
        def __init__(self, page_id: str) -> None:
            super().__init__()
            self.page_id = page_id

    def __init__(self, page_id: str, title: str) -> None:
        super().__init__(title, id=f"rail-{page_id}", classes="rail-item")
        self.page_id = page_id
        self.title = title
        self.compact = False

    def show(self, state: StepState, current: bool) -> None:
        title = (
            SHORT_TITLES.get(self.page_id, self.title) if self.compact else self.title
        )
        self.label = f"{GLYPHS[state]} {title}"
        self.tooltip = f"{self.title}: {LABELS[state]}"
        self.set_class(current, "current")
        for item in StepState:
            self.set_class(item is state, f"state-{item.value}")


class StepRail(VerticalScroll):
    """Grouped, keyboard- and mouse-navigable steps with derived states."""

    def compose(self) -> ComposeResult:
        for group in GROUPS:
            yield Static(group, classes="rail-heading", name=group)
            for item in PAGES:
                if item.group == group:
                    yield RailItem(item.id, item.title)
        yield Static("TOOLS", classes="rail-heading", name="TOOLS")
        for identifier, label, _short in TOOLS:
            yield Button(label, id=identifier, classes="rail-item tool")

    def set_compact(self, compact: bool) -> None:
        """Short labels where the rail is narrow, so nothing is clipped."""
        for heading in self.query(".rail-heading").results(Static):
            name = heading.name or ""
            heading.update(SHORT_GROUPS.get(name, name) if compact else name)
        for identifier, label, short in TOOLS:
            self.query_one(f"#{identifier}", Button).label = short if compact else label
        for item in self.query(RailItem):
            item.compact = compact

    def show(self, states: dict[str, StepState], current: str) -> None:
        for item in self.query(RailItem):
            item.show(
                states.get(item.page_id, StepState.NOT_STARTED), item.page_id == current
            )


class Card(Vertical):
    """A bounded panel with an optional title row."""

    DEFAULT_CLASSES = "card"

    def __init__(
        self,
        *children: Widget,
        title: str = "",
        id: str | None = None,
        classes: str = "",
    ) -> None:
        super().__init__(*children, id=id, classes=f"card {classes}".strip())
        self.border_title = title or None


class ActionBar(Horizontal):
    """Sticky Back / Finish later / Continue, with the step position."""

    def compose(self) -> ComposeResult:
        yield Static("", id="step-position")
        yield Button("← Back", id="nav-back")
        yield Button("Finish later", id="nav-later")
        yield Button("Continue →", id="nav-continue", variant="primary")

    def show(self, position: str, continue_label: str = "Continue →") -> None:
        self.query_one("#step-position", Static).update(plain(position))
        self.query_one("#nav-continue", Button).label = continue_label


class StatusStrip(Horizontal):
    """Outcome of the last action, and context-appropriate shortcuts."""

    def compose(self) -> ComposeResult:
        yield Static(
            Text.assemble(
                *(
                    part
                    for key, label in HINTS
                    for part in ((key, "bold"), f" {label}   ")
                )
            ),
            id="hints",
        )
        yield Static("", id="status-message")

    def show(self, message: str, tone: str = "") -> None:
        widget = self.query_one("#status-message", Static)
        widget.update(plain(message))
        for name in ("good", "warn", "bad"):
            widget.set_class(tone == name, f"tone-{name}")


class IssueList(Vertical):
    """At most a few issues inline, each with a jump; 'View all' for the rest."""

    class Jump(Message):
        def __init__(self, index: int) -> None:
            super().__init__()
            self.index = index

    def __init__(self, *, id: str | None = None, limit: int = 5) -> None:
        super().__init__(id=id, classes="issue-list")
        self.limit = limit
        self._count = 0

    def show(self, lines: Iterable[tuple[str, str]], total: int | None = None) -> None:
        """``lines`` are (severity, text) pairs; only the first few render."""
        items = list(lines)
        self.remove_children()
        shown = items[: self.limit]
        for severity, text in shown:
            glyph = "✕" if severity == "error" else "ⓘ"
            widget = Static(plain(f"{glyph} {text}"), classes=f"issue issue-{severity}")
            self.mount(widget)
        count = total if total is not None else len(items)
        if count > len(shown):
            self.mount(
                Button(
                    f"View all ({count})",
                    classes="compact link view-all",
                    name=f"{self.id}-all" if self.id else None,
                )
            )
        self._count = count
        self.display = bool(items)


def app_of(widget: Widget) -> NfSpliceApp:
    from nf_splice.interfaces.tui.app import NfSpliceApp

    app = widget.app
    assert isinstance(app, NfSpliceApp)
    return app


class TakeoverBar(Vertical):
    """Shown over the page while an agent waits for a person's decision."""

    def compose(self) -> ComposeResult:
        yield Static("", id="takeover-text")
        with Horizontal(id="takeover-actions"):
            yield Button(
                "Return to AI panel (F6)", id="takeover-return", classes="compact"
            )
            yield Button(
                "Resume same session",
                id="takeover-resume",
                classes="compact",
                variant="primary",
            )

    def show(self, text: str) -> None:
        self.query_one("#takeover-text", Static).update(plain(text))
