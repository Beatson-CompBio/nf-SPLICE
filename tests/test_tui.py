"""The unified workspace in manual mode: real services, real files (ADR-0067).

Every test drives the Textual application headlessly through the same
widgets a person uses and checks the drafts on disk afterwards. Screenshots
are written when ``NF_SPLICE_SCREENSHOTS`` names a folder.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
import yaml  # type: ignore[import-untyped]
from textual.widgets import Button, Checkbox, DataTable, Input, Select, TextArea, Tree

from layer_fixtures import edit_draft_file, write_pipeline
from multi_route import author_all, build, copy_fixture
from nf_splice.interfaces.tui import NavigationStore, NfSpliceApp
from nf_splice.interfaces.tui.editors import OutputEditor
from nf_splice.interfaces.tui.modals import (
    AccessDialog,
    ConfirmDialog,
    HelpDialog,
    ListDialog,
    ThemeDialog,
    ViewerDialog,
)
from nf_splice.interfaces.tui.navigation import PAGE_IDS, StepState, Target
from nf_splice.layers.base import LAYERS, read_layer
from tui_helpers import page_text, press, press_named, screenshot, settle

pytestmark = pytest.mark.asyncio
WIDE = (160, 50)
DRAFTS = ".splice-local/drafts"


def _draft(root: Path, layer: str) -> dict[str, Any]:
    state = read_layer(root, layer)
    assert state.draft is not None, state.error
    data: dict[str, Any] = state.draft.data
    return data


def _drafts(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted((root / DRAFTS).rglob("*"))
        if path.is_file()
    }


def _pipeline(tmp_path: Path) -> Path:
    root = tmp_path / "pipeline"
    root.mkdir()
    write_pipeline(root)
    (root / "nextflow.config").write_text(
        "manifest {\n    name = 'reference'\n    version = '1.0.0'\n"
        "    homePage = 'https://github.com/org/reference'\n"
        "    description = 'Reference pipeline.'\n}\n",
        encoding="utf-8",
    )
    return root


# ------------------------------------------------------------ start


async def test_start_manually_creates_six_drafts_once_then_overview(
    tmp_path: Path,
) -> None:
    root = _pipeline(tmp_path)
    app = NfSpliceApp(root, user="Ada")
    async with app.run_test(size=WIDE) as pilot:
        await settle(app, pilot)
        assert app.current == "welcome"
        assert app.model.step_state("welcome") is StepState.NOT_STARTED
        screenshot(app, "welcome")
        await press(app, pilot, "#welcome-start")
        # The worker finished before navigating, and the states are fresh
        # without pressing Ctrl+R.
        assert app.current == "overview"
        assert app.model.all_drafts
        assert app.model.step_state("identity") is not StepState.NOT_STARTED
        assert {spec.name for spec in LAYERS} == {
            name for name, view in app.model.layers.items() if view.exists
        }
        text = page_text(app)
        assert "6\nEditable drafts" in text
        assert "No bundle has been published yet. This is expected." in text
        screenshot(app, "overview")
        before = _drafts(root)
        app.show_page("welcome")
        await settle(app, pilot)
        await press(app, pilot, "#welcome-start")
        assert app.current == "overview"
        assert _drafts(root) == before  # starting again preserves every draft


async def test_identity_shows_sources_and_saves_a_targeted_patch(
    tmp_path: Path,
) -> None:
    root = _pipeline(tmp_path)
    app = NfSpliceApp(root, user="Ada", start="welcome")
    async with app.run_test(size=WIDE) as pilot:
        await settle(app, pilot)
        await press(app, pilot, "#welcome-start")
        draft = root / DRAFTS / "bundle.draft.yaml"
        draft.write_text(
            draft.read_text(encoding="utf-8") + "# a comment the author wrote\n",
            encoding="utf-8",
        )
        app.action_reload()
        await settle(app, pilot)
        app.show_page("identity")
        await settle(app, pilot)
        text = page_text(app)
        assert "✓ source: config" in text  # name, version and URL
        assert "derived from name" in text
        screenshot(app, "identity")
        name = app.screen.query_one("#identity-version", Input)
        name.value = "1.1.0"
        assert app.current_page().has_unsaved()  # type: ignore[union-attr]
        await press(app, pilot, "#identity-save")
        assert _draft(root, "bundle")["pipeline"]["version"] == "1.1.0"
        assert "# a comment the author wrote" in draft.read_text(encoding="utf-8")
        assert not app.current_page().has_unsaved()  # type: ignore[union-attr]
        # An edited value is shown as the person's, not as imported.
        assert "edited by a person" in page_text(app)


async def test_authors_take_a_normalised_orcid_or_refuse_an_invalid_one(
    tmp_path: Path,
) -> None:
    root = _pipeline(tmp_path)
    app = NfSpliceApp(root, user="Ada", start="welcome")
    async with app.run_test(size=WIDE) as pilot:
        await settle(app, pilot)
        await press(app, pilot, "#welcome-start")
        app.show_page("identity", Target("identity", field="authors"))
        await settle(app, pilot)
        screen = app.screen
        screen.query_one("#author-name", Input).value = "Ada Lovelace"
        screen.query_one("#author-orcid", Input).value = "0000-0002-1825-0098"
        await press(app, pilot, "#author-add")
        assert "not a valid ORCID" in str(screen.query_one("#author-error").render())
        screen.query_one("#author-orcid", Input).value = "0000-0002-1825-0097"
        await press(app, pilot, "#author-add")
        await press(app, pilot, "#identity-save")
        authors = _draft(root, "bundle")["pipeline"]["authors"]
        assert {
            "name": "Ada Lovelace",
            "type": "person",
            "orcid": ("https://orcid.org/0000-0002-1825-0097"),
        } in authors


async def test_a_stale_form_never_overwrites_an_external_edit(tmp_path: Path) -> None:
    root = _pipeline(tmp_path)
    app = NfSpliceApp(root, user="Ada", start="welcome")
    async with app.run_test(size=WIDE) as pilot:
        await settle(app, pilot)
        await press(app, pilot, "#welcome-start")
        app.show_page("identity")
        await settle(app, pilot)
        app.screen.query_one("#identity-version", Input).value = "9.9.9"
        edit_draft_file(
            root,
            "bundle",
            lambda data: data["pipeline"].update(description="Edited in vim."),
        )
        app.action_reload()
        await settle(app, pilot)
        assert "changed on disk while you were editing" in page_text(app)
        await press(app, pilot, "#identity-save")
        assert isinstance(app.screen, ListDialog)
        assert _draft(root, "bundle")["pipeline"]["description"] == "Edited in vim."
        assert _draft(root, "bundle")["pipeline"]["version"] == "1.0.0"
        await press(app, pilot, "#list-reload")
        assert app.screen.query_one("#identity-version", Input).value == "1.0.0"


# ------------------------------------------------------------ assays


async def test_assay_tree_has_one_state_per_assay_and_never_preselects(
    tmp_path: Path,
) -> None:
    root = _pipeline(tmp_path)
    app = NfSpliceApp(root, user="Ada", start="welcome")
    async with app.run_test(size=WIDE) as pilot:
        await settle(app, pilot)
        await press(app, pilot, "#welcome-start")
        app.show_page("assays")
        await settle(app, pilot)
        tree = app.screen.query_one("#assay-tree", Tree)
        nodes = [node for node in _walk(tree.root) if node.data is not None]
        selectable = [node for node in nodes if node.data.key is not None]
        assert selectable and not any(
            str(node.label).startswith("[x]") for node in selectable
        )
        xenium = [node for node in selectable if node.data.label == "Xenium RNA"]
        assert len(xenium) == 2  # under Imaging and under Transcriptomics
        # Organisational parents cannot be ticked.
        assert any(node.data.key is None for node in nodes)
        page = app.current_page()
        page._toggle(xenium[0].data.key)  # type: ignore[union-attr]
        await pilot.pause()
        assert all(str(node.label).startswith("[x]") for node in xenium)
        screenshot(app, "assays")
        await press(app, pilot, "#assay-save")
        declared = _draft(root, "bundle")["pipeline"]["assay_capabilities"]
        assert len(declared) == 1
        assert declared[0]["evidence"] == "asserted"
        assert declared[0]["rationale"].startswith("Declared by a person")


async def test_selecting_assay_rows_never_scans_the_repository(tmp_path: Path) -> None:
    root = _pipeline(tmp_path)
    app = NfSpliceApp(root, user="Ada", start="welcome")
    async with app.run_test(size=WIDE) as pilot:
        await settle(app, pilot)
        await press(app, pilot, "#welcome-start")
        app.show_page("assays")
        await settle(app, pilot)
        tree = app.screen.query_one("#assay-tree", Tree)
        tree.focus()
        calls = {"rglob": 0, "walk": 0}
        original_rglob = Path.rglob
        original_walk = os.walk

        def counted_rglob(self: Path, pattern: str) -> Any:
            calls["rglob"] += 1
            return original_rglob(self, pattern)

        def counted_walk(*args: Any, **kwargs: Any) -> Any:
            calls["walk"] += 1
            return original_walk(*args, **kwargs)

        with (
            mock.patch.object(Path, "rglob", counted_rglob),
            mock.patch("os.walk", counted_walk),
        ):
            for index in range(100):
                await pilot.press("down" if index % 2 == 0 else "up")
        assert calls == {"rglob": 0, "walk": 0}


def _walk(node: Any) -> list[Any]:
    found = []
    stack = list(node.children)
    while stack:
        item = stack.pop()
        found.append(item)
        stack.extend(item.children)
    return found


# ------------------------------------------------------------ parameters


def _fail_closed(root: Path) -> None:
    """A real nf-core shape: required input and outdir, nobody may supply them."""

    def contract(data: dict[str, Any]) -> None:
        data.pop("$defs", None)
        data.pop("allOf", None)
        data["required"] = ["input", "outdir"]
        data["properties"] = {
            "input": {
                "type": "string",
                "format": "file-path",
                "description": "Sample sheet.",
                "x-splice-access": {"editable_by": []},
            },
            "outdir": {
                "type": "string",
                "format": "directory-path",
                "description": "Results directory.",
                "x-splice-access": {"editable_by": []},
            },
            "threshold": {
                "type": "number",
                "default": 0.5,
                "x-splice-access": {"editable_by": []},
            },
        }

    edit_draft_file(root, "inputs", contract)


async def test_required_parameters_nobody_may_supply_are_blockers_until_assigned(
    tmp_path: Path,
) -> None:
    root = _pipeline(tmp_path)
    app = NfSpliceApp(root, user="Ada", start="welcome")
    async with app.run_test(size=WIDE) as pilot:
        await settle(app, pilot)
        await press(app, pilot, "#welcome-start")
        _fail_closed(root)
        app.action_reload()
        await settle(app, pilot)
        app.show_page("parameters")
        await settle(app, pilot)
        assert {item.name for item in app.model.submission_blockers} == {
            "input",
            "outdir",
        }
        text = page_text(app)
        assert "input: required, has no default" in text
        assert "The platform may legitimately supply an output directory." in text
        assert app.model.step_state("parameters") is StepState.NEEDS_REVIEW
        screenshot(app, "parameters-blockers")
        # Nothing is granted implicitly: the import stays fail-closed.
        inputs = _draft(root, "inputs")
        assert inputs["properties"]["input"]["x-splice-access"]["editable_by"] == []
        await press_named(app, pilot, "parameter-fix-input")
        table = app.screen.query_one("#parameter-table", DataTable)
        assert table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value == (
            "input"
        )
        await pilot.press("u")
        page = app.current_page()
        page.marked = {"outdir", "threshold"}  # type: ignore[union-attr]
        await press(app, pilot, "#parameter-bulk")
        dialog = app.screen
        assert isinstance(dialog, AccessDialog)
        dialog.query_one("#access-platform", Checkbox).value = True
        await press(app, pilot, "#access-apply")
        await press(app, pilot, "#parameter-save")
        properties = _draft(root, "inputs")["properties"]
        assert properties["input"]["x-splice-access"]["editable_by"] == ["user"]
        assert properties["outdir"]["x-splice-access"]["editable_by"] == ["platform"]
        assert properties["threshold"]["x-splice-access"]["editable_by"] == ["platform"]
        assert not app.model.submission_blockers


# ------------------------------------------------------------ outputs


async def _add_output(app: NfSpliceApp, pilot: Any, values: dict[str, Any]) -> None:
    editor = app.screen
    assert isinstance(editor, OutputEditor)
    editor.query_one("#output-title", Input).value = values["title"]
    await pilot.pause()
    editor.query_one("#output-description", TextArea).text = values["description"]
    editor.query_one("#output-category", Input).value = values["category"]
    editor.query_one("#output-formats", Input).value = values["formats"]
    editor.query_one(f"#scope-{values['scope']}").value = True  # type: ignore[attr-defined]
    await pilot.pause()
    await press(app, pilot, "#editor-next")
    editor.query_one("#output-example", Input).value = values["example"]
    await press(app, pilot, "#editor-split")
    for index, kind in values["parts"].items():
        for select in editor.query(Select):
            if select.name == f"part-{index}":
                select.value = kind
    await pilot.pause()
    await press(app, pilot, "#editor-save")


async def test_one_output_in_two_steps_then_duplicate_edit_and_remove(
    tmp_path: Path,
) -> None:
    root = _pipeline(tmp_path)
    app = NfSpliceApp(root, user="Ada", start="welcome")
    async with app.run_test(size=WIDE) as pilot:
        await settle(app, pilot)
        await press(app, pilot, "#welcome-start")
        app.show_page("outputs")
        await settle(app, pilot)
        assert _draft(root, "outputs")["outputs"] == []  # no speculative entries
        text = page_text(app)
        assert "No output entries yet" in text
        assert "0 DESCRIBED" in text
        assert "Needs confirmation" in text  # not the pipeline release
        screenshot(app, "outputs-empty")
        await press(app, pilot, "#outputs-add-first")
        screenshot(app, "add-output-step-1")
        # A required field left empty is refused with the field named.
        await press(app, pilot, "#editor-next")
        assert "Complete: title" in str(app.screen.query_one("#error-what").render())
        await _add_output(
            app,
            pilot,
            {
                "title": "Gene counts",
                "description": "Raw gene-level counts.",
                "category": "quantification",
                "formats": "tsv",
                "scope": "sample",
                "example": "quantification/SAMPLE1/counts.tsv",
                "parts": {1: "sample"},
            },
        )
        outputs = _draft(root, "outputs")["outputs"]
        assert outputs == [
            {
                "key": "gene_counts",
                "title": "Gene counts",
                "description": "Raw gene-level counts.",
                "category": "quantification",
                "formats": ["tsv"],
                "scopes": ["sample"],
                "entity_types": ["file"],
                "path_patterns": ["^quantification/{sample}/counts\\.tsv$"],
            }
        ]
        text = page_text(app)
        assert "Saved Gene counts (gene_counts)" in text
        screenshot(app, "outputs-catalogue")
        await press(app, pilot, "#outputs-duplicate-this")
        editor = app.screen
        assert isinstance(editor, OutputEditor)
        # The key is suggested from the new title, never the original key.
        assert editor.query_one("#output-key", Input).value == "gene_counts_copy"
        assert editor.query_one("#output-title", Input).value == "Gene counts (copy)"
        await press(app, pilot, "#editor-cancel")
        await press(app, pilot, "#outputs-version-first")
        assert _draft(root, "outputs")["contract"]["schema_version"] == "1.0.0"
        await press(app, pilot, "#outputs-remove")
        assert isinstance(app.screen, ConfirmDialog)
        await press(app, pilot, "#confirm-ok")
        assert _draft(root, "outputs")["outputs"] == []


async def test_an_invalid_pattern_is_refused_in_place(tmp_path: Path) -> None:
    root = _pipeline(tmp_path)
    app = NfSpliceApp(root, user="Ada", start="welcome")
    async with app.run_test(size=WIDE) as pilot:
        await settle(app, pilot)
        await press(app, pilot, "#welcome-start")
        app.show_page("outputs")
        await settle(app, pilot)
        await press(app, pilot, "#outputs-add-first")
        editor = app.screen
        editor.query_one("#output-title", Input).value = "Report"
        await pilot.pause()
        editor.query_one("#output-description", TextArea).text = "Job report."
        editor.query_one("#output-category", Input).value = "report"
        editor.query_one("#output-formats", Input).value = "html"
        await press(app, pilot, "#editor-next")
        await press(app, pilot, "#editor-advanced")
        editor.query_one("#output-pattern", Input).value = "reports/(unclosed"
        await press(app, pilot, "#editor-save")
        assert isinstance(app.screen, OutputEditor)
        assert "anchor the pattern" in str(editor.query_one("#error-where").render())
        assert _draft(root, "outputs")["outputs"] == []


# ------------------------------------------------------------ review and publish


async def test_review_groups_blockers_and_fix_opens_the_field(tmp_path: Path) -> None:
    root = _pipeline(tmp_path)
    app = NfSpliceApp(root, user="Ada", start="welcome")
    async with app.run_test(size=WIDE) as pilot:
        await settle(app, pilot)
        await press(app, pilot, "#welcome-start")
        app.show_page("review")
        await settle(app, pilot)
        page = app.current_page()
        groups = page.groups  # type: ignore[union-attr]
        assert "assays" in groups and "outputs" in groups
        # One root cause (no assay) is not repeated in every layer.
        assert not any(
            item.code == "identity_not_ready"
            for items in groups.values()
            for item in items
        )
        text = page_text(app)
        assert "NOT READY TO PUBLISH" in text
        assert app.screen.query_one("#review-publish", Button).disabled
        screenshot(app, "review")
        await press_named(app, pilot, "review-fix-outputs")
        assert app.current == "outputs"


async def test_publish_shows_the_plan_and_four_separate_facts(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path)
    author_all(root)
    app = NfSpliceApp(root, user="Ada", start="publish")
    async with app.run_test(size=WIDE) as pilot:
        await settle(app, pilot)
        text = page_text(app)
        assert "READY TO PUBLISH" in text
        assert "create     splice/bundle.json" in text
        assert not (root / "splice" / "bundle.json").exists()
        screenshot(app, "publish-plan")
        await press(app, pilot, "#publish-go")
        app.request_readiness(force=True)
        await settle(app, pilot)
        assert (root / "splice" / "bundle.json").is_file()
        text = page_text(app)
        assert "Published ✓" in text
        assert "Structural validation ✓" in text
        assert "Scientific classification ✓ assessed" in text
        assert "SPLICE ingestion readiness" in text
        screenshot(app, "published")
    # Changing a draft, then publishing again, asks before replacing files.
    edit_draft_file(
        root, "bundle", lambda data: data["pipeline"].update(description="Changed.")
    )
    app = NfSpliceApp(root, user="Ada", start="publish")
    async with app.run_test(size=WIDE) as pilot:
        await settle(app, pilot)
        await press(app, pilot, "#publish-go")
        assert isinstance(app.screen, ConfirmDialog)
        await press(app, pilot, "#confirm-cancel")
        bundle = (root / "splice" / "bundle.json").read_text(encoding="utf-8")
        assert "Changed." not in bundle


async def test_inspect_only_never_writes(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path)
    author_all(root)
    before = _drafts(root)
    app = NfSpliceApp(root, user="Ada", start="identity", inspect_only=True)
    async with app.run_test(size=WIDE) as pilot:
        await settle(app, pilot)
        app.screen.query_one("#identity-version", Input).value = "9.9.9"
        await press(app, pilot, "#identity-save")
        app.show_page("publish")
        await settle(app, pilot)
        assert app.screen.query_one("#publish-go", Button).disabled
    assert _drafts(root) == before
    assert not (root / "splice" / "bundle.json").exists()


# ------------------------------------------------------------ shell


async def test_the_workspace_reopens_where_it_was_left_and_reports_edits(
    tmp_path: Path,
) -> None:
    root = copy_fixture(tmp_path)
    author_all(root)
    store = NavigationStore(tmp_path / "navigation")
    app = NfSpliceApp(root, navigation=store)
    async with app.run_test(size=WIDE) as pilot:
        await settle(app, pilot)
        app.show_page("software")
        await settle(app, pilot)
    edit_draft_file(
        root, "bundle", lambda data: data["pipeline"].update(description="Edited.")
    )
    again = NfSpliceApp(root, navigation=store)
    async with again.run_test(size=WIDE) as pilot:
        await settle(again, pilot)
        assert again.current == "software"
        message = str(again.query_one("#status-message").render())
        assert "changed outside nf-SPLICE" in message


async def test_every_page_renders_at_120_and_80_columns_and_warns_when_tiny(
    tmp_path: Path,
) -> None:
    root = copy_fixture(tmp_path)
    author_all(root)
    for size in ((120, 40), (80, 30)):
        app = NfSpliceApp(root, start="welcome")
        async with app.run_test(size=size) as pilot:
            await settle(app, pilot)
            for page_id in PAGE_IDS:
                app.show_page(page_id)
                await settle(app, pilot)
                assert app.current_page() is not None
                assert app.query_one("#nav-continue").region.width > 0 or (
                    page_id == "publish"
                )
                screenshot(app, f"{page_id}-{size[0]}")
            assert app.screen.has_class("wide" if size[0] >= 120 else "medium")
    app = NfSpliceApp(root, start="welcome")
    async with app.run_test(size=(50, 16)) as pilot:
        await settle(app, pilot)
        assert app.query_one("#too-small").display
        assert not app.query_one("#main").display


async def test_help_theme_drafts_and_sources_open_bounded_dialogs(
    tmp_path: Path,
) -> None:
    root = copy_fixture(tmp_path)
    author_all(root)
    app = NfSpliceApp(root, start="outputs")
    async with app.run_test(size=WIDE) as pilot:
        await settle(app, pilot)
        await pilot.press("f1")
        await pilot.pause()
        assert isinstance(app.screen, HelpDialog)
        await pilot.press("escape")
        await pilot.pause()
        await press(app, pilot, "#tool-theme")
        assert isinstance(app.screen, ThemeDialog)
        await pilot.press("escape")
        await pilot.pause()
        await press(app, pilot, "#tool-drafts")
        assert isinstance(app.screen, ListDialog)
        table = app.screen.query_one("#list-table", DataTable)
        assert table.row_count >= 6
        await press(app, pilot, "#list-view")
        assert isinstance(app.screen, ViewerDialog)
        await pilot.press("escape")
        await pilot.pause()
        await press(app, pilot, "#tool-sources")
        await settle(app, pilot)
        assert isinstance(app.screen, ListDialog)
        paths = [
            str(app.screen.query_one("#list-table", DataTable).get_row_at(index)[0])
            for index in range(app.screen.query_one("#list-table", DataTable).row_count)
        ]
        assert "main.nf" in paths
        assert not any(path.startswith(".splice-local") for path in paths)


async def test_routes_are_browsed_read_only_and_excluded_with_a_reason(
    tmp_path: Path,
) -> None:
    root = copy_fixture(tmp_path)
    author_all(root)
    edit_draft_file(
        root,
        "outputs",
        lambda data: data.update(
            outputs=[
                item for item in data["outputs"] if item["key"] != "multiqc_report"
            ]
        ),
    )
    before = _drafts(root)
    app = NfSpliceApp(root, user="Ada", start="outputs")
    async with app.run_test(size=WIDE) as pilot:
        await settle(app, pilot)
        await press(app, pilot, "#outputs-routes")
        await settle(app, pilot)
        dialog = app.screen
        assert isinstance(dialog, ListDialog)
        rows = [
            [str(cell) for cell in dialog.query_one(DataTable).get_row_at(index)]
            for index in range(dialog.query_one(DataTable).row_count)
        ]
        assert any(
            row[1] == "MULTIQC" and row[0].startswith("not covered") for row in rows
        )
        assert _drafts(root) == before  # browsing writes nothing
        await press(app, pilot, "#dialog-close")
        app.exclude_route("MULTIQC", "multiqc/multiqc_report.html")
        await pilot.pause()
        form = app.screen
        form.query_one("#form-kind", Select).value = "out_of_scope"
        form.query_one("#form-reason", Input).value = "The report stays internal."
        await press(app, pilot, "#form-submit")
        excluded = _draft(root, "outputs")["excluded_routes"]
        assert {
            "glob": "multiqc/multiqc_report.html",
            "kind": "out_of_scope",
            "reason": "The report stays internal.",
        } in excluded


async def test_start_fresh_backs_up_old_drafts_and_reseeds_without_guesses(
    tmp_path: Path,
) -> None:
    root = copy_fixture(tmp_path)
    author_all(root)
    build(root)
    old = _draft(root, "outputs")
    app = NfSpliceApp(root, user="Ada", start="overview")
    async with app.run_test(size=WIDE) as pilot:
        await settle(app, pilot)
        await press(app, pilot, "#overview-fresh")
        assert isinstance(app.screen, ConfirmDialog)
        await press(app, pilot, "#confirm-ok")
    backups = list((root / ".splice-local" / "backups").glob("drafts-*"))
    assert len(backups) == 1
    saved = yaml.safe_load(
        (backups[0] / "drafts" / "outputs.draft.yaml").read_text(encoding="utf-8")
    )
    assert saved["outputs"] == old["outputs"]
    # The published catalogue (written by people) seeds the fresh draft.
    assert sorted(item["key"] for item in _draft(root, "outputs")["outputs"]) == sorted(
        item["key"] for item in old["outputs"]
    )


async def test_every_page_reads_without_the_reserved_word(tmp_path: Path) -> None:
    from nf_splice.vocabulary import reserved_terms_in

    root = copy_fixture(tmp_path)
    author_all(root)
    app = NfSpliceApp(root, user="Ada", start="welcome")
    async with app.run_test(size=WIDE) as pilot:
        await settle(app, pilot)
        for page_id in PAGE_IDS:
            app.show_page(page_id)
            await settle(app, pilot)
            text = page_text(app)
            assert not reserved_terms_in(text), (page_id, reserved_terms_in(text))
            screenshot(app, f"page-{page_id}")
