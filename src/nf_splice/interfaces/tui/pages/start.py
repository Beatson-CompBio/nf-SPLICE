"""Welcome and Pipeline overview."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.events import Resize
from textual.widgets import Button, Static

from nf_splice.interfaces.tui.model import WorkspaceModel
from nf_splice.interfaces.tui.navigation import StepState
from nf_splice.interfaces.tui.pages.base import PageView
from nf_splice.interfaces.tui.widgets import BANNER, BANNER_WIDTH, Card, plain

JOURNEY = (
    "1  Confirm the pipeline identity",
    "2  Tick supported assays and review parameter access",
    "3  Describe the outputs you want SPLICE to expose",
    "4  Review software, execution and provenance",
    "5  Review and publish",
)


#: Every Welcome option: (action, button id). Which appear, and in which
#: order, depends on the working copy and on AI readiness (:func:`options`).
OPTION_IDS = {
    "prepare": "welcome-prepare",
    "open-copy": "welcome-open-copy",
    "in-place": "welcome-in-place",
    "inspect": "welcome-inspect",
    "manual": "welcome-start",
    "setup-ai": "welcome-setup-ai",
    "assisted": "welcome-assisted",
    "autonomous": "welcome-autonomous",
    "ai-settings": "welcome-ai-settings",
    "exit": "welcome-exit",
}
#: The authoring steps counted as progress.
AUTHORING = (
    "identity",
    "assays",
    "parameters",
    "outputs",
    "software",
    "execution",
    "provenance",
)


def options(authorised: bool, ai_usable: bool, known_copy: bool) -> tuple[str, ...]:
    """The Welcome choices, in order (numbered from 1 on screen)."""
    if not authorised:
        return (
            ("prepare",)
            + (("open-copy",) if known_copy else ())
            + ("in-place", "inspect", "exit")
        )
    if ai_usable:
        return ("manual", "assisted", "autonomous", "ai-settings", "exit")
    return ("manual", "setup-ai", "exit")


def _copy_lines(model: WorkspaceModel, copies: tuple[str, ...]) -> list[str]:
    record = model.integration or {}
    lines = [f"Folder: {model.repository}"]
    if model.branch:
        lines.append(f"Git branch: {model.branch}")
    if record.get("in_place"):
        lines.append(
            "Working in place, as you authorised: nf-SPLICE writes splice/ and "
            ".splice-local/ in this folder."
        )
    elif record:
        source = record.get("source") or "unknown"
        revision = str(record.get("source_revision") or "")[:12]
        lines.append(
            f"Safe working copy of {source}"
            + (f" at {revision}" if revision else "")
            + ". The original is never changed."
        )
    elif model.has_drafts:
        lines.append(
            "Drafts already exist in this folder (created in place by an earlier "
            "version), so the work continues here."
        )
    else:
        lines.append(
            "This is the original pipeline folder. nf-SPLICE has not changed it, "
            "and will not unless you choose to work in place."
        )
        for path in copies[:3]:
            lines.append(f"A working copy you made earlier: {path}")
    return lines


def _progress_lines(model: WorkspaceModel, session: str) -> list[str]:
    if not model.has_drafts:
        lines = ["No drafts yet."]
    else:
        states = model.step_states()
        ready = sum(
            1
            for page_id in AUTHORING
            if states[page_id] in {StepState.READY, StepState.PUBLISHED}
        )
        lines = [
            f"{ready} of {len(AUTHORING)} steps ready · drafts in "
            ".splice-local/drafts/",
            "A bundle is published in splice/."
            if model.published
            else "Not published yet.",
        ]
    if session:
        lines.append(session)
    return lines


class WelcomePage(PageView):
    page_id = "welcome"
    help_text = (
        "**Welcome.** nf-SPLICE prepares a SPLICE workflow bundle for this "
        "Nextflow pipeline. It works on a safe copy of the pipeline (or, if you "
        "say so, in the folder itself). Your work lives in six editable YAML "
        "drafts in `.splice-local/drafts/`; nothing is published until you "
        "choose Publish.\n\n**What you decide here:** how to work. Manual, "
        "Assisted and Autonomous integration use the same drafts and the same "
        "validation, so you can switch at any time. Assisted and Autonomous "
        "appear once an AI provider has passed its connection test.\n\n"
        "**Keys:** press the number shown beside an option."
    )

    def __init__(self) -> None:
        super().__init__()
        self.choices: tuple[str, ...] = ()

    def body(self) -> ComposeResult:
        yield Static(BANNER, id="welcome-banner")
        yield Static("nf-SPLICE | Nextflow Integration Toolkit", id="welcome-compact")
        yield Static("", id="welcome-summary")
        with Card(title="Working copy", id="welcome-copy-card"):
            yield Static("", id="welcome-copy")
            yield Static("", id="welcome-progress", classes="muted")
        yield Static("", id="welcome-ai", classes="notice")
        with Vertical(id="welcome-options"):
            for identifier in OPTION_IDS.values():
                yield Button("", id=identifier, classes="welcome-option")
        yield Static(
            "Drafts are private until you publish; nothing is pushed anywhere.",
            classes="muted",
        )

    def on_mount(self) -> None:
        self._banner(self.app.size.width)

    def on_resize(self, event: Resize) -> None:
        self._banner(self.app.size.width)

    def _banner(self, width: int) -> None:
        wide = width >= BANNER_WIDTH + 30
        self.query_one("#welcome-banner").display = wide
        self.query_one("#welcome-compact").display = not wide

    def action_option(self, number: int) -> None:
        if 1 <= number <= len(self.choices):
            self.query_one(f"#{OPTION_IDS[self.choices[number - 1]]}", Button).press()

    def focus_first_option(self) -> None:
        if self.choices:
            # Without scrolling: the banner stays in view on short terminals.
            self.query_one(f"#{OPTION_IDS[self.choices[0]]}", Button).focus(
                scroll_visible=False
            )

    def refresh_page(self, model: WorkspaceModel) -> None:
        workspace = self.workspace
        readiness = workspace.ai_readiness
        snapshot = workspace.coordinator.snapshot()
        pipeline = model.pipeline()
        source = str((model.integration or {}).get("source") or "")
        name = str(
            pipeline.get("name")
            or (Path(source).name if source and "://" not in source else "")
            or model.repository.name
        )
        version = str(pipeline.get("version") or "")
        self.query_one("#welcome-summary", Static).update(
            plain(f"Pipeline: {name}" + (f" {version}" if version else ""))
        )
        self.query_one("#welcome-copy", Static).update(
            plain("\n".join(_copy_lines(model, workspace.known_copies)))
        )
        session = ""
        if snapshot.session_id and snapshot.mode:
            stage = snapshot.stage_title or snapshot.stage or "the start"
            session = (
                f"Agent session {snapshot.session_id}: {snapshot.mode}, "
                f"{snapshot.label.lower()}, at {stage}."
            )
        self.query_one("#welcome-progress").display = model.authorised
        self.query_one("#welcome-progress", Static).update(
            plain("\n".join(_progress_lines(model, session)))
        )
        ai = self.query_one("#welcome-ai", Static)
        if readiness is None:
            ai_text = "AI assistance: checking…"
        else:
            ai_text = f"AI assistance: {readiness.summary()}"
            if readiness.provider and readiness.billing:
                ai_text += f"\nBilling: {readiness.billing}"
            if readiness.usable:
                ai_text += "\nAssisted and Autonomous integration are available."
            else:
                if readiness.provider and readiness.detail:
                    ai_text += f"\n{readiness.detail}"
                ai_text += "\nManual integration works fully without AI."
        ai.set_class(bool(readiness and readiness.usable), "good")
        ai.update(plain(ai_text))
        first = not self.choices
        self.choices = options(
            model.authorised, workspace.ai_usable, bool(workspace.known_copies)
        )
        live = snapshot.session_id is not None and snapshot.state.value not in {
            "completed",
            "stopped",
            "off",
            "ready",
        }
        labels = {
            "prepare": "Prepare a safe working copy (recommended)",
            "open-copy": "Open the working copy you made earlier",
            "in-place": "Work in this folder instead…",
            "inspect": "Inspect only (no changes)",
            "manual": (
                "Continue manual integration"
                if model.has_drafts
                else "Start manual integration"
            ),
            "setup-ai": (
                "Set up AI assistance to resume the agent session"
                if live
                else "Set up AI assistance"
            ),
            "assisted": (
                "Resume assisted integration"
                if live and snapshot.mode == "assisted"
                else "Assisted integration"
            ),
            "autonomous": (
                "Resume autonomous integration"
                if live and snapshot.mode == "autonomous"
                else "Autonomous integration"
            ),
            "ai-settings": "AI provider settings",
            "exit": "Exit",
        }
        for action, identifier in OPTION_IDS.items():
            button = self.query_one(f"#{identifier}", Button)
            if action in self.choices:
                number = self.choices.index(action) + 1
                button.label = plain(f"[{number}] {labels[action]}")
                button.display = True
            else:
                button.display = False
        if first and workspace.current == "welcome":
            self.call_after_refresh(self.focus_first_option)


class OverviewPage(PageView):
    page_id = "overview"
    help_text = (
        "**Pipeline overview.** What nf-SPLICE read from this repository: only "
        "documented keys in recognised structured files (pipeline metadata, the "
        "parameter schema, module metadata, an existing RO-Crate). Prose such as "
        "the README is for you to browse, never copied into a field.\n\n**What "
        "happens next:** confirm the identity, then work through the steps in "
        "any order. A missing `splice/` folder is normal before publishing."
    )

    def body(self) -> ComposeResult:
        with Horizontal(classes="stats"):
            yield Static("", id="overview-drafts", classes="stat")
            yield Static("", id="overview-published", classes="stat")
            yield Static("", id="overview-sources", classes="stat")
        with Card(title="Source inspection", id="overview-inspection"):
            yield Static("", id="overview-source-list")
            yield Static("", id="overview-upstream", classes="muted")
            yield Button("Browse sources ↗", id="overview-browse", classes="compact")
        with Card(title="Your integration journey"):
            yield Static("\n".join(JOURNEY))
            yield Static("", id="overview-drafts-note", classes="notice good")
        with Card(title="Start again from exact metadata", id="overview-fresh-card"):
            yield Static(
                "Drafts from an earlier version may contain guessed entries (for "
                "example, an output per published route). This keeps a private "
                "backup of every draft, then recreates them from exact metadata "
                "only.",
                classes="muted",
            )
            yield Button("Start fresh from exact metadata…", id="overview-fresh")

    def refresh_page(self, model: WorkspaceModel) -> None:
        drafts = sum(1 for item in model.layers.values() if item.exists)
        found = [item for item in model.sources if item.found]
        self.query_one("#overview-drafts", Static).update(
            plain(f"{drafts}\nEditable drafts")
        )
        self.query_one("#overview-published", Static).update(
            plain(f"{1 if model.published else 0}\nPublished bundles")
        )
        self.query_one("#overview-sources", Static).update(
            plain(f"{len(found)}\nRecognised sources")
        )
        self.query_one("#overview-source-list", Static).update(
            plain(
                "\n".join(
                    f"{'✓' if item.found else '-'} {item.path}  "
                    f"({item.purpose}{'' if item.found else '; not found'})"
                    for item in model.sources
                )
            )
        )
        record = model.integration or {}
        upstream = record.get("source_remote")
        if upstream:
            text = f"Recorded upstream (integration record): {upstream}"
        elif record:
            text = (
                f"Integration copy of {record.get('source')}; no upstream remote "
                "was recorded."
            )
        else:
            text = "No integration record: this is the pipeline checkout itself."
        self.query_one("#overview-upstream", Static).update(plain(text))
        self.query_one("#overview-drafts-note", Static).update(
            plain(
                (
                    f"✓ {drafts} drafts ready for editing in .splice-local/drafts/\n"
                    if drafts
                    else "No drafts yet: use Start manually on Welcome.\n"
                )
                + (
                    "A bundle is already published in splice/."
                    if model.published
                    else "No bundle has been published yet. This is expected."
                )
            )
        )
        self.query_one("#overview-fresh-card").display = model.has_drafts

    def tag_text(self, model: WorkspaceModel, state: StepState) -> str:
        return "✓ WORKSPACE PREPARED" if model.all_drafts else "○ NO DRAFTS YET"
