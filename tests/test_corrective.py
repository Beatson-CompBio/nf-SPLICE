"""Regression tests of the 0.3.0 corrective consistency pass (ADR-0061 to ADR-0065).

They exercise real services, files and commands. Scripted providers prove
orchestration, permissions and evidence records only, never a real model's
scientific reasoning.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
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


# ------------------------------------------------------------ outputs


def _drop_output(root: Path, predicate: Any) -> None:
    edit_draft_file(
        root,
        "outputs",
        lambda data: data.update(
            outputs=[item for item in data["outputs"] if not predicate(item)]
        ),
    )


def _codes(root: Path) -> dict[str, list[Any]]:
    from nf_splice.services.lifecycle import validate_layer

    found: dict[str, list[Any]] = {}
    for item in validate_layer(root, "outputs").issues:
        found.setdefault(item.code, []).append(item)
    return found


def test_an_established_uncovered_route_blocks_until_resolved(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path)
    author_all(root)
    _drop_output(
        root,
        lambda item: any("multiqc" in pattern for pattern in item["path_patterns"]),
    )
    found = _codes(root)
    established = found["route_not_covered"]
    assert established[0].severity.value == "error"
    assert "MULTIQC always publishes" in established[0].message
    assert "false_positive" in established[0].message

    def exclude(kind: str | None) -> None:
        def mutate(data: dict[str, Any]) -> None:
            entry = {"process": "MULTIQC", "reason": "Static discovery is wrong."}
            if kind is not None:
                entry["kind"] = kind
            data["excluded_routes"] = [entry]

        edit_draft_file(root, "outputs", mutate)

    exclude("not_a_kind")
    assert "invalid_value" in _codes(root)
    exclude("false_positive")
    assert "route_not_covered" not in _codes(root)


def test_alternative_routes_stay_in_the_catalogue_as_classified_warnings(
    tmp_path: Path,
) -> None:
    root = copy_fixture(tmp_path)
    author_all(root)
    _drop_output(root, lambda item: item["key"] == "hisat2_alignment")
    found = _codes(root)
    assert "route_not_covered" not in found
    conditional = found["conditional_route_not_covered"]
    assert conditional[0].severity.value == "warning"
    assert "HISAT2_ALIGN" in conditional[0].message
    assert "union of every route" in conditional[0].message
    # No approval queue: the draft still builds with the warning.
    build(root)
    assert (root / "splice" / "outputs.schema.json").is_file()


def test_unresolvable_routes_are_unverified_warnings_never_blockers(
    tmp_path: Path,
) -> None:
    root = copy_fixture(tmp_path)
    author_all(root)
    module = root / "modules" / "local" / "dynamic"
    module.mkdir(parents=True)
    (module / "main.nf").write_text(
        "process DYNAMIC {\n"
        '    publishDir "${params.outdir}/${task.ext.prefix}"\n'
        "    output:\n"
        "    path out_name\n"
        "    script:\n"
        "    'true'\n"
        "}\n",
        encoding="utf-8",
    )
    main = root / "main.nf"
    text = main.read_text(encoding="utf-8")
    main.write_text(
        "include { DYNAMIC } from './modules/local/dynamic/main'\n"
        + text.replace("workflow {", "workflow {\n    DYNAMIC()", 1),
        encoding="utf-8",
    )
    found = _codes(root)
    unverified = found.get("route_unverified", [])
    assert all(item.severity.value == "warning" for item in unverified)
    assert "route_not_covered" not in found


def test_an_outputs_review_must_address_uncovered_alternative_routes(
    tmp_path: Path,
) -> None:
    from layer_fixtures import follow_scope, review_arguments

    root = copy_fixture(tmp_path)
    author_all(root)
    _drop_output(root, lambda item: item["key"] == "hisat2_alignment")
    tools = _review_toolbox(root, "outputs", "outputs")
    follow_scope(tools)
    silent = tools.call("complete_review", review_arguments("outputs"))
    assert silent["denied"] and "HISAT2_ALIGN" in str(silent)
    explained = tools.call(
        "complete_review",
        review_arguments(
            "outputs",
            uncertainties=[
                "HISAT2_ALIGN is published when params.aligner is hisat2; the "
                "developer must say whether that route is supported"
            ],
        ),
    )
    assert explained["success"], explained


# ------------------------------------------------------------ components

_SIF = (
    b"#!/usr/bin/env run-singularity\n".ljust(32, b"\n") + b"SIF_MAGIC\x00" + b"x" * 500
)
_IMAGE = "https://images.example.net/store/quay.io-biocontainers-star.img"


def _verified_bundle(tmp_path: Path) -> tuple[Path, str]:
    """A published bundle with one verified image distribution."""
    from layer_fixtures import ADA
    from nf_splice.layers.components import verify_distribution
    from test_containers import FakeFetcher, _ok, _public

    root = copy_fixture(tmp_path)
    author_all(root)
    state = read_layer(root, "components")
    assert state.draft is not None
    star = next(
        item["id"]
        for item in state.draft.data["containers"]
        if "star" in json.dumps(item["source_images"])
    )
    verify_distribution(
        root,
        star,
        _IMAGE,
        ADA,
        fetcher=FakeFetcher({_IMAGE: _ok(_SIF)}),
        resolver=_public,
    )
    build(root)
    return root, star


def _reseed(root: Path) -> None:
    import shutil

    from layer_fixtures import ADA
    from nf_splice.services.workspace import initialise

    shutil.rmtree(root / ".splice-local")
    initialise(root, ADA)


def _container(root: Path, identifier: str) -> dict[str, Any]:
    state = read_layer(root, "components")
    assert state.draft is not None
    found: dict[str, Any] = next(
        item for item in state.draft.data["containers"] if item["id"] == identifier
    )
    return found


def test_a_verified_distribution_survives_adoption_of_the_inventory(
    tmp_path: Path,
) -> None:
    from nf_splice.layers.base import load_review_state

    root, star = _verified_bundle(tmp_path)
    published = json.loads((root / "splice" / "components.json").read_text())
    expected = next(item for item in published["containers"] if item["id"] == star)
    _reseed(root)
    kept = _container(root, star)
    assert kept["distribution"] == expected["distribution"]
    record = load_review_state(root, "components").section("verified")[star]
    assert record["adopted_from"] == "splice/components.json"
    assert record["sha256"] == expected["distribution"]["sha256"]
    codes = {item.code for item in _component_issues(root)}
    assert "adopted_distribution" in codes and "unverified_distribution" not in codes


def _component_issues(root: Path) -> list[Any]:
    from nf_splice.services.lifecycle import validate_layer

    return list(validate_layer(root, "components").issues)


def test_no_distribution_is_kept_from_an_unvouched_or_changed_source(
    tmp_path: Path,
) -> None:
    root, star = _verified_bundle(tmp_path / "edited")
    path = root / "splice" / "components.json"
    path.write_text(path.read_text().replace('"sha256"', '"sha256" ', 1))
    _reseed(root)
    assert _container(root, star)["distribution"] is None  # the lock disagrees

    root, star = _verified_bundle(tmp_path / "changed")
    module = root / "modules" / "local" / "star" / "main.nf"
    module.write_text(
        module.read_text().replace("2.7.11b--h43eeafb_0", "2.7.11b--h5ca1c30_6")
    )
    _reseed(root)
    containers = read_layer(root, "components").draft.data["containers"]  # type: ignore[union-attr]
    assert all(
        item["distribution"] is None
        for item in containers
        if "star" in json.dumps(item["source_images"])
    )


def test_a_module_that_declares_a_container_must_be_mapped(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path)
    author_all(root)

    def unmap(data: dict[str, Any]) -> None:
        for item in data["components"]:
            if item["path"].endswith("/star"):
                item.pop("container_id", None)

    edit_draft_file(root, "components", unmap)
    issues = [
        item for item in _component_issues(root) if item.code == "container_not_mapped"
    ]
    assert issues and issues[0].severity.value == "error"
    assert "modules/local/star/main.nf" in issues[0].message


def test_conda_only_components_block_deployment_under_a_container_engine(
    tmp_path: Path,
) -> None:
    root = copy_fixture(tmp_path)
    author_all(root)
    build(root)
    path = root / "splice" / "components.json"
    document = json.loads(path.read_text())
    document["components"][0].pop("container_id", None)
    document["components"][0]["conda_packages"] = ["bioconda::star=2.7.11b"]
    document["components"][1].pop("container_id", None)
    document["components"][1].pop("conda_packages", None)
    path.write_text(json.dumps(document))
    deployment = assess_readiness(root).dimensions["deployment"]
    assert deployment.status == "blocked"
    assert any("declare only Conda packages" in item for item in deployment.blockers)
    assert any("execution host's software" in item for item in deployment.notes)


# ------------------------------------------------------------ wizard


@pytest.mark.asyncio
async def test_the_wizard_states_the_same_lifecycle_as_the_cli(tmp_path: Path) -> None:
    from textual.widgets import Static

    from nf_splice.interfaces.tui import NfSpliceApp
    from tui_helpers import settle

    root = copy_fixture(tmp_path)
    author_all(root)
    edit_draft_file(root, "inputs", _unbind_input)
    build(root)
    status = runner.invoke(app, ["status", "--repository", str(root)])
    assert "Published, but not ready for SPLICE ingestion." in status.output
    wizard = NfSpliceApp(root)
    async with wizard.run_test(size=(160, 60)) as pilot:
        await settle(wizard, pilot)
        wizard.show_step("done")
        await settle(wizard, pilot)
        report = str(wizard.query_one("#done-report", Static).render())
    assert "Published, but not ready for SPLICE ingestion." in report
    assert "runtime parameters: input" in report


# ------------------------------------------------------------ image reuse


def _lock(root: Path) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(
        (root / "splice" / "nf-splice.lock.json").read_text(encoding="utf-8")
    )
    return loaded


def _rewrite_published(root: Path, mutate: Any) -> None:
    """Change components.json and re-vouch for it in the lock, as a tool might."""
    import hashlib

    path = root / "splice" / "components.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    mutate(document)
    payload = (json.dumps(document, indent=2) + "\n").encode("utf-8")
    path.write_bytes(payload)
    lock = _lock(root)
    lock["managed_files"]["components.json"]["sha256"] = hashlib.sha256(
        payload
    ).hexdigest()
    (root / "splice" / "nf-splice.lock.json").write_text(
        json.dumps(lock, indent=2) + "\n", encoding="utf-8"
    )


def test_the_lock_records_each_verification_and_its_basis(tmp_path: Path) -> None:
    root, star = _verified_bundle(tmp_path)
    record = _lock(root)["distributions"][star]
    assert record["verification"] == "fresh"
    assert set(record) == {
        "sha256",
        "download_uri",
        "size_bytes",
        "source_images_sha256",
        "verification",
    }
    # Re-seed only the components, as a fresh clone of the inventory would.
    from layer_fixtures import ADA
    from nf_splice.services.workspace import initialise

    (root / ".splice-local" / "drafts" / "components.draft.yaml").unlink()
    (root / ".splice-local" / "reviews" / "components.review.json").unlink()
    initialise(root, ADA)
    edit_draft_file(
        root, "components", lambda data: data.update(require_downloadable_images=False)
    )
    assert _container(root, star)["distribution"] is not None
    from nf_splice.services.lifecycle import promote

    promote(root, None, ADA, replace_existing=True)
    assert _lock(root)["distributions"][star]["verification"] == "historical"
    deployment = assess_readiness(root).dimensions["deployment"]
    assert any("historical verification" in note for note in deployment.notes)
    assert any("not checked" in note for note in deployment.notes)


def test_reuse_needs_the_lock_record_metadata_and_sources_to_agree(
    tmp_path: Path,
) -> None:
    def reused(root: Path, star: str) -> bool:
        _reseed(root)
        return _container(root, star)["distribution"] is not None

    root, star = _verified_bundle(tmp_path / "no-record")
    lock = _lock(root)
    lock.pop("distributions")  # an earlier lock with no verification record
    (root / "splice" / "nf-splice.lock.json").write_text(json.dumps(lock))
    assert not reused(root, star)

    root, star = _verified_bundle(tmp_path / "metadata")

    def wrong_cache_name(document: dict[str, Any]) -> None:
        for item in document["containers"]:
            if item["id"] == star:
                item["distribution"]["cache_filename"] = "other.img"

    _rewrite_published(root, wrong_cache_name)
    assert not reused(root, star)

    root, star = _verified_bundle(tmp_path / "checksum")

    def other_checksum(document: dict[str, Any]) -> None:
        for item in document["containers"]:
            if item["id"] == star:
                item["distribution"]["sha256"] = "0" * 64

    _rewrite_published(root, other_checksum)
    assert not reused(root, star)

    root, star = _verified_bundle(tmp_path / "agreeing")
    assert reused(root, star)


def test_reverify_checks_availability_now_and_never_changes_a_mismatch(
    tmp_path: Path,
) -> None:
    from nf_splice.layers.base import load_review_state
    from nf_splice.layers.components import reverify_distributions
    from test_containers import FakeFetcher, _ok, _public

    root, star = _verified_bundle(tmp_path)
    _reseed(root)
    assert "adopted_distribution" in {item.code for item in _component_issues(root)}
    before = (root / ".splice-local" / "drafts" / "components.draft.yaml").read_bytes()

    changed = reverify_distributions(
        root,
        [star],
        fetcher=FakeFetcher({_IMAGE: _ok(_SIF + b"tampered")}),
        resolver=_public,
    )
    assert [item.status for item in changed] == ["changed"]
    assert "nothing was changed" in changed[0].detail
    assert "adopted_distribution" in {item.code for item in _component_issues(root)}

    def unreachable(url: str, *, timeout: float) -> Any:
        from nf_splice.services.containers import ContainerServiceError

        raise ContainerServiceError(f"{url} is unreachable")

    failed = reverify_distributions(root, [star], fetcher=unreachable, resolver=_public)
    assert [item.status for item in failed] == ["failed"]

    fresh = reverify_distributions(
        root, [star], fetcher=FakeFetcher({_IMAGE: _ok(_SIF)}), resolver=_public
    )
    assert [item.status for item in fresh] == ["fresh"]
    record = load_review_state(root, "components").section("verified")[star]
    assert record["basis"] == "fresh" and "adopted_from" not in record
    assert "adopted_distribution" not in {item.code for item in _component_issues(root)}
    after = (root / ".splice-local" / "drafts" / "components.draft.yaml").read_bytes()
    assert after == before  # only the verification record changed

    refused = runner.invoke(
        app, ["containers", "reverify", star, "--repository", str(root)]
    )
    assert refused.exit_code == 2 and "--approve-network" in refused.output
