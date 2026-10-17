"""Regression tests of the 0.3.0 corrective consistency pass (ADR-0061 to ADR-0064).

They exercise real services, files and commands. Scripted providers prove
orchestration, permissions and evidence records only, never a real model's
scientific reasoning.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from layer_fixtures import edit_draft_file
from multi_route import author_all, build, copy_fixture
from nf_splice.cli import app
from nf_splice.layers.base import read_layer
from nf_splice.services.readiness import (
    INGESTION_READY,
    NOT_PUBLISHED,
    PUBLISHED_NOT_READY,
    assess_readiness,
    lifecycle,
)

runner = CliRunner()


def _unbind_input(data: dict[str, Any]) -> None:
    """Make ``input`` required with no default and nobody allowed to set it."""
    for group in data.get("$defs", {}).values():
        if "input" in group.get("properties", {}):
            group.setdefault("required", [])
            if "input" not in group["required"]:
                group["required"].append("input")
            group["properties"]["input"].pop("default", None)
            group["properties"]["input"]["x-splice-access"] = {"editable_by": []}


def _input_policy(root: Path) -> Any:
    state = read_layer(root, "inputs")
    assert state.draft is not None
    for group in state.draft.data.get("$defs", {}).values():
        if "input" in group.get("properties", {}):
            return group["properties"]["input"]["x-splice-access"]
    raise AssertionError("no input parameter")


# ------------------------------------------------------------ lifecycle


def test_lifecycle_before_publication_is_not_published(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path)
    author_all(root)
    state = lifecycle(root)
    assert state.state == NOT_PUBLISHED and state.drafts_valid
    assert not state.ingestion_ready
    assert any("nothing is published" in item for item in state.reasons())


def test_a_build_publishes_but_never_claims_ingestion_readiness(
    tmp_path: Path,
) -> None:
    root = copy_fixture(tmp_path)
    author_all(root)
    edit_draft_file(root, "inputs", _unbind_input)
    built = runner.invoke(app, ["build", "all", "--repository", str(root)])
    assert built.exit_code == 0, built.output
    assert "Published, but not ready for SPLICE ingestion." in built.output
    assert "runtime parameters: input" in built.output
    # Readiness never makes a parameter editable to satisfy itself.
    assert _input_policy(root) == {"editable_by": []}

    status = runner.invoke(app, ["status", "--repository", str(root), "--json"])
    document = json.loads(status.output)
    assert document["lifecycle"]["state"] == PUBLISHED_NOT_READY
    assert document["lifecycle"]["published"] is True
    assert document["lifecycle"]["ingestion_ready"] is False

    validated = runner.invoke(app, ["validate", "--repository", str(root), "--json"])
    assert validated.exit_code == 2
    report = json.loads(validated.output)
    assert report["published"] and not report["ingestion_ready"]
    assert report["lifecycle"] == PUBLISHED_NOT_READY
    assert any(item.startswith("runtime parameters:") for item in report["reasons"])

    exported = runner.invoke(app, ["export", "--repository", str(root)])
    assert exported.exit_code == 0, exported.output
    assert "not that the bundle is ready for SPLICE ingestion" in exported.output
    assert "Published, but not ready for SPLICE ingestion." in exported.output

    drafts = runner.invoke(app, ["draft", "validate", "--repository", str(root)])
    assert "Draft checks only" in drafts.output


def test_a_complete_integration_is_reported_ready_everywhere(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path)
    author_all(root)
    build(root)
    state = lifecycle(root)
    assert state.state == INGESTION_READY, state.reasons()
    status = runner.invoke(app, ["status", "--repository", str(root)])
    assert "Published and ready for SPLICE ingestion." in status.output
    validated = runner.invoke(app, ["validate", "--repository", str(root)])
    assert validated.exit_code == 0, validated.output


def test_a_null_default_does_not_supply_a_required_input(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path)
    author_all(root)

    def null_default(data: dict[str, Any]) -> None:
        _unbind_input(data)
        for group in data.get("$defs", {}).values():
            if "input" in group.get("properties", {}):
                group["properties"]["input"]["default"] = None

    edit_draft_file(root, "inputs", null_default)
    build(root)
    runtime = assess_readiness(root).dimensions["runtime_parameters"]
    assert runtime.status == "blocked" and "input" in runtime.blockers[0]


def test_drafts_changed_after_publishing_are_reported(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path)
    author_all(root)
    build(root)

    def break_identity(data: dict[str, Any]) -> None:
        data["pipeline"]["version"] = "not a version"

    edit_draft_file(root, "bundle", break_identity)
    state = lifecycle(root)
    assert state.published and state.drafts_valid is False
    assert "no longer validate" in state.headline


def test_not_assessed_dimensions_are_not_ready(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path)
    author_all(root)
    build(root)
    (root / "splice" / "components.json").unlink()
    readiness = assess_readiness(root)
    assert readiness.dimensions["deployment"].status == "not_assessed"
    assert not readiness.ingestion_ready


# ------------------------------------------------------------ reviews


def _review_toolbox(root: Path, stage: str, layer: str) -> Any:
    from nf_splice.agents.operations import READ_OPERATIONS
    from nf_splice.agents.permissions import ExecutionPolicy
    from nf_splice.agents.state import Usage
    from nf_splice.agents.toolbox import SessionToolbox, ToolMode
    from nf_splice.domain import Actor, ChangeOrigin
    from nf_splice.layers import ChangeContext

    return SessionToolbox(
        root=root,
        policy=ExecutionPolicy(),
        mode=ToolMode.EXECUTE,
        operations=set(READ_OPERATIONS) | {"replace_draft"},
        controls={"review_scope", "complete_review", "submit_stage_proposal"},
        change=ChangeContext(
            actor=Actor(label="agent"), origin=ChangeOrigin.AGENT_AUTONOMOUS
        ),
        usage=Usage(),
        stage_layer=layer,
        stage=stage,
    )


def test_review_scope_is_derived_from_this_pipeline(tmp_path: Path) -> None:
    from nf_splice.agents.review_scope import review_scope

    root = copy_fixture(tmp_path)
    author_all(root)
    outputs = {item.id: item for item in review_scope(root, "outputs")}
    assert "main.nf" in outputs["workflow_sources"].targets
    assert outputs["workflow_sources"].every
    rules = outputs["publication_rules"]
    assert rules.required and rules.every
    assert all("publishDir" in (root / item).read_text() for item in rules.targets)
    assert "example_outputs" not in outputs  # none supplied
    with_examples = {item.id for item in review_scope(root, "outputs", examples=True)}
    assert "example_outputs" in with_examples
    profiles = {item.id: item for item in review_scope(root, "profiles")}
    assert profiles["profile_configs"].targets  # every profile's own config
    provenance = {item.id for item in review_scope(root, "provenance")}
    assert {"crate_analysis", "reviewed_identity"} <= provenance


def test_a_review_with_required_evidence_uninspected_is_refused(
    tmp_path: Path,
) -> None:
    from layer_fixtures import review_arguments

    root = copy_fixture(tmp_path)
    author_all(root)
    tools = _review_toolbox(root, "outputs", "outputs")
    tools.call("read_source", {"path": "main.nf"})
    tools.call("analyse_routes", {})
    refused = tools.call("complete_review", review_arguments("outputs"))
    assert refused["denied"]
    assert "required evidence for this stage is not inspected" in str(refused)
    assert "publishDir" in str(refused)
    scope = tools.call("review_scope", {})
    assert not scope["data"]["complete"]
    for call in scope["suggested_calls"]:
        tools.call(call["tool"], call["arguments"])
    assert tools.call("review_scope", {})["data"]["complete"]
    assert tools.call("complete_review", review_arguments("outputs"))["success"]


def test_a_review_citing_an_unread_file_or_confirming_nothing_is_refused(
    tmp_path: Path,
) -> None:
    from layer_fixtures import follow_scope, review_arguments

    root = copy_fixture(tmp_path)
    author_all(root)
    tools = _review_toolbox(root, "outputs", "outputs")
    follow_scope(tools)
    cited = tools.call(
        "complete_review",
        review_arguments("outputs", evidence=["modules/local/never_read/main.nf:3"]),
    )
    assert cited["denied"] and "never_read" in str(cited)
    free_text = tools.call(
        "complete_review", review_arguments("outputs", evidence=["I looked."])
    )
    assert free_text["denied"] and "cite the evidence" in str(free_text)
    accepted = review_arguments("outputs")
    accepted["draft_assessment"]["confirmed"] = []
    unchanged = tools.call("complete_review", accepted)
    assert unchanged["denied"] and "draft is unchanged" in str(unchanged)


def test_a_proposal_needs_the_same_evidence(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path)
    author_all(root)
    tools = _review_toolbox(root, "outputs", "outputs")
    tools.call("read_source", {"path": "main.nf"})
    refused = tools.call(
        "submit_stage_proposal", {"summary": "x", "evidence": ["main.nf"]}
    )
    assert refused["denied"] and "required evidence" in str(refused)


def test_completed_reviews_record_evidence_coverage_and_basis(
    tmp_path: Path,
) -> None:
    import asyncio

    from agent_scripts import RouteAgent
    from layer_fixtures import ADA
    from nf_splice.agents import ExecutionPolicy, InteractionMode, SessionEngine
    from nf_splice.agents.providers.scripted import ScriptedProvider
    from nf_splice.agents.stages import Stage

    root = copy_fixture(tmp_path)
    engine = SessionEngine.create(
        root,
        mode=InteractionMode.AUTONOMOUS,
        provider=ScriptedProvider(RouteAgent()),
        objective="integrate",
        policy=ExecutionPolicy(),
        actor=ADA.actor,
    )
    asyncio.run(engine.advance())
    for stage in (Stage.IDENTITY, Stage.OUTPUTS, Stage.COMPONENTS):
        review = engine.state.stages[stage].review
        assert review is not None, stage
        assert review.basis in {"revised", "verified_unchanged"}
        assert review.evidence and review.coverage
        required = [item for item in review.coverage if item["required"]]
        assert required and all(item["status"] == "covered" for item in required)
        assert set(review.draft_assessment) == {
            "omissions",
            "incorrect_assumptions",
            "unsupported_declarations",
            "confirmed",
        }
    report = engine.report()
    assert report["provider_verification"].startswith("offline scripted provider")


# ------------------------------------------------------------ RO-Crate

_FAKE_NF_CORE = """#!/usr/bin/env python3
import json, sys
if sys.argv[1:] == ["--version"]:
    print("nf-core, version 3.5.1")
    raise SystemExit(0)
target = sys.argv[sys.argv.index("--json_path") + 1]
json.dump({
    "@context": "https://w3id.org/ro/crate/1.1/context",
    "@graph": [
        {"@id": "ro-crate-metadata.json", "@type": "CreativeWork",
         "about": {"@id": "./"},
         "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"}},
        {"@id": "./", "@type": "Dataset", "name": "generated",
         "url": "https://nf-co.re/multiroute",
         "mainEntity": {"@id": "main.nf"}},
        {"@id": "main.nf",
         "@type": ["File", "SoftwareSourceCode", "ComputationalWorkflow"],
         "name": "generated"},
    ],
}, open(target, "w"))
"""

_FAKE_VALIDATOR = """#!/usr/bin/env python3
import json, sys
if "--version" in sys.argv:
    print("rocrate-validator 0.12.2")
    raise SystemExit(0)
report = sys.argv[sys.argv.index("-o") + 1]
crate = sys.argv[-1]
import os
ok = os.path.isfile(os.path.join(crate, "ro-crate-metadata.json"))
json.dump({"passed": ok, "issues": []}, open(report, "w"))
"""


def _executable(directory: Path, name: str, text: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)
    return path


def _crate_tools(root: Path, *grants: str) -> Any:
    from nf_splice.agents.operations import READ_OPERATIONS
    from nf_splice.agents.permissions import ExecutionPolicy, validate_grants
    from nf_splice.agents.state import Usage
    from nf_splice.agents.toolbox import SessionToolbox, ToolMode
    from nf_splice.domain import Actor, ChangeOrigin
    from nf_splice.layers import ChangeContext

    return SessionToolbox(
        root=root,
        policy=ExecutionPolicy(grants=validate_grants(list(grants))),
        mode=ToolMode.EXECUTE,
        operations=set(READ_OPERATIONS)
        | {"generate_ro_crate", "provenance_strategy", "replace_draft"},
        controls=set(),
        change=ChangeContext(
            actor=Actor(label="agent"), origin=ChangeOrigin.AGENT_AUTONOMOUS
        ),
        usage=Usage(),
        stage_layer="provenance",
        stage="provenance",
    )


def test_the_agent_assesses_the_crate_and_chooses_how_to_start(
    tmp_path: Path,
) -> None:
    from layer_fixtures import write_root_crate
    from nf_splice.services.crate_review import assess_crate

    root = copy_fixture(tmp_path)
    author_all(root)
    tools = _crate_tools(root)
    kept = tools.call("analyse_ro_crate", {})["data"]
    assert kept["recommendation"]["action"] == "keep"
    assert kept["draft"]["present"] and not kept["root_crate"]["present"]

    write_root_crate(root, "multiroute", "0.9.0")  # an older release's crate
    edit_draft_file(root, "provenance", lambda data: data.update(crate=None))
    stale = assess_crate(root)
    assert stale["recommendation"]["action"] == "correct", stale
    corrected = tools.call("provenance_strategy", {"strategy": "correct"})
    assert corrected["success"], corrected
    assert assess_crate(root)["recommendation"]["action"] == "keep"


def test_the_nf_core_generator_is_permission_controlled_and_isolated(
    tmp_path: Path, monkeypatch: Any
) -> None:
    import hashlib

    root = copy_fixture(tmp_path / "repo")
    author_all(root)
    sources = {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).digest()
        for path in root.rglob("*")
        if path.is_file() and ".splice-local" not in path.parts
    }
    denied = _crate_tools(root).call("generate_ro_crate", {})
    assert denied["denied"] and "external_tools" in str(denied)
    no_network = _crate_tools(root, "external_tools").call("generate_ro_crate", {})
    assert no_network["denied"] and "network" in str(no_network)

    monkeypatch.setenv("PATH", "/nonexistent")
    missing = _crate_tools(root, "external_tools", "network").call(
        "generate_ro_crate", {}
    )
    assert not missing["success"] and "not installed" in str(missing)
    assert "never installs" in str(missing)

    tools_dir = tmp_path / "bin"
    _executable(tools_dir, "nf-core", _FAKE_NF_CORE)
    monkeypatch.setenv("PATH", f"{tools_dir}:/usr/bin:/bin")
    generated = _crate_tools(root, "external_tools", "network").call(
        "generate_ro_crate", {}
    )
    assert generated["success"], generated
    assert generated["generator"]["version"] == "3.5.1"
    state = read_layer(root, "provenance")
    assert state.draft is not None and state.draft.data["origin"] == "nf-core"
    root_entity = next(
        item for item in state.draft.data["crate"]["@graph"] if item["@id"] == "./"
    )
    assert root_entity["name"] == "multiroute"  # reconciled with the identity
    assert "nf-co.re" not in json.dumps(state.draft.data["crate"])
    after = {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).digest()
        for path in root.rglob("*")
        if path.is_file() and ".splice-local" not in path.parts
    }
    assert after == sources  # the pipeline itself is untouched


def test_structural_and_standards_checks_are_reported_apart(
    tmp_path: Path, monkeypatch: Any
) -> None:
    root = copy_fixture(tmp_path / "repo")
    author_all(root)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.delenv("NF_SPLICE_ROCRATE_VALIDATOR", raising=False)
    result = _crate_tools(root).call("validate_ro_crate", {})["data"]
    assert result["structural"]["status"] == "passed"
    assert result["standards"]["status"] == "not_run"
    assert "Only the structural checks are established" in result["statement"]

    validator = _executable(tmp_path / "bin", "rocrate-validator", _FAKE_VALIDATOR)
    monkeypatch.setenv("NF_SPLICE_ROCRATE_VALIDATOR", str(validator))
    unpermitted = _crate_tools(root).call("validate_ro_crate", {})["data"]
    assert unpermitted["standards"]["status"] == "not_run"
    assert "not permitted" in unpermitted["standards"]["reason"]
    permitted = _crate_tools(root, "external_tools").call("validate_ro_crate", {})
    assert permitted["data"]["standards"]["status"] == "passed"
    assert "--offline" in permitted["data"]["standards"]["command"]

    cli = runner.invoke(
        app, ["draft", "check-crate", "--repository", str(root), "--json"]
    )
    document = json.loads(cli.output)
    assert document["checks"]["standards"]["status"] == "not_run"
    assert document["assessment"]["recommendation"]["action"] == "keep"
