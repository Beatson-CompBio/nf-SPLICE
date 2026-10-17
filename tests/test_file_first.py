"""Acceptance tests of the file-first, high-reasoning authoring model (ADR-0057).

Each test names the acceptance IDs it covers. Scripted providers prove
orchestration, permissions and transactions only, never model reasoning;
tests that need a real pipeline checkout, Nextflow, rocrate-validator or an
S3 store are opt-in and skip with the reason.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import shutil
import zipfile
from pathlib import Path
from typing import Any

import pytest

from layer_fixtures import (
    ADA,
    edit_draft_file,
    review_arguments,
    review_turns,
    scripted_review,
    write_root_crate,
)
from multi_route import FIXTURE, author_all, build, copy_fixture
from nf_splice.agents import ExecutionPolicy, InteractionMode, SessionEngine
from nf_splice.agents.operations import OPERATIONS, OperationContext
from nf_splice.agents.permissions import Permission, PolicyViolation
from nf_splice.agents.protocol import TurnRequest, resolve_effort
from nf_splice.agents.providers.scripted import ScriptedProvider
from nf_splice.agents.stages import Stage, StageStatus
from nf_splice.agents.state import Usage
from nf_splice.agents.toolbox import SessionToolbox, ToolMode
from nf_splice.domain import Actor, ChangeOrigin
from nf_splice.domain.access import Principal
from nf_splice.drafts import DraftConflictError
from nf_splice.inspectors.containers import container_sources, nextflow_cache_filename
from nf_splice.layers import ChangeContext, LayerError
from nf_splice.layers.base import LAYERS, load_review_state, read_layer, replace_draft
from nf_splice.services.export import ExportScope, export_archive
from nf_splice.services.input_policy import authorise_changes
from nf_splice.services.lifecycle import plan_promotion, validate_bundle, validate_layer
from nf_splice.services.readiness import assess_readiness
from nf_splice.services.workspace import initialise

DECISIONS = {
    "accept_output",
    "reject_output",
    "merge_outputs",
    "split_output",
    "accept_component",
    "reject_component",
    "review_profile",
    "reject_profile",
    "confirm",
}


def _sources(root: Path) -> dict[str, str]:
    """Hashes of every pipeline file nf-splice must never change."""
    found = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if path.is_file() and relative.parts[0] not in {".splice-local", ".gitignore"}:
            found[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return found


def _draft(root: Path, layer: str) -> dict[str, Any]:
    state = read_layer(root, layer)
    assert state.draft is not None, state.error
    data: dict[str, Any] = state.draft.data
    return data


# ------------------------------------------------------------ CORE


def test_core_01_02_init_seeds_every_layer_once_and_changes_no_source(
    tmp_path: Path,
) -> None:
    root = copy_fixture(tmp_path)
    before = _sources(root)
    report = initialise(root, ADA)
    assert sorted(report.created) == sorted(item.name for item in LAYERS)
    assert _sources(root) == before  # CORE-01: the pipeline is untouched

    outputs = _draft(root, "outputs")["outputs"]
    assert {item["key"] for item in outputs} >= {"star_align_bam", "hisat2_align_bam"}
    components = _draft(root, "components")
    assert components["components"] and components["containers"]
    profiles = _draft(root, "execution-profiles")
    assert profiles["default_profile"] == "default"
    config = root / ".splice-local/drafts/configs/default.draft.config"
    text = config.read_text(encoding="utf-8")
    assert "// ***** User Pipeline Input Params *****" in text
    assert "// ***** SPLICE Pipeline Input Params *****" in text
    from nf_splice.layers.inputs import iter_parameters

    parameters = list(iter_parameters(_draft(root, "inputs")))
    assert parameters and all(item.editable_by == () for item in parameters)
    assert _draft(root, "provenance")["crate"]["@graph"]

    # CORE-02: a second run changes no authored byte and adds no candidate.
    files = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in (root / ".splice-local" / "drafts").rglob("*")
        if path.is_file()
    }
    candidates = len(load_review_state(root, "outputs").candidates)
    initialise(root, ADA)
    assert files == {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in (root / ".splice-local" / "drafts").rglob("*")
        if path.is_file()
    }
    assert len(load_review_state(root, "outputs").candidates) == candidates


def test_core_03_externally_authored_drafts_build_without_candidate_decisions(
    tmp_path: Path,
) -> None:
    root = copy_fixture(tmp_path)
    author_all(root)
    assert plan_promotion(root).ready
    build(root)
    for layer in ("outputs", "components", "execution-profiles"):
        actions = {event["action"] for event in load_review_state(root, layer).events}
        assert not actions & DECISIONS, (layer, actions)
        statuses = {
            entry.get("status")
            for entry in load_review_state(root, layer).candidates.values()
        }
        assert not statuses & {"accepted", "rejected", "merged", "split"}


def test_core_04_05_errors_are_precise_and_files_are_never_rewritten(
    tmp_path: Path,
) -> None:
    root = copy_fixture(tmp_path)
    author_all(root)
    path = root / ".splice-local/drafts/outputs.draft.yaml"
    good = path.read_bytes()
    path.write_text(good.decode().replace("- sample", "- library", 1), "utf-8")
    broken = path.read_bytes()
    issues = validate_layer(root, "outputs").errors
    assert any(item.pointer.startswith("/outputs/") for item in issues)
    assert path.read_bytes() == broken  # CORE-04: retained as written
    path.write_bytes(good)
    assert validate_layer(root, "outputs").ready

    path.write_text("outputs: [\n", encoding="utf-8")  # CORE-05
    malformed = path.read_bytes()
    result = validate_layer(root, "outputs")
    assert [item.code for item in result.errors] == ["syntax"]
    with pytest.raises(LayerError, match="syntax"):
        replace_draft(
            root,
            "outputs",
            ADA,
            expected_sha256=hashlib.sha256(malformed).hexdigest(),
            section="/outputs",
            data=[],
        )
    assert path.read_bytes() == malformed


def test_core_06_replacement_from_a_stale_read_is_refused(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path)
    initialise(root, ADA)
    state = read_layer(root, "outputs")
    edit_draft_file(root, "outputs", lambda data: data.update(categories={}))
    with pytest.raises(DraftConflictError, match="changed on disk"):
        replace_draft(
            root,
            "outputs",
            ADA,
            expected_sha256=state.file.sha256,
            section="/outputs",
            data=[],
        )
    assert _draft(root, "outputs")["outputs"]  # the person's file survived


def test_core_07_unfinished_autonomous_work_survives_and_is_honest(
    tmp_path: Path,
) -> None:
    root = copy_fixture(tmp_path)
    author_all(root)

    def write_invalid(request: TurnRequest, tools: Any) -> list[str]:
        if request.stage != "outputs":
            scripted_review(tools, str(request.stage))
            return ["Reviewed."]
        draft = tools.call("read_draft", {"layer": "outputs"})["data"]
        tools.call("analyse_routes", {})
        entry = dict(draft["data"]["outputs"][0]) | {"description": None}
        tools.call(
            "replace_draft",
            {
                "layer": "outputs",
                "expected_sha256": draft["sha256"],
                "section": "/outputs",
                "data": [entry],
            },
        )
        tools.call(
            "record_blocker",
            {
                "decision": "What the first output contains",
                "artefact": ".splice-local/drafts/outputs.draft.yaml",
            },
        )
        return ["I could not finish the catalogue."]

    engine = SessionEngine.create(
        root,
        mode=InteractionMode.AUTONOMOUS,
        provider=ScriptedProvider(write_invalid),
        objective="author",
        policy=ExecutionPolicy(),
        actor=ADA.actor,
    )
    asyncio.run(engine.advance())
    draft = _draft(root, "outputs")
    assert len(draft["outputs"]) == 1 and draft["outputs"][0]["description"] is None
    assert not validate_layer(root, "outputs").ready
    assert engine.state.stages[Stage.OUTPUTS].status is StageStatus.BLOCKED
    assert engine.report()["completion"] == "partial"


def test_core_09_a_valid_draft_is_still_reviewed_by_the_agent(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path)
    author_all(root)
    assert validate_layer(root, "outputs").ready
    provider = ScriptedProvider(review_turns("identity", "inputs"))
    engine = SessionEngine.create(
        root,
        mode=InteractionMode.ASSISTED,
        provider=provider,
        objective="review",
        policy=ExecutionPolicy(),
        actor=ADA.actor,
    )
    asyncio.run(engine.advance())
    # Identity and inputs validated, yet each needed a review turn; outputs
    # is next and waits for its own review rather than being skipped.
    stages = [item.stage for item in provider.requests]
    assert stages[:3] == ["identity", "inputs", "outputs"]
    identity = engine.state.stages[Stage.IDENTITY]
    assert identity.status is StageStatus.COMPLETED
    assert identity.review is not None and identity.review.kind == "scientific"
    assert any(
        item.startswith("read_source main.nf:1-") for item in identity.review.inspected
    )
    assert engine.state.stages[Stage.OUTPUTS].status is not StageStatus.COMPLETED


def test_core_09_a_review_without_inspection_is_refused(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path)
    author_all(root)
    provider = ScriptedProvider(
        [
            {
                "stage": "identity",
                "steps": [
                    {
                        "tool": "complete_review",
                        "arguments": review_arguments("identity"),
                    }
                ],
            }
        ]
    )
    engine = SessionEngine.create(
        root,
        mode=InteractionMode.ASSISTED,
        provider=provider,
        objective="review",
        policy=ExecutionPolicy(),
        actor=ADA.actor,
    )
    asyncio.run(engine.advance())
    assert engine.state.stages[Stage.IDENTITY].status is not StageStatus.COMPLETED
    assert any(
        "a review needs evidence" in item.text for item in engine.state.conversation
    )


def test_core_11_unsafe_content_paths_and_secrets_are_refused(tmp_path: Path) -> None:
    from nf_splice.layers.execution import write_config_draft

    root = copy_fixture(tmp_path)
    initialise(root, ADA)
    state = read_layer(root, "outputs")
    tagged = (state.file.text or "") + "evil: !!python/object:os.system ls\n"
    with pytest.raises(LayerError, match="unsafe or invalid YAML"):
        replace_draft(
            root, "outputs", ADA, expected_sha256=state.file.sha256, content=tagged
        )
    with pytest.raises(LayerError, match="x-splice-draft"):
        replace_draft(
            root,
            "outputs",
            ADA,
            expected_sha256=state.file.sha256,
            content="outputs: []\n",
        )
    with pytest.raises(LayerError, match="config name"):
        write_config_draft(root, "../../escape", "x", ADA, expected_sha256=None)
    (root / ".env").write_text("TOKEN=abc\n", encoding="utf-8")
    context = OperationContext(root=root, change=ADA, policy=ExecutionPolicy())
    with pytest.raises(PolicyViolation, match="secrets file"):
        OPERATIONS["read_source"].handler(context, {"path": ".env"})
    assert read_layer(root, "outputs").file.sha256 == state.file.sha256


# ------------------------------------------------------------ identity


def test_id_03_nested_identity_is_authored_in_the_file_and_consent_is_kept(
    tmp_path: Path,
) -> None:
    root = copy_fixture(tmp_path)
    author_all(root)

    def nested(data: dict[str, Any]) -> None:
        data["pipeline"]["authors"] = [
            {"name": "Ada Lovelace", "affiliation": "Analytical Engines"},
            {"name": "Beatson Institute", "type": "organization"},
        ]
        data["pipeline"]["funders"] = [{"name": "CRUK", "award_id": "A1"}]
        data["pipeline"]["citation"] = {"doi": "10.5281/zenodo.1234567"}
        data["maintainers"] = [{"name": "Grace Hopper", "email": "grace@uni.ac.uk"}]

    edit_draft_file(root, "bundle", nested)
    edit_draft_file(
        root,
        "provenance",
        lambda data: (
            data["crate"]["@graph"][1].update(
                creator=[{"@id": "#ada"}, {"@id": "#beatson"}]
            )
            or data["crate"]["@graph"].extend(
                [
                    {"@id": "#ada", "@type": "Person", "name": "Ada Lovelace"},
                    {
                        "@id": "#beatson",
                        "@type": "Organization",
                        "name": "Beatson Institute",
                    },
                ]
            )
        ),
    )
    # Consent stays a person's explicit decision, even in a hand-edited file.
    blockers = plan_promotion(root).blockers
    assert any("maintainers_publication_approved" in item.message for item in blockers)
    edit_draft_file(
        root, "bundle", lambda data: data.update(maintainers_publication_approved=True)
    )
    build(root)
    bundle = json.loads((root / "splice/bundle.json").read_text("utf-8"))
    assert bundle["pipeline"]["funders"][0]["name"] == "CRUK"
    assert bundle["pipeline"]["authors"][1]["type"] == "organization"
    assert bundle["maintainers"][0]["name"] == "Grace Hopper"


# ------------------------------------------------------------ inputs


@pytest.mark.parametrize(
    "principals",
    [
        [],
        ["user"],
        ["platform"],
        ["agent"],
        ["user", "platform"],
        ["user", "agent"],
        ["platform", "agent"],
        ["user", "platform", "agent"],
    ],
)
def test_in_03_08_every_principal_combination_is_enforced_by_the_service(
    principals: list[str],
) -> None:
    schema = {
        "properties": {
            "threshold": {
                "type": "number",
                "default": 1,
                "x-splice-access": {"editable_by": principals},
                "x-splice-ui": {"visibility": "hidden"},
            }
        }
    }
    for principal in Principal:
        denied = authorise_changes(schema, principal, {"threshold": 2})
        assert (not denied) == (principal.value in principals), principal


def test_in_05_an_unbound_required_input_blocks_ingestion_readiness(
    tmp_path: Path,
) -> None:
    root = copy_fixture(tmp_path)
    author_all(root)

    def required(data: dict[str, Any]) -> None:
        for group in data.get("$defs", {}).values():
            if "input" in group.get("properties", {}):
                group.setdefault("required", [])
                if "input" not in group["required"]:
                    group["required"].append("input")
                group["properties"]["input"]["x-splice-access"] = {"editable_by": []}

    edit_draft_file(root, "inputs", required)
    build(root)
    readiness = assess_readiness(root)
    runtime = readiness.dimensions["runtime_parameters"]
    assert runtime.status == "blocked" and "input" in runtime.blockers[0]
    assert not readiness.ingestion_ready
    assert validate_bundle(root).structurally_valid  # valid, but not ready


# ------------------------------------------------------------ outputs


def test_out_01_03_04_07_routes_seed_a_catalogue_and_coverage_is_substantive(
    tmp_path: Path,
) -> None:
    root = copy_fixture(tmp_path)
    initialise(root, ADA)
    keys = {item["key"] for item in _draft(root, "outputs")["outputs"]}
    # Both aligner routes are published alternatives (one example uses STAR).
    assert {"star_align_bam", "hisat2_align_bam", "quant"} <= keys
    # SAMTOOLS_SORT declares a BAM no rule publishes: an intermediate.
    patterns = " ".join(
        pattern
        for item in _draft(root, "outputs")["outputs"]
        for pattern in item["path_patterns"]
    )
    assert r"\.sorted\.bam" not in patterns
    root = copy_fixture(tmp_path / "authored")
    author_all(root)
    edit_draft_file(
        root,
        "outputs",
        lambda data: data.update(
            outputs=[
                item for item in data["outputs"] if item["key"] != "hisat2_alignment"
            ]
        ),
    )
    issues = validate_layer(root, "outputs").issues
    # HISAT2 is an alternative route: a classified warning, never dropped.
    covered = [item for item in issues if item.code == "conditional_route_not_covered"]
    assert covered and "HISAT2_ALIGN" in covered[0].message
    assert "when " in covered[0].message
    assert all(item.severity.value == "warning" for item in covered)
    assert "pending_candidate" not in {item.code for item in issues}


# ------------------------------------------------------------ components


NF_CORE_TERNARY = """process FASTP {
    container "${ workflow.containerEngine in ['apptainer','singularity'] &&
        !task.ext.singularity_pull_docker_container ?
        'https://depot.galaxyproject.org/singularity/fastp:1.0.1--heae3180_0' :
        'quay.io/biocontainers/fastp:1.0.1--heae3180_0' }"

    input:
    path reads
}
"""


def test_comp_02_03_06_runtime_branches_and_cache_names(tmp_path: Path) -> None:
    module = tmp_path / "main.nf"
    module.write_text(NF_CORE_TERNARY, encoding="utf-8")
    sources = {
        item.runtime.value: item.raw for item in container_sources(module, "main.nf")
    }
    assert sources == {
        "singularity": "https://depot.galaxyproject.org/singularity/fastp:1.0.1--heae3180_0",
        "apptainer": "https://depot.galaxyproject.org/singularity/fastp:1.0.1--heae3180_0",
        "docker": "quay.io/biocontainers/fastp:1.0.1--heae3180_0",
    }
    assert nextflow_cache_filename(sources["singularity"]) == (
        "depot.galaxyproject.org-singularity-fastp-1.0.1--heae3180_0.img"
    )
    assert nextflow_cache_filename(sources["docker"]) == (
        "quay.io-biocontainers-fastp-1.0.1--heae3180_0.img"
    )
    # A dynamic expression is kept verbatim, never guessed.
    module.write_text(
        'process X {\n    container "${params.registry}/tool:${params.tag}"\n\n'
        "    input:\n}\n",
        encoding="utf-8",
    )
    [dynamic] = container_sources(module, "main.nf")
    assert dynamic.kind.value == "unresolved_expression"
    assert "params.registry" in dynamic.raw


def test_comp_05_published_container_ids_are_kept(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path)
    (root / "splice").mkdir()
    module = root / "modules/local/fastqc/main.nf"
    [source] = [item.raw for item in container_sources(module, "x")][:1] or ["?"]
    (root / "splice/components.json").write_text(
        json.dumps(
            {
                "containers": [
                    {"id": "container-0123456789ab", "uri": source, "type": "docker"}
                ],
                "components": [],
            }
        ),
        encoding="utf-8",
    )
    initialise(root, ADA)
    containers = _draft(root, "components")["containers"]
    assert "container-0123456789ab" in {item["id"] for item in containers}


class _Body:
    def __init__(self, data: bytes) -> None:
        self._stream = io.BytesIO(data)

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)


class FakeStore:
    """An in-memory S3 subset; ``corrupt`` makes read-back differ."""

    def __init__(self, *, corrupt: bool = False) -> None:
        self.objects: dict[str, tuple[bytes, dict[str, str]]] = {}
        self.corrupt = corrupt

    def head_object(self, **kwargs: Any) -> dict[str, Any]:
        if kwargs["Key"] not in self.objects:
            error = Exception("missing")
            error.response = {"Error": {"Code": "404"}}  # type: ignore[attr-defined]
            raise error
        data, metadata = self.objects[kwargs["Key"]]
        return {"ContentLength": len(data), "Metadata": metadata}

    def put_object(self, **kwargs: Any) -> dict[str, Any]:
        data = kwargs["Body"].read()
        self.objects[kwargs["Key"]] = (data, dict(kwargs["Metadata"]))
        return {}

    def get_object(self, **kwargs: Any) -> dict[str, Any]:
        data = self.objects[kwargs["Key"]][0]
        return {"Body": _Body(data + (b"x" if self.corrupt else b""))}


SIF = b"#!/usr/bin/env run-singularity\n\0" + b"SIF_MAGIC" + b"\0" * 64


def test_comp_08_09_10_uploads_are_verified_and_never_overwrite(
    tmp_path: Path,
) -> None:
    from nf_splice.services.containers import ContainerServiceError
    from nf_splice.services.images import S3Uploader, StoreSettings, deliver_images

    image = tmp_path / "image.sif"
    image.write_bytes(SIF)
    sha = hashlib.sha256(SIF).hexdigest()
    settings = StoreSettings("https://s3.example.ac.uk", "images", "nf/")
    store = FakeStore()
    uploader = S3Uploader(settings, store)
    assert uploader.upload(image, "tool.img", sha) == "uploaded"
    assert uploader.upload(image, "tool.img", sha) == "already_stored"  # idempotent
    other = tmp_path / "other.sif"
    other.write_bytes(SIF + b"different")
    with pytest.raises(ContainerServiceError, match="never overwrites"):
        uploader.upload(
            other, "tool.img", hashlib.sha256(other.read_bytes()).hexdigest()
        )
    corrupt = S3Uploader(settings, FakeStore(corrupt=True))
    with pytest.raises(ContainerServiceError, match="read-back"):
        corrupt.upload(image, "tool.img", sha)

    # COMP-10: without approval nothing is fetched, uploaded or recorded, and
    # without a public URL nothing is claimed downloadable.
    root = copy_fixture(tmp_path / "pipeline")
    author_all(root)
    with pytest.raises(ContainerServiceError, match="network approval"):
        deliver_images(
            root, ADA, approve_network=False, approve_upload=True, uploader=uploader
        )

    def fake_download(url: str, *, scratch: Path, keep_as: Path) -> None:
        keep_as.write_bytes(SIF)

    def fake_pull(source: str, target: Path, *, approve_network: bool) -> Any:
        target.write_bytes(SIF)

    recorded: list[str] = []
    actions = deliver_images(
        root,
        ADA,
        approve_network=True,
        approve_upload=True,
        uploader=S3Uploader(settings, FakeStore()),
        verify=fake_download,
        materialise=fake_pull,
        record=lambda *args: recorded.append(args[2]),
    )
    assert actions and all("not recorded" in str(item.outcome) for item in actions)
    assert recorded == []
    assert all(
        item.get("distribution") is None
        for item in _draft(root, "components")["containers"]
    )


@pytest.mark.s3
@pytest.mark.skipif(
    os.environ.get("NF_SPLICE_S3_TEST") != "1",
    reason="opt-in: set NF_SPLICE_S3_TEST=1 and NF_SPLICE_S3_* for a test bucket",
)
def test_comp_09_real_store_round_trip(tmp_path: Path) -> None:
    from nf_splice.services.images import S3Uploader, load_settings, s3_client

    settings = load_settings()
    assert settings is not None
    uploader = S3Uploader(settings, s3_client(settings))
    image = tmp_path / "nf-splice-test.img"
    image.write_bytes(SIF + os.urandom(16))
    sha = hashlib.sha256(image.read_bytes()).hexdigest()
    name = f"nf-splice-test-{sha[:12]}.img"
    assert uploader.upload(image, name, sha) == "uploaded"
    assert uploader.upload(image, name, sha) == "already_stored"


# ------------------------------------------------------------ execution


def test_exe_05_07_memory_null_sizing_and_unguarded_task_memory(
    tmp_path: Path,
) -> None:
    from nf_splice.services.execution_review import analyse_execution

    root = tmp_path / "pipeline"
    (root / "conf").mkdir(parents=True)
    (root / "conf/base.config").write_text(
        "process {\n  withLabel:process_medium {\n    cpus = { 6 * task.attempt }\n"
        "    memory = { 36.GB * task.attempt }\n  }\n}\n",
        encoding="utf-8",
    )
    (root / "modules/qualimap").mkdir(parents=True)
    (root / "modules/qualimap/main.nf").write_text(
        "process QUALIMAP {\n    label 'process_medium'\n    script:\n"
        "    def memory = (task.memory.mega*0.8).intValue() + 'M'\n}\n",
        encoding="utf-8",
    )
    (root / "modules/fastqc").mkdir(parents=True)
    (root / "modules/fastqc/main.nf").write_text(
        "process FASTQC {\n    label 'process_medium'\n    script:\n"
        "    def mb = task.memory ? task.memory.toUnit('MB') / task.cpus : null\n"
        "    def fastqc_memory = mb > 10000 ? 10000 : (mb < 100 ? 100 : mb)\n}\n",
        encoding="utf-8",
    )
    cirrus = (
        "process {\n  withName: '.*' {\n    memory = null\n  }\n}\n"
        "env {\n  NXF_EXECUTOR_MEM_GIGA_PER_CORE = 2\n}\n"
        "process { executor = 'slurm' }\n"
    )
    report = analyse_execution(root, cirrus)
    assert report["config"]["memory_null_for_every_process"]
    assert report["config"]["gigabytes_per_core"] == 2.0
    [sizing] = report["cpu_sizing"]
    assert sizing["cpus_for_intended_memory"] == 18  # 36 GB at 2 GB per CPU
    unguarded = {item["process"] for item in report["unguarded_task_memory"]}
    assert unguarded == {"QUALIMAP"}
    fastqc = next(
        item for item in report["task_memory_uses"] if item["process"] == "FASTQC"
    )
    assert fastqc["guarded"] and fastqc["derived_uses"]  # falls back to 100 MB


@pytest.mark.nextflow
@pytest.mark.skipif(
    os.environ.get("NF_SPLICE_NEXTFLOW_TESTS") != "1"
    or shutil.which("nextflow") is None,
    reason="opt-in: requires a local nextflow and NF_SPLICE_NEXTFLOW_TESTS=1",
)
def test_exe_06_effective_config_has_no_memory_request(tmp_path: Path) -> None:
    from nf_splice.services.checks import nextflow_config_check

    root = copy_fixture(tmp_path)
    config = root / "conf/cirrus.config"
    config.write_text(
        "process {\n  executor = 'slurm'\n  memory = '4 GB'\n"
        "  withName: '.*' {\n    memory = null\n  }\n}\n",
        encoding="utf-8",
    )
    nulled = nextflow_config_check(
        root, permitted={"run_nextflow"}, profile_config="conf/cirrus.config"
    )
    if nulled.status.value == "not_run":
        pytest.skip(f"Nextflow cannot run here: {nulled.reason}")
    assert nulled.status.value == "passed", nulled.output_excerpt
    config.write_text("process {\n  memory = '4 GB'\n}\n", encoding="utf-8")
    requested = nextflow_config_check(
        root, permitted={"run_nextflow"}, profile_config="conf/cirrus.config"
    )
    assert requested.warnings, requested.output_excerpt
    refused = nextflow_config_check(root, permitted=set())
    assert refused.status.value == "not_run"


# ------------------------------------------------------------ RO-Crate and ZIPs


def test_roc_08_09_10_archives_project_the_crate_without_touching_sources(
    tmp_path: Path,
) -> None:
    root = copy_fixture(tmp_path)
    write_root_crate(root, "multiroute", "0.9.0")  # stale, developer-owned
    original = (root / "ro-crate-metadata.json").read_bytes()
    author_all(root)
    build(root)
    pipeline = export_archive(root, ExportScope.PIPELINE, tmp_path / "pipeline.zip")
    with zipfile.ZipFile(pipeline.path) as archive:
        names = archive.namelist()
        assert names.count("ro-crate-metadata.json") == 1  # exactly one root
        assert (
            archive.read("ro-crate-metadata.json")
            == (root / "splice/ro-crate-metadata.json").read_bytes()
        )
    assert (root / "ro-crate-metadata.json").read_bytes() == original
    assert any("replaced in the archive" in item for item in pipeline.checks)

    bundle = export_archive(root, ExportScope.BUNDLE, tmp_path / "bundle.zip")
    with zipfile.ZipFile(bundle.path) as archive:
        assert "ro-crate-metadata.json" not in archive.namelist()
        crate = json.loads(archive.read("splice/ro-crate-metadata.json"))
    text = json.dumps(crate)
    # ROC-10: no invented download location and no self-referential checksum.
    assert "contentUrl" not in text and "DataDownload" not in text
    assert pipeline.sha256 not in text


@pytest.mark.rocrate_validator
@pytest.mark.skipif(
    not os.environ.get("NF_SPLICE_ROCRATE_VALIDATOR"),
    reason="opt-in: set NF_SPLICE_ROCRATE_VALIDATOR to a rocrate-validator",
)
def test_roc_07_pipeline_archive_conforms_to_workflow_ro_crate(tmp_path: Path) -> None:
    from nf_splice.services.checks import rocrate_validation

    root = copy_fixture(tmp_path)
    author_all(root)
    build(root)
    result = rocrate_validation(root, permitted={"external_tools", "network"})
    assert result.status.value == "passed", result.failures


# ------------------------------------------------------------ agents


def _toolbox(
    root: Path, layer: str, mode: ToolMode = ToolMode.EXECUTE
) -> SessionToolbox:
    return SessionToolbox(
        root=root,
        policy=ExecutionPolicy(),
        mode=mode,
        operations={"replace_draft", "read_draft", "read_source", "write_config"},
        controls={"complete_review"},
        change=ChangeContext(
            actor=Actor(label="agent"), origin=ChangeOrigin.AGENT_AUTONOMOUS
        ),
        usage=Usage(),
        stage_layer=layer,
    )


def test_ai_01_replace_draft_is_mediated_and_bounded(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path)
    author_all(root)
    tools = _toolbox(root, "outputs")
    read = tools.call("read_draft", {"layer": "outputs"})["data"]
    wrong_layer = tools.call(
        "replace_draft",
        {
            "layer": "bundle",
            "expected_sha256": read["sha256"],
            "section": "/x",
            "data": 1,
        },
    )
    assert wrong_layer["denied"]
    stale = tools.call(
        "replace_draft",
        {
            "layer": "outputs",
            "expected_sha256": "0" * 64,
            "section": "/outputs",
            "data": [],
        },
    )
    assert not stale["success"] and "changed on disk" in stale["issues"][0]
    saved = tools.call(
        "replace_draft",
        {
            "layer": "outputs",
            "expected_sha256": read["sha256"],
            "section": "/outputs",
            "data": [],
        },
    )
    assert saved["success"] and saved["validation"]["ready"] is False
    events = load_review_state(root, "outputs").events
    assert events[-1]["action"] == "replace_section"
    assert events[-1]["origin"] == "agent_autonomous"

    # Assay capabilities change only through the vocabulary-checked tools.
    identity = _toolbox(root, "bundle")
    current = identity.call("read_draft", {"layer": "bundle"})["data"]
    refused = identity.call(
        "replace_draft",
        {
            "layer": "bundle",
            "expected_sha256": current["sha256"],
            "section": "/pipeline/assay_capabilities",
            "data": [],
        },
    )
    assert refused["denied"]
    granted = ExecutionPolicy(grants=[Permission.READ])
    with pytest.raises(PolicyViolation):
        granted.require(Permission.DRAFT_EDIT)


def test_ai_07_reasoning_effort_is_applied_honestly() -> None:
    assert resolve_effort(
        "high", ("low", "medium", "high"), provider="p", control="c"
    ) == (
        "high",
        None,
    )
    sent, notice = resolve_effort(
        "max", ("low", "medium", "high"), provider="p", control="c"
    )
    assert sent == "high" and notice and "'high' was used" in notice
    sent, notice = resolve_effort("high", (), provider="p", control="c")
    assert sent is None and notice and "not applied" in notice
    assert resolve_effort(None, ("high",), provider="p", control="c") == (None, None)


def test_ai_07_adapters_send_their_native_controls(tmp_path: Path) -> None:
    from nf_splice.agents.providers.claude import ClaudeSession, sdk_efforts
    from nf_splice.agents.providers.openai import OpenAIProvider, OpenAISession

    session = OpenAISession(OpenAIProvider(model="m"))
    tools = _toolbox(tmp_path, "outputs", ToolMode.OBSERVE)
    request = TurnRequest(
        purpose="plan",
        instruction="x",
        system_prompt="s",
        tools=tools,
        reasoning_effort="high",
    )
    session.effort = "high"
    assert session._body(request, "m")["reasoning"] == {"effort": "high"}
    if not sdk_efforts():
        pytest.skip("the Claude Agent SDK is not installed")
    sdk = pytest.importorskip("claude_agent_sdk")

    claude = ClaudeSession(tmp_path, None)
    options = claude.options(sdk, request)
    assert options.effort == "high" and options.thinking == {"type": "adaptive"}
    low = claude.options(
        sdk,
        TurnRequest(purpose="plan", instruction="x", system_prompt="s", tools=tools),
    )
    assert low.effort is None


# ------------------------------------------------------------ real pipeline


REFERENCE = os.environ.get("NF_SPLICE_BULK_RNASEQ")


@pytest.mark.reference_pipeline
@pytest.mark.skipif(
    not REFERENCE, reason="opt-in: set NF_SPLICE_BULK_RNASEQ to a pipeline checkout"
)
def test_in_06_comp_01_exe_05_real_bulk_rnaseq_pipeline(tmp_path: Path) -> None:
    source = Path(str(REFERENCE))
    root = tmp_path / "bulk"
    shutil.copytree(
        source,
        root,
        ignore=shutil.ignore_patterns(".git", ".splice-local", "work", ".nextflow*"),
    )
    before = {
        path.relative_to(source).as_posix(): path.stat().st_mtime_ns
        for path in source.rglob("*")
        if path.is_file() and ".git" not in path.parts
    }
    initialise(root, ADA)
    from nf_splice.inspectors.parameters import parameter_usage
    from nf_splice.layers.inputs import iter_parameters
    from nf_splice.services.execution_review import analyse_execution

    parameters = list(iter_parameters(_draft(root, "inputs")))
    assert len(parameters) == 122  # IN-06: every declared parameter
    assert all(item.editable_by == () for item in parameters)
    usage = parameter_usage(root).references
    assert usage["genomes"].classification({item.name for item in parameters}) == (
        "internal_mapping"
    )
    assert usage["jobfile_fastq_dir"].classification(set()) == "comment_only"

    components = _draft(root, "components")  # COMP-01
    assert len(components["components"]) == 72
    published = json.loads((root / "splice/components.json").read_text("utf-8"))
    kept = {item["id"] for item in published["containers"]} & {
        item["id"] for item in components["containers"]
    }
    assert len(kept) == len(published["containers"])
    fastqc = next(item for item in components["components"] if "fastqc" in item["id"])
    container = next(
        item
        for item in components["containers"]
        if item["id"] == fastqc["container_id"]
    )
    assert container["source_images"]["singularity"].startswith(
        "https://depot.galaxyproject.org/singularity/fastqc"
    )
    assert container["source_images"]["docker"].startswith("quay.io/biocontainers/")

    config = root / ".splice-local/drafts/configs/default.draft.config"  # EXE-05
    report = analyse_execution(root, config.read_text(encoding="utf-8"))
    assert report["config"]["memory_null_for_every_process"]
    assert report["config"]["gigabytes_per_core"] == 2.0
    assert {item["process"] for item in report["unguarded_task_memory"]} >= {
        "QUALIMAP_RNASEQ",
        "UMICOLLAPSE",
    }
    assert {
        path.relative_to(source).as_posix(): path.stat().st_mtime_ns
        for path in source.rglob("*")
        if path.is_file() and ".git" not in path.parts
    } == before


def test_fixture_is_unchanged_by_the_suite() -> None:
    """The committed multi-route fixture is byte-exact input, never output."""
    assert not (FIXTURE / "repository" / ".splice-local").exists()
