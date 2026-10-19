"""The first-run journey (ADR-0071): help, working copy, Welcome, rendering.

Help is checked as rendered text from the real entry point at several
terminal widths, redirected and in a pseudo-terminal. The workspace is driven
headlessly over real files; its screen is read back character by character.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import select
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest
import typer
from textual.widgets import Button, Input, Static
from typer.testing import CliRunner

from layer_fixtures import write_pipeline
from nf_splice import credentials
from nf_splice.agents.providers import base as provider_base
from nf_splice.agents.providers import readiness as readiness_module
from nf_splice.agents.providers.readiness import ReadinessLevel, assess
from nf_splice.agents.providers.scripted import ScriptedProvider
from nf_splice.cli import app
from nf_splice.interfaces import help as cli_help
from nf_splice.interfaces.tui import NfSpliceApp
from nf_splice.interfaces.tui.pages.start import options
from nf_splice.interfaces.tui.widgets import BANNER
from nf_splice.services.source import (
    authorise_in_place,
    copies_of,
    read_record,
    recent_integrations,
    remember_integration,
)
from tui_helpers import press, settle

ROOT = Path(__file__).resolve().parents[1]
runner = CliRunner()
WIDTHS = (80, 100, 120, 250)
REPRESENTATIVE = (
    ["--help"],
    ["--help-all"],
    ["draft", "--help"],
    ["session", "start", "--help"],
    ["source", "prepare", "--help"],
    ["tui", "--help"],
    ["provider", "test", "--help"],
    ["init", "--help"],
)
ESCAPE = re.compile(r"\x1b\[")
PANEL = re.compile(r"[╭╮╰╯│─]")
needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")


@pytest.fixture(autouse=True)
def _git_identity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "gitconfig"
    config.write_text(
        "[user]\n\tname = Ada Lovelace\n\temail = ada@example.org\n"
        "[init]\n\tdefaultBranch = main\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("NF_SPLICE_CONFIG_DIR", str(tmp_path / "config"))


def _cli(
    arguments: list[str],
    *,
    columns: int = 80,
    term: str = "xterm-256color",
    extra: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = (
        dict(os.environ) | {"COLUMNS": str(columns), "TERM": term} | (extra or {})
    )
    return subprocess.run(
        [sys.executable, "-m", "nf_splice", *arguments],
        capture_output=True,
        text=True,
        env=environment,
        stdin=subprocess.DEVNULL,
        timeout=120,
        check=False,
    )


def _pipeline(root: Path, *, git: bool = True) -> Path:
    root.mkdir(parents=True)
    write_pipeline(root)
    (root / "nextflow.config").write_text(
        "manifest {\n    name = 'demo/rnaseq'\n    version = '1.0.0'\n}\n",
        encoding="utf-8",
    )
    if git:
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
        subprocess.run(
            ["git", "-C", str(root), "commit", "-q", "-m", "pipeline"], check=True
        )
    return root


def _tree(root: Path) -> dict[str, str]:
    """Every file under a folder (outside .git) with its sha256."""
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file() and ".git" not in path.relative_to(root).parts
    }


# ------------------------------------------------------------ help


@pytest.mark.parametrize("width", WIDTHS)
@pytest.mark.parametrize("arguments", REPRESENTATIVE, ids=" ".join)
def test_help_fits_the_terminal_without_panels_or_escapes(
    arguments: list[str], width: int
) -> None:
    result = _cli(arguments, columns=width)
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert lines and "Usage:" in result.stdout
    limit = min(width, cli_help.MAX_WIDTH)
    assert max(len(line) for line in lines) <= limit, (arguments, width)
    assert not ESCAPE.search(result.stdout)
    assert not PANEL.search(result.stdout)
    assert result.stderr == ""


@pytest.mark.parametrize("term", ["dumb", "xterm-256color", "vt100"])
def test_help_without_colour_support_is_plain(term: str) -> None:
    for extra in ({}, {"NO_COLOR": "1"}, {"FORCE_COLOR": "1"}):
        result = _cli(["--help"], term=term, extra=extra)
        assert result.returncode == 0
        assert not ESCAPE.search(result.stdout)


def test_root_help_is_task_oriented_and_agrees_with_the_readme() -> None:
    text = _cli(["--help"]).stdout
    for heading in ("Getting started:", "Authoring and validation:", "AI integration:"):
        assert heading in text
    for starting_point, _summary in cli_help.STARTING_POINTS:
        assert starting_point in text
    assert "--help-all" in text and "--version" in text
    # Advanced commands are one flag away, not in the root view.
    for advanced in ("analysis-output", "catalogue", "containers", "migrate"):
        assert advanced not in text
    assert len(text.splitlines()) < 45
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    quick_start = readme.split("## Quick start", 1)[1].split("## Documentation", 1)[0]
    first_command = re.search(r"```bash\n(.+?)\n", quick_start)
    assert first_command and first_command.group(1).startswith(
        "nf-splice source prepare"
    )
    assert "nf-splice --help-all" in quick_start
    assert "nf-splice init --in-place" in quick_start


def _all_commands() -> list[tuple[str, list[str]]]:
    group: Any = typer.main.get_command(app)
    context = group.context_class(group)
    found = []
    for name in group.list_commands(context):
        child = group.get_command(context, name)
        subcommands = (
            child.list_commands(child.context_class(child))
            if hasattr(child, "list_commands")
            else []
        )
        found.append((name, subcommands))
    return found


def test_help_all_lists_every_command_and_subcommand_by_task() -> None:
    result = _cli(["--help-all"], columns=250)
    assert result.returncode == 0
    flat = " ".join(result.stdout.split())
    assert "Other commands" not in result.stdout  # every command has a section
    sectioned = cli_help.sectioned()
    for name, subcommands in _all_commands():
        assert name in sectioned, name
        assert re.search(rf"(^|\s){re.escape(name)}\s", result.stdout), name
        for subcommand in subcommands:
            assert subcommand in flat, (name, subcommand)


def test_every_command_keeps_complete_help_and_runs() -> None:
    for name, subcommands in _all_commands():
        for path in [[name]] + [[name, item] for item in subcommands]:
            result = runner.invoke(app, [*path, "--help"])
            assert result.exit_code == 0, (path, result.output)
            assert "Usage: nf-splice " + " ".join(path) in " ".join(
                result.output.split()
            )


def test_version_and_bare_invocation_without_a_terminal() -> None:
    version = _cli(["--version"])
    assert version.returncode == 0 and version.stdout.startswith("nf-splice 0.3.0")
    bare = _cli([])
    assert bare.returncode == 2
    assert "Getting started:" in bare.stdout  # help, never a prompt
    assert bare.stderr == ""


def _pty(arguments: list[str], columns: int = 80) -> tuple[int, str]:
    """Run the entry point in a pseudo-terminal of the given width."""
    import fcntl
    import pty
    import struct
    import termios

    pid, descriptor = pty.fork()
    if pid == 0:  # pragma: no cover - the child process
        os.environ.update({"COLUMNS": str(columns), "TERM": "xterm-256color"})
        os.execv(sys.executable, [sys.executable, "-m", "nf_splice", *arguments])
    fcntl.ioctl(descriptor, termios.TIOCSWINSZ, struct.pack("HHHH", 40, columns, 0, 0))
    output = b""
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        ready, _, _ = select.select([descriptor], [], [], 1)
        if not ready:
            continue
        try:
            chunk = os.read(descriptor, 65536)
        except OSError:
            break
        if not chunk:
            break
        output += chunk
    _, status = os.waitpid(pid, 0)
    os.close(descriptor)
    return os.waitstatus_to_exitcode(status), output.decode("utf-8", "replace")


@pytest.mark.skipif(sys.platform == "win32", reason="needs a POSIX pty")
@pytest.mark.parametrize("width", [80, 120])
def test_help_in_a_real_terminal_never_opens_the_workspace(width: int) -> None:
    code, text = _pty(["--help"], width)
    assert code == 0
    assert "Getting started:" in text
    assert not ESCAPE.search(text)  # neither colour nor the workspace's screen
    assert max(len(line) for line in text.splitlines()) <= width
    code, text = _pty(["--version"], width)
    assert code == 0 and "nf-splice 0.3.0" in text


# ------------------------------------------------------------ working copy


@needs_git
def test_init_refuses_an_original_pipeline_until_authorised(tmp_path: Path) -> None:
    original = _pipeline(tmp_path / "rnaseq")
    before = _tree(original)
    refused = runner.invoke(app, ["init", "--repository", str(original)])
    assert refused.exit_code == 2
    assert "nf-splice source prepare" in refused.output
    assert "--in-place" in refused.output
    assert _tree(original) == before  # nothing written, not even .gitignore
    script = tmp_path / "script.json"
    script.write_text("[]", encoding="utf-8")
    session = runner.invoke(
        app,
        [
            "--user",
            "Ada",
            "session",
            "start",
            "--repository",
            str(original),
            "--script",
            str(script),
        ],
    )
    assert session.exit_code == 2 and "source prepare" in session.output
    authorised = runner.invoke(
        app, ["init", "--in-place", "--repository", str(original), "--json"]
    )
    assert authorised.exit_code == 0, authorised.output
    record = read_record(original)
    assert record is not None and record["in_place"] is True
    assert json.loads(authorised.output)["created"]


@needs_git
def test_source_prepare_hands_off_to_the_workspace_on_welcome(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import nf_splice.cli as cli

    original = _pipeline(tmp_path / "rnaseq")
    before = _tree(original)
    opened: list[tuple[Path, str | None]] = []
    monkeypatch.setattr(cli, "_interactive_terminal", lambda: True)
    monkeypatch.setattr(
        cli, "_open_workspace", lambda path, **kw: opened.append((path, kw["start"]))
    )
    result = runner.invoke(app, ["source", "prepare", str(original)])
    assert result.exit_code == 0, result.output
    copy = tmp_path / "rnaseq-splice-integration"
    assert opened == [(copy.resolve(), "welcome")]
    assert "--repository" not in result.output  # no command to copy by hand
    assert _tree(original) == before
    assert [item["path"] for item in recent_integrations()] == [str(copy.resolve())]
    # The copy is authorised; init there needs no consent.
    assert runner.invoke(app, ["init", "--repository", str(copy)]).exit_code == 0


@needs_git
def test_source_prepare_without_a_terminal_or_with_json_never_opens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import nf_splice.cli as cli

    opened: list[Path] = []
    monkeypatch.setattr(cli, "_open_workspace", lambda path, **kw: opened.append(path))
    first = _pipeline(tmp_path / "one")
    text = runner.invoke(app, ["source", "prepare", str(first)])
    assert text.exit_code == 0 and "Next: run `nf-splice` in that folder" in text.output
    monkeypatch.setattr(cli, "_interactive_terminal", lambda: True)
    second = _pipeline(tmp_path / "two")
    as_json = runner.invoke(app, ["source", "prepare", str(second), "--json"])
    assert as_json.exit_code == 0
    assert json.loads(as_json.output)["branch"] == "nf-splice/integration-two"
    third = _pipeline(tmp_path / "three")
    assert (
        runner.invoke(app, ["source", "prepare", str(third), "--no-open"]).exit_code
        == 0
    )
    assert opened == []


@needs_git
def test_bare_command_opens_the_folder_or_the_chooser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import nf_splice.cli as cli
    import nf_splice.interfaces.tui.launcher as launcher

    opened: list[tuple[Path, str | None]] = []
    monkeypatch.setattr(
        cli, "_open_workspace", lambda path, **kw: opened.append((path, kw["start"]))
    )
    pipeline = _pipeline(tmp_path / "rnaseq")
    cli._start_interactively(pipeline)
    assert opened == [(pipeline.resolve(), "welcome")]
    chosen = tmp_path / "chosen"
    monkeypatch.setattr(
        launcher.LauncherApp,
        "run",
        lambda self: chosen,
    )
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    cli._start_interactively(elsewhere)
    assert opened[-1] == (chosen, "welcome")


# ------------------------------------------------------------ readiness


def _diagnosis(ready: bool, model_ok: bool = True) -> provider_base.Diagnosis:
    return provider_base.Diagnosis(
        provider="claude",
        available=True,
        authenticated=ready,
        auth_method="Claude Platform API key" if ready else "none",
        account=None,
        inference="remote",
        billing="anthropic-console-credits",
        checks=[provider_base.Check("api_key", ready, "API key")],
        guidance=[] if ready else ["Set ANTHROPIC_API_KEY."],
    )


def test_readiness_needs_a_passing_test_for_the_same_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nf_splice.agents.providers import select

    state = {"ready": False}
    monkeypatch.setattr(
        readiness_module, "diagnose", lambda name: _diagnosis(state["ready"])
    )
    assert assess().level is ReadinessLevel.NOT_CONFIGURED
    select("claude", "model-a")
    assert assess().level is ReadinessLevel.INCOMPLETE  # no key yet
    state["ready"] = True
    unverified = assess()
    assert unverified.level is ReadinessLevel.UNVERIFIED and not unverified.usable
    readiness_module.record_verification("claude", "model-a")
    verified = assess()
    assert verified.usable and verified.model == "model-a"
    assert "Verified: claude" in verified.summary()
    assert "secret" not in json.dumps(credentials.preferences())
    select("claude", "model-b")  # another model is not verified
    assert assess().level is ReadinessLevel.UNVERIFIED
    select("claude", "model-a")
    state["ready"] = False  # e.g. the key was removed
    assert assess().level is ReadinessLevel.UNAVAILABLE
    readiness_module.clear_verification("claude")
    assert assess().level is ReadinessLevel.INCOMPLETE


def test_welcome_options_follow_the_working_copy_and_readiness() -> None:
    assert options(False, False, False) == ("prepare", "in-place", "inspect", "exit")
    assert options(False, True, True)[:2] == ("prepare", "open-copy")
    assert options(True, False, False) == ("manual", "setup-ai", "exit")
    assert options(True, True, False) == (
        "manual",
        "assisted",
        "autonomous",
        "ai-settings",
        "exit",
    )


# ------------------------------------------------------------ the workspace


def _visible_options(app: NfSpliceApp) -> list[str]:
    return [
        str(button.label)
        for button in app.query(".welcome-option").results(Button)
        if button.display
    ]


def _authorised(tmp_path: Path) -> Path:
    root = _pipeline(tmp_path / "rnaseq", git=False)
    authorise_in_place(root)
    return root


@pytest.mark.asyncio
async def test_welcome_without_ai_offers_manual_and_set_up_only(
    tmp_path: Path,
) -> None:
    root = _authorised(tmp_path)
    app = NfSpliceApp(root, user="Ada")
    async with app.run_test(size=(140, 50)) as pilot:
        await settle(app, pilot)
        assert app.current == "welcome"
        assert _visible_options(app) == [
            "[1] Start manual integration",
            "[2] Set up AI assistance",
            "[3] Exit",
        ]
        assert "AI assistance: Not configured" in str(
            app.query_one("#welcome-ai", Static).render()
        )
        assert app.screen.has_class("ai-off")  # no Ask/Assist/Autonomous buttons
        for selector in ("#top-ask", "#top-assist", "#top-autonomous"):
            assert not app.query_one(selector).display, selector
        # The canonical banner, unchanged.
        assert str(app.query_one("#welcome-banner", Static).render()) == BANNER
        # [1] starts manual integration fully offline.
        await pilot.press("1")
        await settle(app, pilot)
        assert app.model.all_drafts and app.current == "overview"


@pytest.mark.asyncio
async def test_welcome_with_an_unverified_provider_does_not_offer_agents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nf_splice.agents.providers import select

    monkeypatch.setattr(readiness_module, "diagnose", lambda name: _diagnosis(True))
    select("claude")
    root = _authorised(tmp_path)
    app = NfSpliceApp(root, user="Ada")
    async with app.run_test(size=(140, 50)) as pilot:
        await settle(app, pilot)
        assert app.ai_readiness is not None
        assert app.ai_readiness.level is ReadinessLevel.UNVERIFIED
        assert "Configured, not yet verified" in str(
            app.query_one("#welcome-ai", Static).render()
        )
        assert _visible_options(app)[1] == "[2] Set up AI assistance"
        assert not any("Assisted" in item for item in _visible_options(app))
        assert app.coordinator.provider is None  # nothing was connected


@pytest.mark.asyncio
async def test_welcome_with_a_verified_provider_offers_all_three_modes(
    tmp_path: Path,
) -> None:
    root = _authorised(tmp_path)
    app = NfSpliceApp(root, user="Ada", agent_provider=ScriptedProvider([]))
    async with app.run_test(size=(140, 50)) as pilot:
        await settle(app, pilot)
        assert _visible_options(app) == [
            "[1] Start manual integration",
            "[2] Assisted integration",
            "[3] Autonomous integration",
            "[4] AI provider settings",
            "[5] Exit",
        ]
        assert not app.screen.has_class("ai-off")
        await press(app, pilot, "#welcome-autonomous")
        # The same dock and scope approval as before: nothing starts by itself.
        assert app.query_one("#dock").display
        assert app.coordinator.engine is None


@needs_git
@pytest.mark.asyncio
async def test_original_pipeline_welcome_prepares_a_copy_and_reopens_there(
    tmp_path: Path,
) -> None:
    original = _pipeline(tmp_path / "rnaseq")
    before = _tree(original)
    app = NfSpliceApp(original, user="Ada")
    async with app.run_test(size=(140, 50)) as pilot:
        await settle(app, pilot)
        assert _visible_options(app) == [
            "[1] Prepare a safe working copy (recommended)",
            "[2] Work in this folder instead…",
            "[3] Inspect only (no changes)",
            "[4] Exit",
        ]
        app.start_manually()  # refused: this is the original
        await settle(app, pilot)
        assert not app.model.has_drafts
        await press(app, pilot, "#welcome-prepare")
        # Confirming prepares the copy, then the workspace exits to reopen there.
        app.screen.query_one("#confirm-ok", Button).press()
        for _ in range(200):
            if app.return_value is not None:
                break
            await pilot.pause(0.05)
    copy = tmp_path / "rnaseq-splice-integration"
    assert app.return_value == copy.resolve()
    assert read_record(copy) is not None
    assert _tree(original) == before
    # Reopening the original offers the copy instead of preparing again.
    assert [item["path"] for item in copies_of(original)] == [str(copy.resolve())]
    again = NfSpliceApp(original, user="Ada")
    async with again.run_test(size=(140, 50)) as pilot:
        await settle(again, pilot)
        assert "[2] Open the working copy you made earlier" in _visible_options(again)


@pytest.mark.asyncio
async def test_work_in_place_needs_explicit_consent(tmp_path: Path) -> None:
    original = _pipeline(tmp_path / "rnaseq", git=False)
    app = NfSpliceApp(original, user="Ada")
    async with app.run_test(size=(140, 50)) as pilot:
        await settle(app, pilot)
        await press(app, pilot, "#welcome-in-place")
        await press(app, pilot, "#confirm-cancel")
        assert read_record(original) is None
        await press(app, pilot, "#welcome-in-place")
        await press(app, pilot, "#confirm-ok")
        await settle(app, pilot)
        assert read_record(original)["in_place"] is True  # type: ignore[index]
        assert _visible_options(app)[0] == "[1] Start manual integration"


@pytest.mark.asyncio
async def test_resume_shows_progress_and_keeps_drafts(tmp_path: Path) -> None:
    root = _authorised(tmp_path)
    remember_integration(root)
    first = NfSpliceApp(root, user="Ada")
    async with first.run_test(size=(140, 50)) as pilot:
        await settle(first, pilot)
        await press(first, pilot, "#welcome-start")
    drafts = root / ".splice-local" / "drafts" / "bundle.draft.yaml"
    drafts.write_text(
        drafts.read_text(encoding="utf-8") + "# edited outside\n", encoding="utf-8"
    )
    edited = drafts.read_bytes()
    second = NfSpliceApp(root, user="Ada", start="welcome")
    async with second.run_test(size=(140, 50)) as pilot:
        await settle(second, pilot)
        assert _visible_options(second)[0] == "[1] Continue manual integration"
        progress = str(second.query_one("#welcome-progress", Static).render())
        assert "of 7 steps ready" in progress
        copy = str(second.query_one("#welcome-copy", Static).render())
        assert "Working in place, as you authorised" in copy
        await press(second, pilot, "#welcome-start")
        assert second.current not in {"welcome", "overview"}
    assert drafts.read_bytes() == edited  # the external edit is kept


# ------------------------------------------------------------ rendering


def _screen(app: NfSpliceApp) -> list[str]:
    return [strip.text for strip in app.screen._compositor.render_strips()]


@pytest.mark.parametrize("width", [80, 100, 120, 160])
@pytest.mark.asyncio
async def test_form_controls_have_no_block_glyph_edges(
    tmp_path: Path, width: int
) -> None:
    from textual.widgets import Collapsible

    root = _authorised(tmp_path)
    app = NfSpliceApp(root, user="Ada")
    async with app.run_test(size=(width, 60)) as pilot:
        await settle(app, pilot)
        await press(app, pilot, "#welcome-start")
        app.show_page("identity")
        await settle(app, pilot)
        screens = [_screen(app)]
        app.query_one("#identity-authors-section", Collapsible).collapsed = False
        await settle(app, pilot)
        app.query_one("#author-name").scroll_visible(animate=False, top=True)
        await settle(app, pilot)
        screens.append(_screen(app))
        app.query_one("#identity-description").focus()
        await settle(app, pilot)
        screens.append(_screen(app))
        for lines in screens:
            for line in lines:
                # The last two columns are the page's scrollbar.
                body = line[: width - 2]
                found = [glyph for glyph in "▊▎▌▐█" if glyph in body]
                assert not found, (width, found, line)
        for selector in ("#identity-name", "#author-name", "#author-affiliation"):
            assert app.query_one(selector, Input).size.width >= 14, (width, selector)
        assert app.query_one("#author-type").size.width >= 14


def test_the_stylesheet_has_no_tall_or_block_borders() -> None:
    sheet = (ROOT / "src" / "nf_splice" / "interfaces" / "tui" / "tui.tcss").read_text(
        encoding="utf-8"
    )
    rules = re.sub(r"/\*.*?\*/", "", sheet, flags=re.DOTALL)
    assert not re.search(r"border[a-z-]*:\s*(tall|thick|outer|inner|wide|panel)", rules)
