"""Guided Textual wizard: navigation, editing, sessions and CLI equivalence."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from textual.widgets import DataTable, Input, Select, Switch
from typer.testing import CliRunner

from layer_fixtures import write_pipeline, write_root_crate
from nf_splice.cli import app as cli
from nf_splice.drafts import read_yaml
from nf_splice.interfaces.tui import NfSpliceApp, SessionStore
from nf_splice.interfaces.tui.screens.outputs import OutputsView
from nf_splice.layers.base import LAYERS, load_review_state
from nf_splice.layers.outputs import discover_outputs
from tui_helpers import check_snapshot, press, screen_text, settle

SIZE = (160, 60)
runner = CliRunner()


def _pipeline(root: Path) -> None:
    root.mkdir(exist_ok=True)
    write_pipeline(root)
    (root / "nextflow.config").write_text(
        "manifest {\n    name = 'reference'\n    version = '1.0.0'\n"
        "    homePage = 'https://github.com/org/reference'\n"
        "    description = 'Reference pipeline.'\n}\n"
        "profiles { local { includeConfig 'conf/local.config' } }\n",
        encoding="utf-8",
    )
    write_root_crate(root, "reference", "1.0.0")


def _cli(root: Path, *arguments: str) -> None:
    result = runner.invoke(
        cli, ["--actor", "Ada", *arguments, "--repository", str(root)]
    )
    assert result.exit_code == 0, result.output


ASSAY_RATIONALE = "Documented library types: poly(A) and total RNA"


def _author_with_cli(root: Path) -> None:
    _cli(root, "init", "--accept-detected", "--contract-version", "1.0.0")
    _cli(
        root,
        "configure",
        "identity",
        "--add-assay",
        "polya_rnaseq",
        "--add-assay",
        "total_rnaseq",
        "--assay-rationale",
        ASSAY_RATIONALE,
    )
    _cli(
        root,
        "configure",
        "inputs",
        "--set",
        "threshold=user,agent",
        "--set",
        "outdir=platform",
    )
    _cli(
        root,
        "configure",
        "outputs",
        "--set",
        "report.description=Job report.",
        "--set",
        "report.category=job_report",
    )
    _cli(root, "configure", "components", "--require-downloadable", "false")
    _cli(
        root,
        "configure",
        "execution-profiles",
        "--set",
        "default.type=development",
        "--set",
        "default.description=Local development.",
        "--set",
        "default.config_adopt=conf/local.config",
        "--default",
        "default",
    )
    _cli(root, "configure", "provenance", "--strategy", "include")
    _cli(root, "build", "all")


async def _author_with_tui(root: Path, snapshots: bool = False) -> None:
    app = NfSpliceApp(root, actor="Ada")
    async with app.run_test(size=SIZE) as pilot:
        await settle(app, pilot)
        if snapshots:
            check_snapshot("welcome", screen_text(app))
        await press(app, pilot, "#welcome-create")
        assert app.current == "repository"
        if snapshots:
            check_snapshot("repository", screen_text(app))

        app.show_step("identity")
        await settle(app, pilot)
        if snapshots:
            check_snapshot("identity-detected", screen_text(app))
        await press(app, pilot, "#identity-confirm")

        app.show_step("assays")
        await settle(app, pilot)
        app.query_one("#assays-rationale", Input).value = ASSAY_RATIONALE
        table = app.query_one("#assays-table", DataTable)
        for code in ("polya_rnaseq", "total_rnaseq"):
            table.move_cursor(row=table.get_row_index(code))
            await press(app, pilot, "#assays-add")
        if snapshots:
            check_snapshot("assays", screen_text(app))

        app.show_step("inputs")
        await settle(app, pilot)
        table = app.query_one("#inputs-table", DataTable)
        table.focus()
        table.move_cursor(row=table.get_row_index("threshold"))
        await pilot.press("u", "g")
        table.move_cursor(row=table.get_row_index("outdir"))
        await pilot.press("p")
        if snapshots:
            check_snapshot("inputs-staged", screen_text(app))
        await press(app, pilot, "#inputs-save")

        app.show_step("outputs")
        await settle(app, pilot)
        view = app.current_view()
        assert isinstance(view, OutputsView)
        catalogue = app.query_one("#outputs-catalogue", DataTable)
        catalogue.move_cursor(row=catalogue.get_row_index("report"))
        await settle(app, pilot)
        app.query_one("#output-description", Input).value = "Job report."
        app.query_one("#output-category", Input).value = "job_report"
        await press(app, pilot, "#outputs-save")
        if snapshots:
            check_snapshot("outputs-reviewed", screen_text(app))

        app.show_step("components")
        await settle(app, pilot)
        app.query_one("#components-require", Switch).value = False
        await press(app, pilot, "#components-policy")
        if snapshots:
            check_snapshot("components", screen_text(app))

        app.show_step("profiles")
        await settle(app, pilot)
        profiles = app.query_one("#profiles-table", DataTable)
        profiles.move_cursor(row=profiles.get_row_index("default"))
        await settle(app, pilot)
        app.query_one("#profile-type", Select).value = "development"
        app.query_one("#profile-description", Input).value = "Local development."
        app.query_one("#profile-route", Select).value = "adopt"
        app.query_one("#profile-source", Input).value = "conf/local.config"
        await press(app, pilot, "#profiles-save")
        await press(app, pilot, "#profiles-make-default")
        if snapshots:
            check_snapshot("profiles", screen_text(app))

        app.show_step("provenance")
        await settle(app, pilot)
        await press(app, pilot, "#provenance-include")
        if snapshots:
            check_snapshot("provenance", screen_text(app))

        app.show_step("drafts")
        await settle(app, pilot)
        if snapshots:
            check_snapshot("drafts", screen_text(app))
        app.show_step("review")
        await settle(app, pilot)
        assert app.snapshot.publish_ready, app.snapshot.publish_blockers
        if snapshots:
            check_snapshot("review-ready", screen_text(app))
        app.show_step("build")
        await settle(app, pilot)
        if snapshots:
            check_snapshot("build-plan", screen_text(app))
        await press(app, pilot, "#build-publish")
        assert app.snapshot.bundle_valid, app.query_one("#status").render()
        app.show_step("done")
        await settle(app, pilot)
        if snapshots:
            check_snapshot("done", screen_text(app))


def _draft_semantics(root: Path) -> dict[str, Any]:
    result = {}
    for spec in LAYERS:
        state = read_yaml(root, spec.draft)
        assert state.draft is not None, spec.draft
        result[spec.draft] = state.draft.data
    return result


def _finals(root: Path) -> dict[str, bytes]:
    splice = root / "splice"
    return {
        path.relative_to(splice).as_posix(): path.read_bytes()
        for path in sorted(splice.rglob("*"))
        if path.is_file() and "drafts" not in path.relative_to(splice).parts
    }


@pytest.mark.asyncio
async def test_cli_and_tui_produce_identical_drafts_and_bundles(tmp_path: Path) -> None:
    """Hard regression gate: the same decisions through CLI and TUI."""
    cli_root, tui_root = tmp_path / "cli", tmp_path / "tui"
    _pipeline(cli_root)
    _pipeline(tui_root)
    _author_with_cli(cli_root)
    await _author_with_tui(tui_root, snapshots=True)
    assert _draft_semantics(cli_root) == _draft_semantics(tui_root)
    assert _finals(cli_root) == _finals(tui_root)
    events = load_review_state(tui_root, "outputs").events
    assert {event["origin"] for event in events} == {"manual_tui"}
    assert not (tui_root / "splice" / "nf-splice.yaml").exists()


@pytest.mark.asyncio
async def test_navigation_locking_back_defer_and_help(tmp_path: Path) -> None:
    _pipeline(tmp_path / "repo")
    app = NfSpliceApp(tmp_path / "repo")
    async with app.run_test(size=SIZE) as pilot:
        await settle(app, pilot)
        app.show_step("build")
        await pilot.pause()
        assert app.current == "welcome"
        assert "locked" in str(app.query_one("#status").render())
        await press(app, pilot, "#welcome-create")
        await pilot.press("ctrl+n")
        await settle(app, pilot)
        assert app.current == "identity"
        await pilot.press("escape")
        await settle(app, pilot)
        assert app.current == "repository"
        app.show_step("identity")
        await settle(app, pilot)
        await pilot.press("ctrl+d")
        await settle(app, pilot)
        assert "identity" in app.session.deferred and app.current == "assays"
        labels = [str(label.render()) for label in app.query("#rail Label")]
        assert any("» Identity" in label for label in labels)
        await pilot.press("f1")
        await pilot.pause()
        assert app.screen.__class__.__name__ == "HelpScreen"
        await pilot.press("escape")


@pytest.mark.asyncio
async def test_identity_edits_are_targeted_patches_preserving_comments(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    _pipeline(root)
    app = NfSpliceApp(root, actor="Ada")
    async with app.run_test(size=SIZE) as pilot:
        await settle(app, pilot)
        await press(app, pilot, "#welcome-create")
        draft = root / ".splice-local" / "drafts" / "bundle.draft.yaml"
        draft.write_text("# kept comment\n" + draft.read_text(encoding="utf-8"))
        await pilot.press("ctrl+r")
        app.show_step("identity")
        await settle(app, pilot)
        app.query_one("#identity-title", Input).value = "Reference Pipeline"
        app.query_one("#author-name", Input).value = "Ada Lovelace"
        await press(app, pilot, "#author-add")
        await press(app, pilot, "#identity-save")
        text = draft.read_text(encoding="utf-8")
        assert "# kept comment" in text
        assert "title: Reference Pipeline" in text and "Ada Lovelace" in text
        app.query_one("#identity-repository_url", Input).value = "not a url"
        await press(app, pilot, "#identity-save")
        issues = str(app.query_one("#identity-issues").render())
        assert "repository_url" in issues
        assert "Error" not in str(app.query_one("#status").render())
        check_snapshot("identity-error", screen_text(app))


@pytest.mark.asyncio
async def test_inspect_only_mode_never_writes(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _pipeline(root)
    app = NfSpliceApp(root)
    async with app.run_test(size=SIZE) as pilot:
        await settle(app, pilot)
        await press(app, pilot, "#welcome-inspect")
        app.show_step("identity")
        await settle(app, pilot)
        app.perform("write", lambda: None)
        assert "Inspect-only" in str(app.query_one("#status").render())
    assert not (root / "splice").exists()


@pytest.mark.asyncio
async def test_sessions_resume_but_state_derives_from_files(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _pipeline(root)
    store = SessionStore(tmp_path / "sessions")
    app = NfSpliceApp(root, sessions=store)
    async with app.run_test(size=SIZE) as pilot:
        await settle(app, pilot)
        await press(app, pilot, "#welcome-create")
        app.show_step("identity")
        await settle(app, pilot)
        app.show_step("outputs")
        await settle(app, pilot)
        assert app.current == "outputs"
        app.query_one("#output-title", Input).value = "Half typed"
        app.show_step("components")
        await settle(app, pilot)
    saved = store.load(root)
    assert saved is not None and saved.current_step == "components"
    assert "outputs" in saved.unsaved
    assert not list((root / "splice").rglob("*session*"))

    draft = root / ".splice-local" / "drafts" / "outputs.draft.yaml"
    draft.write_text(draft.read_text(encoding="utf-8") + "# external\n")
    resumed = NfSpliceApp(root, sessions=store)
    async with resumed.run_test(size=SIZE) as pilot:
        await settle(resumed, pilot)
        assert resumed.current == "components"
        assert "outputs.draft.yaml" in str(resumed.query_one("#status").render())
    store.delete(root)
    fresh = NfSpliceApp(root, sessions=store)
    async with fresh.run_test(size=SIZE) as pilot:
        await settle(fresh, pilot)
        assert fresh.snapshot.layer_state("bundle") != "missing"


@pytest.mark.asyncio
async def test_selection_survives_external_edits_and_rediscovery(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    _pipeline(root)
    app = NfSpliceApp(root, actor="Ada")
    async with app.run_test(size=SIZE) as pilot:
        await settle(app, pilot)
        await press(app, pilot, "#welcome-create")
        app.show_step("identity")
        await settle(app, pilot)
        app.show_step("outputs")
        await settle(app, pilot)
        table = app.query_one("#outputs-catalogue", DataTable)
        table.move_cursor(row=table.get_row_index("report"))
        # Someone edits the YAML in an editor and discovery runs again.
        draft = root / ".splice-local" / "drafts" / "outputs.draft.yaml"
        draft.write_text(
            draft.read_text(encoding="utf-8").replace(
                "outputs:\n",
                "outputs:\n"
                "  - key: aaa_first\n"
                "    title: First\n"
                "    description: Written in an editor.\n"
                "    category: summaries\n"
                "    formats: [txt]\n"
                "    scopes: [job]\n"
                "    entity_types: [file]\n"
                "    path_patterns: ['^aaa/first\\.txt$']\n",
                1,
            ),
            encoding="utf-8",
        )
        tree = tmp_path / "tree"
        (tree / "aaa").mkdir(parents=True)
        (tree / "aaa" / "first.txt").write_text("x", encoding="utf-8")
        discover_outputs(root, example_output_tree=tree)
        await pilot.press("ctrl+r")
        await settle(app, pilot)
        view = app.current_view()
        assert isinstance(view, OutputsView)
        assert view.selected_output() == "report"
        app.query_one("#output-description", Input).value = "Job report."
        app.query_one("#output-category", Input).value = "job_report"
        await press(app, pilot, "#outputs-save")
    text = draft.read_text(encoding="utf-8")
    assert "Written in an editor." in text and "description: Job report." in text
    statuses = {
        entry["status"]
        for entry in load_review_state(root, "outputs").candidates.values()
    }
    assert "rejected" not in statuses and "accepted" not in statuses
