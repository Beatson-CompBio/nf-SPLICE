"""Choose a pipeline when `nf-splice` starts outside one.

Shown only when the current folder is neither a working copy nor a Nextflow
pipeline. It lists the working copies opened before and takes a pipeline
folder or Git URL to prepare as a safe copy; the workspace (and its Welcome
page) then opens on the chosen copy. It is a chooser, not a second
workspace: everything else happens in :class:`NfSpliceApp`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical, VerticalScroll
from textual.events import Resize
from textual.widgets import Button, Input, Static

from nf_splice.interfaces.tui.themes import (
    THEMES,
    load_theme_preference,
)
from nf_splice.interfaces.tui.widgets import BANNER, BANNER_WIDTH, Card, plain


class LauncherApp(App[Path | None]):
    """Returns the working copy to open, or None to exit."""

    TITLE = "nf-SPLICE"
    CSS_PATH = "tui.tcss"
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape,ctrl+q", "exit_launcher", "Exit", priority=True),
    ]

    def __init__(self, folder: Path) -> None:
        super().__init__()
        from nf_splice.services.source import recent_integrations

        self.folder = folder
        self.recent = recent_integrations()
        for theme in THEMES:
            self.register_theme(theme)
        self.theme = load_theme_preference()

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="launcher", classes="page"):
            yield Static(BANNER, id="welcome-banner")
            yield Static(
                "nf-SPLICE | Nextflow Integration Toolkit", id="welcome-compact"
            )
            yield Static(
                plain(
                    f"{self.folder} is not a Nextflow pipeline or an nf-SPLICE "
                    "working copy. Choose a working copy, or prepare one."
                ),
                id="welcome-summary",
            )
            if self.recent:
                with Card(title="Your working copies"), Vertical(id="welcome-options"):
                    for index, item in enumerate(self.recent, start=1):
                        name = Path(item["path"]).name
                        branch = item.get("branch") or "no branch"
                        state = "drafts" if item.get("has_drafts") else "no drafts yet"
                        yield Button(
                            plain(f"[{index}] {name}  ({branch}; {state})"),
                            id=f"launch-recent-{index}",
                            classes="welcome-option",
                            tooltip=str(item["path"]),
                        )
            with Card(title="Prepare a safe working copy"):
                yield Static(
                    "A pipeline folder, local Git repository or Git URL. nf-SPLICE "
                    "copies it next to the original (as <name>-splice-integration) "
                    "on its own Git branch; the original is never changed.",
                    classes="muted",
                )
                yield Input(placeholder="../my-pipeline", id="launch-source")
                yield Button("Prepare and open", id="launch-prepare")
            yield Static("", id="launch-message", classes="muted")
            yield Button("Exit", id="launch-exit")

    def on_mount(self) -> None:
        self._banner(self.size.width)
        target = "#launch-recent-1" if self.recent else "#launch-source"
        self.query_one(target).focus()

    def on_resize(self, event: Resize) -> None:
        self._banner(event.size.width)

    def _banner(self, width: int) -> None:
        wide = width >= BANNER_WIDTH + 4
        self.query_one("#welcome-banner").display = wide
        self.query_one("#welcome-compact").display = not wide

    def on_key(self, event: Any) -> None:
        if (
            event.character
            and event.character.isdigit()
            and not isinstance(self.focused, Input)
        ):
            number = int(event.character)
            if 1 <= number <= len(self.recent):
                self.exit(Path(self.recent[number - 1]["path"]))

    def action_exit_launcher(self) -> None:
        self.exit(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "launch-source":
            self._prepare()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        identifier = event.button.id or ""
        if identifier == "launch-exit":
            self.exit(None)
        elif identifier == "launch-prepare":
            self._prepare()
        elif identifier.startswith("launch-recent-"):
            index = int(identifier.rsplit("-", 1)[1]) - 1
            self.exit(Path(self.recent[index]["path"]))

    def _say(self, text: str) -> None:
        self.query_one("#launch-message", Static).update(plain(text))

    def _prepare(self) -> None:
        source = self.query_one("#launch-source", Input).value.strip()
        if not source:
            self._say("Enter a pipeline folder or Git URL first.")
            return
        if "://" not in source and not source.startswith("git@"):
            source = str((self.folder / Path(source).expanduser()).resolve())
        self.query_one("#launch-prepare", Button).disabled = True
        self._say(f"Preparing a safe working copy of {source}…")

        def work() -> None:
            from nf_splice.services.source import (
                prepare_integration_copy,
                remember_integration,
            )

            try:
                copy = prepare_integration_copy(source)
            except Exception as error:
                self.call_from_thread(self._failed, str(error))
                return
            remember_integration(Path(copy.path))
            self.call_from_thread(self.exit, Path(copy.path))

        self.run_worker(work, thread=True, group="prepare")

    def _failed(self, message: str) -> None:
        self.query_one("#launch-prepare", Button).disabled = False
        self._say(f"The working copy was not created; nothing changed. {message}")
