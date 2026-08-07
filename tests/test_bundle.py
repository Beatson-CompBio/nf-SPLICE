"""Acceptance tests for complete bundle orchestration and validation."""

from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
from pathlib import Path

import pytest
from textual.widgets import Button, Static
from typer.testing import CliRunner

from nf_splice.cli import app
from nf_splice.domain import (
    AuthoringDocument,
    Decision,
    DecisionStatus,
    LayerState,
    OutputCategory,
    OutputContractSettings,
    OutputEntityType,
    OutputFormat,
    OutputScope,
    PipelineIdentity,
    ReviewedComponent,
    ReviewedExecutionProfile,
    ReviewedInput,
    ReviewedOutput,
    ReviewedProvenance,
    dump_authoring_document,
)
from nf_splice.domain.execution import (
    ContainerEngine,
    ExecutionEngine,
    ExecutionExecutor,
    ExecutionProfileType,
)
from nf_splice.domain.inputs import InputClassification
from nf_splice.interfaces.tui import NfSpliceApp
from nf_splice.services import (
    ApplicationService,
    IntegrationBuildError,
    StaticChangeKind,
    build_integration,
    plan_integration,
    validate_integration,
)

runner = CliRunner()


def _git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ("git", "-C", str(root), *arguments),
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def complete_repository(root: Path) -> bytes:
    """Write compact, fully reviewed canonical and developer-owned sources."""
    reviewed = (
        (
            "input:threshold",
            ReviewedInput(
                name="threshold",
                group="analysis",
                group_title="Analysis",
                classification=InputClassification.USER_CONFIGURABLE,
                schema_fragment={
                    "type": "number",
                    "description": "Reviewed threshold.",
                },
            ),
            "inputs",
        ),
        (
            "component:tool",
            ReviewedComponent(
                id="component:tool",
                name="tool",
                path="modules/local/tool",
                namespace="local",
                tool_name="tool",
                version="1.0",
                container_uri="quay.io/example/tool:1.0",
                evidence_locations=("modules/local/tool/main.nf",),
            ),
            "components",
        ),
        (
            "output:report",
            ReviewedOutput(
                key="report",
                title="Report",
                description="Run report.",
                category=OutputCategory.RUN_REPORT,
                formats=(OutputFormat.HTML,),
                scopes=(OutputScope.RUN,),
                entity_types=(OutputEntityType.FILE,),
                path_patterns=(r"^reports/report\.html$",),
            ),
            "outputs",
        ),
        (
            "profile:local",
            ReviewedExecutionProfile(
                id="profile-local-6c6f63616c",
                name="Local",
                description="Local execution.",
                type=ExecutionProfileType.DEVELOPMENT,
                engine=ExecutionEngine.NEXTFLOW,
                executor=ExecutionExecutor.LOCAL,
                container_engine=ContainerEngine.SINGULARITY,
                source_profile="local",
                config_source="conf/local.config",
                config_path="configs/profile-local-6c6f63616c.config",
                evidence_locations=("nextflow.config", "conf/local.config"),
            ),
            "execution_profiles",
        ),
        (
            "provenance:root-ro-crate",
            ReviewedProvenance(
                source_path="ro-crate-metadata.json",
                evidence_locations=("ro-crate-metadata.json",),
            ),
            "provenance",
        ),
    )
    decisions = tuple(
        Decision(
            id=identifier,
            status=DecisionStatus.REVIEWED,
            value=value.model_dump(mode="json"),
        )
        for identifier, value, _layer in reviewed
    )
    layers = tuple(
        LayerState(
            name=layer,
            configured=True,
            decision_ids=tuple(
                identifier
                for identifier, _value, item_layer in reviewed
                if item_layer == layer
            ),
        )
        for layer in (
            "inputs",
            "outputs",
            "components",
            "execution_profiles",
            "provenance",
        )
    )
    document = AuthoringDocument(
        pipeline=PipelineIdentity(
            name="Example Pipeline",
            version="1.2.3",
            repository_url="https://github.com/org/example",
            release_url="https://github.com/org/example/releases/tag/1.2.3",
        ),
        output_contract=OutputContractSettings(schema_version="1.0.0"),
        decisions=decisions,
        layers=layers,
    )
    splice = root / "splice"
    splice.mkdir()
    (splice / "nf-splice.yaml").write_text(
        dump_authoring_document(document), encoding="utf-8"
    )
    config = b"process { executor = 'local' }\r\nsingularity.enabled = true\r\n"
    (root / "conf").mkdir()
    (root / "conf" / "local.config").write_bytes(config)
    crate = {
        "@context": "https://w3id.org/ro/crate/1.1/context",
        "@graph": [
            {
                "@id": "ro-crate-metadata.json",
                "@type": "CreativeWork",
                "about": {"@id": "./"},
            },
            {"@id": "./", "@type": "Dataset"},
        ],
    }
    (root / "ro-crate-metadata.json").write_text(
        json.dumps(crate, indent=2) + "\n", encoding="utf-8"
    )
    return config


def test_complete_plan_build_validate_and_second_build_are_deterministic(
    tmp_path: Path,
) -> None:
    config = complete_repository(tmp_path)
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.name", "nf-splice test")
    _git(tmp_path, "config", "user.email", "nf-splice@example.invalid")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "reference source")
    revision = _git(tmp_path, "rev-parse", "HEAD")
    before_source = (tmp_path / "ro-crate-metadata.json").read_bytes()

    plan = plan_integration(tmp_path)
    checked = build_integration(tmp_path, check=True)

    assert plan.ready
    assert len(plan.changes) == 10
    assert {item.kind for item in plan.changes} == {StaticChangeKind.CREATE}
    assert checked.wrote is False
    assert not (tmp_path / "splice" / "bundle.json").exists()

    built = build_integration(tmp_path)
    report = validate_integration(tmp_path)
    repeated = plan_integration(tmp_path)
    bundle = json.loads((tmp_path / "splice" / "bundle.json").read_text())
    lock = json.loads((tmp_path / "splice" / "nf-splice.lock.json").read_text())

    assert built.wrote
    assert report.valid
    assert report.checked_files == 10
    assert {item.kind for item in repeated.changes} == {StaticChangeKind.UNCHANGED}
    assert "nf-splice.lock.json" not in lock["managed_files"]
    assert len(lock["managed_files"]) == 9
    assert bundle["files"] == {
        "inputs_schema": "inputs.schema.json",
        "outputs_catalogue": "outputs.yaml",
        "outputs_schema": "outputs.schema.json",
        "ro_crate": "ro-crate-metadata.json",
        "components": "components.json",
        "execution_profiles": "execution-profiles.json",
    }
    assert lock["generator"]["name"] == "nf-splice"
    assert lock["generator"]["version"]
    assert lock["repository"] == {
        "url": "https://github.com/org/example",
        "revision": revision,
    }
    for relative, record in lock["sources"].items():
        source = (
            tmp_path / relative
            if relative != "splice/nf-splice.yaml"
            else tmp_path / "splice" / "nf-splice.yaml"
        )
        assert record["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    for relative, record in lock["managed_files"].items():
        generated = tmp_path / "splice" / relative
        assert record["sha256"] == hashlib.sha256(generated.read_bytes()).hexdigest()
    assert (tmp_path / "ro-crate-metadata.json").read_bytes() == before_source
    assert (
        tmp_path / "splice" / "configs" / "profile-local-6c6f63616c.config"
    ).read_bytes() == config


def test_complete_build_preflights_collisions_and_preserves_unknown_content(
    tmp_path: Path,
) -> None:
    complete_repository(tmp_path)
    unknown = tmp_path / "splice" / "developer-notes.txt"
    unknown.write_text("preserve\n", encoding="utf-8")
    target = tmp_path / "splice" / "components.json"
    target.write_text(
        '{"schema_version":"old","pipeline":{},"containers":[],"components":[]}\n'
    )

    with pytest.raises(IntegrationBuildError, match="replace-existing"):
        build_integration(tmp_path)

    assert not (tmp_path / "splice" / "bundle.json").exists()
    assert unknown.read_text(encoding="utf-8") == "preserve\n"
    assert build_integration(tmp_path, replace_existing=True).wrote
    assert unknown.read_text(encoding="utf-8") == "preserve\n"


def test_bundle_only_requires_current_layer_materialisations(tmp_path: Path) -> None:
    complete_repository(tmp_path)

    with pytest.raises(IntegrationBuildError, match="build all"):
        build_integration(tmp_path, target="bundle")

    build_integration(tmp_path)
    assert not build_integration(tmp_path, target="bundle").wrote


def test_cli_plan_build_and_validate_have_stable_json_results(tmp_path: Path) -> None:
    complete_repository(tmp_path)

    planned = runner.invoke(app, ["plan", "all", "-r", str(tmp_path), "--json"])
    checked = runner.invoke(
        app,
        ["build", "all", "-r", str(tmp_path), "--check", "--json"],
    )
    built = runner.invoke(
        app, ["build", "all", "-r", str(tmp_path), "--non-interactive"]
    )
    validated = runner.invoke(app, ["validate", "-r", str(tmp_path), "--json"])

    assert planned.exit_code == 0
    assert json.loads(planned.output)["ready"] is True
    assert checked.exit_code == 0
    assert json.loads(checked.output)["wrote"] is False
    assert built.exit_code == 0
    assert validated.exit_code == 0
    assert json.loads(validated.output) == {
        "valid": True,
        "checked_files": 10,
        "issues": [],
    }


def test_individual_layer_check_has_the_same_stable_json_envelope(
    tmp_path: Path,
) -> None:
    complete_repository(tmp_path)

    checked = runner.invoke(
        app,
        ["build", "inputs", "-r", str(tmp_path), "--check", "--json"],
    )

    assert checked.exit_code == 0
    assert json.loads(checked.output) == {
        "target": "inputs",
        "changes": [
            {
                "path": "inputs.schema.json",
                "kind": "create",
                "diff": json.loads(checked.output)["changes"][0]["diff"],
            }
        ],
        "wrote": False,
        "check": True,
        "non_interactive": False,
    }


def test_tui_and_cli_build_the_same_complete_bundle(tmp_path: Path) -> None:
    cli_root = tmp_path / "cli"
    tui_root = tmp_path / "tui"
    cli_root.mkdir()
    tui_root.mkdir()
    complete_repository(cli_root)
    complete_repository(tui_root)

    cli_result = runner.invoke(app, ["build", "all", "-r", str(cli_root)])
    service = ApplicationService()
    tui = NfSpliceApp(service.inspect(tui_root), tui_root, service)

    async def exercise() -> None:
        async with tui.run_test() as pilot:
            tui.query_one("#plan-all", Button).press()
            await pilot.pause()
            assert "create: splice/bundle.json" in str(
                tui.query_one("#integration-summary", Static).content
            )
            tui.query_one("#build-all", Button).press()
            await pilot.pause()
            tui.query_one("#validate-all", Button).press()
            await pilot.pause()
            assert "Valid integration (10 files)." in str(
                tui.query_one("#integration-summary", Static).content
            )

    asyncio.run(exercise())

    assert cli_result.exit_code == 0
    cli_files = {
        path.relative_to(cli_root / "splice").as_posix(): path.read_bytes()
        for path in (cli_root / "splice").rglob("*")
        if path.is_file() and path.name != "nf-splice.yaml"
    }
    tui_files = {
        path.relative_to(tui_root / "splice").as_posix(): path.read_bytes()
        for path in (tui_root / "splice").rglob("*")
        if path.is_file() and path.name != "nf-splice.yaml"
    }
    assert tui_files == cli_files


def test_unconfigured_repository_reports_blockers_without_writes(
    tmp_path: Path,
) -> None:
    (tmp_path / "splice").mkdir()
    (tmp_path / "splice" / "nf-splice.yaml").write_text(
        dump_authoring_document(
            AuthoringDocument(
                pipeline=PipelineIdentity(
                    name="pipeline",
                    version="1.0.0",
                    repository_url="https://github.com/org/pipeline",
                )
            )
        ),
        encoding="utf-8",
    )

    plan = plan_integration(tmp_path)

    assert not plan.ready
    assert "inputs: not configured" in plan.blockers
    assert plan.changes == ()


def test_clean_repository_without_authoring_reports_a_read_only_blocker(
    tmp_path: Path,
) -> None:
    plan = plan_integration(tmp_path)

    assert not plan.ready
    assert "run nf-splice init first" in plan.blockers[0]
    assert not (tmp_path / "splice").exists()


def test_validation_reports_managed_drift_without_repairing_it(tmp_path: Path) -> None:
    complete_repository(tmp_path)
    build_integration(tmp_path)
    target = tmp_path / "splice" / "components.json"
    target.write_text("{}\n", encoding="utf-8")

    report = validate_integration(tmp_path)

    assert not report.valid
    assert any(
        item.path == "splice/components.json" and item.rule == "drift"
        for item in report.issues
    )
    assert target.read_text(encoding="utf-8") == "{}\n"
