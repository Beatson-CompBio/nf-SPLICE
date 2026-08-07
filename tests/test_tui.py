"""Textual Pilot tests for the shared workspace application shell."""

import asyncio
import json
from pathlib import Path

from textual.widgets import Button, Input, ListView, Select, Static
from typer.testing import CliRunner

from nf_splice.cli import app as cli_app
from nf_splice.interfaces.tui import NfSpliceApp
from nf_splice.services import (
    ApplicationService,
    load_repository_document,
    unresolved_component_candidates,
    unresolved_input_candidates,
)

runner = CliRunner()


def test_tui_starts_with_shared_snapshot_and_navigates_layers(
    tmp_path: Path,
) -> None:
    (tmp_path / "main.nf").write_text("workflow {}\n", encoding="utf-8")
    snapshot = ApplicationService().inspect(tmp_path)
    app = NfSpliceApp(snapshot)

    async def exercise() -> None:
        async with app.run_test() as pilot:
            repository = app.query_one("#repository", Static)
            layer_detail = app.query_one("#layer-detail", Static)
            evidence = app.query_one("#evidence", Static)
            layers = app.query_one("#layers", ListView)

            assert str(tmp_path.resolve()) in str(repository.content)
            assert "Identity" in str(layer_detail.content)
            assert "Nextflow Source: 1" in str(evidence.content)
            assert layers.index == 0

            await pilot.press("down")
            await pilot.pause()

            assert layers.index == 1
            assert "Inputs" in str(layer_detail.content)

    asyncio.run(exercise())


def test_tui_applies_the_same_input_and_component_review_services(
    tmp_path: Path,
) -> None:
    service = ApplicationService()
    service.initialise(
        tmp_path,
        name="pipeline",
        version="1.0.0",
        repository_url="https://github.com/org/pipeline",
    )
    (tmp_path / "nextflow_schema.json").write_text(
        json.dumps(
            {
                "$defs": {
                    "analysis": {
                        "title": "Analysis",
                        "properties": {
                            "threshold": {
                                "type": "number",
                                "description": "Threshold.",
                            }
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    module_path = tmp_path / "modules" / "local" / "tool"
    module_path.mkdir(parents=True)
    (module_path / "meta.yml").write_text(
        "name: tool\ntools:\n  - tool:\n      description: Tool\n",
        encoding="utf-8",
    )
    (module_path / "main.nf").write_text(
        "process TOOL {\n  container 'quay.io/example/tool:1.0'\n\n  input:\n}\n",
        encoding="utf-8",
    )
    (tmp_path / "modules.json").write_text(
        json.dumps(
            {
                "items": [
                    {
                        "kind": "module",
                        "path": "modules/local/tool",
                        "namespace": "local",
                        "tool": "tool",
                        "name": "tool",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    service.discover_inputs(tmp_path)
    service.discover_components(tmp_path)
    app = NfSpliceApp(service.inspect(tmp_path), tmp_path, service)

    async def exercise() -> None:
        async with app.run_test() as pilot:
            app.query_one("#input-classification", Select).value = "user-configurable"
            app.query_one("#save-input", Button).press()
            await pilot.pause()
            app.query_one("#accept-component", Button).press()
            await pilot.pause()

    asyncio.run(exercise())
    document = load_repository_document(tmp_path)

    assert unresolved_input_candidates(document) == ()
    assert unresolved_component_candidates(document) == ()


def test_tui_previews_then_applies_legacy_migration(tmp_path: Path) -> None:
    source = tmp_path / "nf-splice.yaml"
    source.write_text(
        "schema_version: '1.0'\n"
        "pipeline: {}\n"
        "evidence: []\n"
        "decisions: []\n"
        "layers: []\n",
        encoding="utf-8",
    )
    service = ApplicationService()
    app = NfSpliceApp(service.inspect(tmp_path), tmp_path, service)

    async def exercise() -> None:
        async with app.run_test() as pilot:
            app.query_one("#preview-migration", Button).press()
            await pilot.pause()
            assert not (tmp_path / "splice").exists()
            app.query_one("#apply-migration", Button).press()
            await pilot.pause()

    asyncio.run(exercise())

    assert source.is_file()
    assert (tmp_path / "splice" / "nf-splice.yaml").is_file()


def _milestone_d_repository(root: Path) -> ApplicationService:
    service = ApplicationService()
    service.initialise(
        root,
        name="pipeline",
        version="1.0.0",
        repository_url="https://github.com/org/pipeline",
    )
    module = root / "modules" / "local" / "tool"
    module.mkdir(parents=True)
    (module / "meta.yml").write_text(
        "name: tool\ntools:\n  - tool:\n      description: Tool\n",
        encoding="utf-8",
    )
    (module / "main.nf").write_text(
        "process TOOL {\n  container 'quay.io/example/tool:1.0'\n\n  input:\n}\n",
        encoding="utf-8",
    )
    (root / "modules.json").write_text(
        json.dumps(
            {
                "items": [
                    {
                        "kind": "module",
                        "path": "modules/local/tool",
                        "namespace": "local",
                        "tool": "tool",
                        "name": "tool",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    service.discover_components(root)
    service.accept_unambiguous_components(root)
    (root / "conf").mkdir()
    (root / "conf" / "local.config").write_text(
        "process { executor = 'local' }\nsingularity.enabled = true\n",
        encoding="utf-8",
    )
    (root / "nextflow.config").write_text(
        "profiles { local { includeConfig 'conf/local.config' } }\n",
        encoding="utf-8",
    )
    return service


def test_cli_and_tui_save_byte_identical_execution_and_provenance_state(
    tmp_path: Path,
) -> None:
    cli_root = tmp_path / "cli"
    tui_root = tmp_path / "tui"
    cli_root.mkdir()
    tui_root.mkdir()
    _milestone_d_repository(cli_root)
    tui_service = _milestone_d_repository(tui_root)
    profile_decisions = cli_root / "profiles.json"
    profile_decisions.write_text(
        json.dumps(
            [
                {
                    "profile": "profile:local",
                    "use": "development",
                    "description": "Supported local execution.",
                }
            ]
        ),
        encoding="utf-8",
    )
    provenance_decision = cli_root / "provenance.json"
    provenance_decision.write_text(
        json.dumps(
            {
                "strategy": "minimal_internal",
                "authors": ["Ada Example"],
                "licenses": ["MIT"],
                "published_at": "2026-08-07",
                "source_revision": "abcdef",
            }
        ),
        encoding="utf-8",
    )
    assert (
        runner.invoke(
            cli_app,
            [
                "configure",
                "execution-profiles",
                "--repository",
                str(cli_root),
                "--decision-file",
                str(profile_decisions),
            ],
        ).exit_code
        == 0
    )
    assert (
        runner.invoke(
            cli_app,
            [
                "configure",
                "provenance",
                "--repository",
                str(cli_root),
                "--decision-file",
                str(provenance_decision),
            ],
        ).exit_code
        == 0
    )

    tui_service.discover_execution_profiles(tui_root)
    tui_service.discover_provenance(tui_root)
    tui_app = NfSpliceApp(tui_service.inspect(tui_root), tui_root, tui_service)

    async def exercise() -> None:
        async with tui_app.run_test() as pilot:
            tui_app.query_one("#profile-use", Select).value = "development"
            tui_app.query_one(
                "#profile-description", Input
            ).value = "Supported local execution."
            tui_app.query_one("#select-profile", Button).press()
            await pilot.pause()
            tui_app.query_one("#provenance-authors", Input).value = "Ada Example"
            tui_app.query_one("#provenance-licenses", Input).value = "MIT"
            tui_app.query_one("#provenance-published", Input).value = "2026-08-07"
            tui_app.query_one("#provenance-revision", Input).value = "abcdef"
            tui_app.query_one("#select-provenance", Button).press()
            await pilot.pause()

    asyncio.run(exercise())

    assert (cli_root / "splice" / "nf-splice.yaml").read_bytes() == (
        tui_root / "splice" / "nf-splice.yaml"
    ).read_bytes()
