"""CLI surface, package metadata and stable machine-readable results."""

from __future__ import annotations

import json
from importlib.metadata import metadata, version
from pathlib import Path

from typer.testing import CliRunner

from layer_fixtures import ready_repository
from nf_splice import __version__
from nf_splice.cli import app

runner = CliRunner()


def test_package_version_matches_installed_metadata() -> None:
    assert __version__ == version("nf-splice") == "0.3.0"


def test_supported_python_range_is_published() -> None:
    requires_python = metadata("nf-splice")["Requires-Python"]
    assert requires_python is not None
    assert ">=3.10" in requires_python and "<3.15" in requires_python


def test_version_option() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.output.strip() == f"nf-splice {__version__}"


def test_help_lists_every_command_group() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in (
        "inspect",
        "status",
        "init",
        "configure",
        "draft",
        "plan",
        "build",
        "validate",
        "preview",
        "containers",
        "schema",
        "audit",
        "analysis-output",
        "tui",
    ):
        assert command in result.output
    listing = result.output.split("Commands", 1)[-1]
    assert "migrate-state" not in listing  # 0.1.0 state relocation is gone
    assert "migrate" in listing and "workspace" in listing
    for group, commands in (
        (
            "draft",
            (
                "list",
                "inspect",
                "validate",
                "diff",
                "confirm",
                "edit",
                "promote",
                "recover",
                "sync-identity",
            ),
        ),
        ("containers", ("classify", "cache-name", "verify")),
        ("analysis-output", ("generate", "validate")),
    ):
        help_output = runner.invoke(app, [group, "--help"]).output
        for command in commands:
            assert command in help_output, (group, command)


def test_inspect_and_status_are_read_only(tmp_path: Path) -> None:
    (tmp_path / "main.nf").write_text("workflow {}\n", encoding="utf-8")
    inspected = runner.invoke(app, ["inspect", "--repository", str(tmp_path)])
    status = runner.invoke(app, ["status", "--repository", str(tmp_path), "--json"])
    assert inspected.exit_code == 0
    assert "SPLICE tree: absent" in inspected.output
    assert "nextflow_source: 1" in inspected.output
    payload = json.loads(status.output)
    assert {item["state"] for item in payload["artifacts"]} == {"missing"}
    assert payload["ready"] is False
    assert not (tmp_path / "splice").exists()


def test_unknown_layer_fails_truthfully(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["configure", "profiles", "--repository", str(tmp_path)]
    )
    assert result.exit_code == 2
    assert "unknown authoring layer" in result.output


def test_draft_commands_report_stable_json(tmp_path: Path) -> None:
    ready_repository(tmp_path)
    listed = runner.invoke(
        app, ["draft", "list", "--repository", str(tmp_path), "--json"]
    )
    assert {item["state"] for item in json.loads(listed.output)} == {"ready"}
    validated = runner.invoke(
        app, ["draft", "validate", "--repository", str(tmp_path), "--json"]
    )
    assert validated.exit_code == 0 and json.loads(validated.output)["valid"] is True
    inspected = runner.invoke(
        app, ["draft", "inspect", "outputs", "--repository", str(tmp_path), "--json"]
    )
    assert json.loads(inspected.output)["finals"] == [
        "outputs.yaml",
        "outputs.schema.json",
    ]
    diff = runner.invoke(
        app, ["draft", "diff", "--repository", str(tmp_path), "--json"]
    )
    plan = json.loads(diff.output)
    assert plan["ready"] and {item["kind"] for item in plan["changes"]} == {"create"}
    check = runner.invoke(
        app, ["build", "all", "--check", "--json", "--repository", str(tmp_path)]
    )
    assert check.exit_code == 0
    envelope = json.loads(check.output)
    assert set(envelope) >= {"target", "ready", "blockers", "changes", "wrote", "check"}
    assert not (tmp_path / "splice" / "bundle.json").exists()
    built = runner.invoke(
        app, ["build", "all", "--json", "--repository", str(tmp_path)]
    )
    assert built.exit_code == 0 and "bundle.json" in json.loads(built.output)["wrote"]
    validated = runner.invoke(
        app, ["validate", "--json", "--repository", str(tmp_path)]
    )
    assert validated.exit_code == 0 and json.loads(validated.output)["valid"]
    preview = runner.invoke(app, ["preview", "outputs", "--repository", str(tmp_path)])
    assert json.loads(preview.output)["x-output-catalog"]["catalog_version"] == "0.3.0"


def test_draft_edit_plans_then_applies_and_reports_conflicts(tmp_path: Path) -> None:
    ready_repository(tmp_path)
    patch = tmp_path / "patch.json"
    patch.write_text(
        json.dumps(
            [
                {
                    "op": "replace",
                    "path": "/pipeline/description",
                    "value": "Edited by patch.",
                    "expected": "Quantifies RNA-seq reads.",
                }
            ]
        ),
        encoding="utf-8",
    )
    draft = tmp_path / ".splice-local" / "drafts" / "bundle.draft.yaml"
    before = draft.read_bytes()
    planned = runner.invoke(
        app,
        [
            "draft",
            "edit",
            "bundle",
            "--patch",
            str(patch),
            "--repository",
            str(tmp_path),
        ],
    )
    assert planned.exit_code == 0 and "Preview only" in planned.output
    assert draft.read_bytes() == before
    applied = runner.invoke(
        app,
        [
            "--actor",
            "Ada",
            "draft",
            "edit",
            "bundle",
            "--patch",
            str(patch),
            "--apply",
            "--repository",
            str(tmp_path),
        ],
    )
    assert applied.exit_code == 0 and "Edited by patch." in draft.read_text()
    stale = json.loads(patch.read_text())
    stale[0]["value"] = "Other"
    patch.write_text(json.dumps(stale), encoding="utf-8")
    draft.write_text(draft.read_text().replace("Edited by patch.", "Hand edit."))
    conflict = runner.invoke(
        app,
        [
            "draft",
            "edit",
            "bundle",
            "--patch",
            str(patch),
            "--apply",
            "--repository",
            str(tmp_path),
        ],
    )
    assert conflict.exit_code == 2 and "conflict" in conflict.output
    assert "Hand edit." in draft.read_text()


def test_containers_commands() -> None:
    classify = runner.invoke(app, ["containers", "classify", "quay.io/a/b:1"])
    assert classify.output.strip() == "oci_registry"
    cache = runner.invoke(
        app, ["containers", "cache-name", "biocontainers/x:1", "--registry", "quay.io"]
    )
    assert cache.output.strip() == "quay.io-biocontainers-x-1.img"
