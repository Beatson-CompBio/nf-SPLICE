"""Welcome and Pipeline overview."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
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


class WelcomePage(PageView):
    page_id = "welcome"
    help_text = (
        "**Welcome.** nf-SPLICE prepares a SPLICE workflow bundle for this "
        "Nextflow pipeline. Your work lives in six editable YAML drafts in "
        "`.splice-local/drafts/`; nothing is published until you choose "
        "Publish.\n\n**What you decide here:** how to start. Manual work and AI "
        "work use the same drafts, so you can switch at any time.\n\n"
        "**Example:** choose *Start manually*, confirm the identity, then ask "
        "the AI to propose outputs while you keep editing."
    )

    def body(self) -> ComposeResult:
        yield Static(BANNER, id="welcome-banner")
        yield Static("nf-SPLICE · Nextflow Integration Toolkit", id="welcome-compact")
        yield Static("", id="welcome-summary", classes="lead")
        with Horizontal(classes="grid"):
            with Card(title="Work manually"):
                yield Static(
                    "Use guided forms and make every scientific decision yourself. "
                    "Ask AI is available on every page and never changes a file.",
                    classes="muted",
                )
                yield Button("Start manually →", id="welcome-start", variant="primary")
                yield Button("Resume where I left off", id="welcome-resume")
            with Card(title="Work with AI"):
                yield Static(
                    "Approve AI proposals step by step, or let an agent work within "
                    "a scope you approve. You can pause, take over a field and "
                    "resume the same session.",
                    classes="muted",
                )
                with Horizontal(classes="row"):
                    yield Button("Ask AI", id="welcome-ask")
                    yield Button("Assist with the first step", id="welcome-assist")
                yield Button("Start autonomous integration", id="welcome-autonomous")
        with Horizontal(classes="row"):
            yield Button("Inspect only (no changes)", id="welcome-inspect")
            yield Button("Theme", id="welcome-theme")
        yield Static(
            "Your original pipeline stays unchanged. Drafts are private until you "
            "publish; nothing is pushed anywhere.",
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

    def refresh_page(self, model: WorkspaceModel) -> None:
        name = model.repository.name
        if model.has_drafts:
            text = (
                f"Repository {name}: your drafts exist. Resume to continue where you "
                "left off; starting again keeps every existing draft."
            )
        else:
            text = (
                f"Repository {name}: no drafts yet. Start manually creates six "
                "editable drafts from exact metadata in this repository."
            )
        self.query_one("#welcome-summary", Static).update(plain(text))
        self.query_one("#welcome-resume").display = model.has_drafts
        self.query_one("#welcome-start", Button).label = (
            "Continue manually →" if model.has_drafts else "Start manually →"
        )


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
