"""nf-splice on pipelines that are neither bulk RNA-seq nor nf-core (ADR-0064).

Two fixtures exercise all six layers end to end:

- ``spatial-imaging-0.3.0``: imaging-based spatial transcriptomics with two
  alternative platform routes (Xenium and CosMx, so two assays on Imaging and
  Transcriptomics paths), OME-TIFF and CSV outputs, a GPU label, a
  Kubernetes profile with Docker, and a module with no container;
- ``minimal-custom-0.3.0``: no ``nextflow_schema.json``, no ``modules.json``,
  no ``modules/`` and no nf-core conventions, one inline process tiling H&E
  whole-slide images.

The scripted sessions prove operations, approvals, blockers and evidence
records only; no real model reasoned about these pipelines.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from layer_fixtures import (
    ADA,
    STAGE_ANALYSIS,
    edit_draft_file,
    follow_scope,
    review_arguments,
)
from nf_splice.agents import ExecutionPolicy, InteractionMode, SessionEngine
from nf_splice.agents.protocol import ToolInvoker, TurnRequest
from nf_splice.agents.providers.scripted import ScriptedProvider
from nf_splice.drafts import resolve
from nf_splice.layers.base import read_layer
from nf_splice.layers.bundle import add_assay_capability
from nf_splice.layers.execution import CONFIGS_DIR
from nf_splice.layers.inputs import iter_parameters, sync_identity
from nf_splice.layers.provenance import generate_minimal
from nf_splice.services.assay_discovery import assess_assays
from nf_splice.services.lifecycle import promote, validate_layer
from nf_splice.services.readiness import INGESTION_READY, lifecycle
from nf_splice.services.workspace import initialise

FIXTURES = Path(__file__).parent / "fixtures"
SPATIAL = FIXTURES / "spatial-imaging-0.3.0" / "repository"
MINIMAL = FIXTURES / "minimal-custom-0.3.0" / "repository"

SPATIAL_IDENTITY = {
    "id": "spatialcells",
    "name": "spatialcells",
    "repository_url": "https://github.com/org/spatialcells",
    "licence": "MIT",
    "released_at": "2026-10-15T10:00:00Z",
}
SPATIAL_ACCESS = {
    "input": ["user"],
    "outdir": ["platform"],
    "platform": ["user"],
    "segmentation_model": ["user"],
}
#: What each seeded output means: title, description, formats, scope and,
#: where the seed guessed wrong, the corrected pattern.
SPATIAL_OUTPUTS: dict[str, tuple[str, str, list[str], str, str | None]] = {
    "matrix": (
        "Cell-by-gene matrix",
        "Transcript counts per segmented cell for one slide region.",
        ["csv"],
        "sample",
        r"^quantification/{sample}\.cell_by_gene\.csv$",
    ),
    "report": (
        "Spatial report",
        "Segmentation and quantification summary for the whole job.",
        ["html"],
        "job",
        None,
    ),
    "xenium_preprocess_morphology": (
        "Xenium morphology image",
        "Morphology image of one Xenium region.",
        ["ome-tiff"],
        "sample",
        None,
    ),
    "cosmx_preprocess_morphology": (
        "CosMx morphology image",
        "Morphology image of one CosMx region.",
        ["ome-tiff"],
        "sample",
        None,
    ),
    "masks": (
        "Cell masks",
        "Cellpose segmentation masks of one region.",
        ["ome-tiff"],
        "sample",
        None,
    ),
}
K8S_PROFILE = {
    "id": "k8s",
    "name": "Kubernetes",
    "description": "Production on a Kubernetes cluster with Docker.",
    "type": "production",
    "engine": "nextflow",
    "executor": "k8s",
    "container_engine": "docker",
    "config": {"adopt": "conf/k8s.config"},
}
#: Words that would betray a default borrowed from one pipeline or site.
_BORROWED = ("cirrus", "epcc", "slurm", "star_align", "salmon", "hisat2", "rnaseq")


def _copy(source: Path, tmp_path: Path, name: str) -> Path:
    root = tmp_path / name
    shutil.copytree(source, root)
    return root


def _hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
        and path.relative_to(root).parts[0] not in {".splice-local"}
        and path.name != ".gitignore"
        and path.relative_to(root).parts[0] != "splice"
    }


def _draft(root: Path, layer: str) -> dict[str, Any]:
    state = read_layer(root, layer)
    assert state.draft is not None, state.error
    data: dict[str, Any] = state.draft.data
    return data


def _author_outputs(data: dict[str, Any]) -> None:
    for item in data["outputs"]:
        title, description, formats, scope, pattern = SPATIAL_OUTPUTS[item["key"]]
        item.update(
            title=title, description=description, formats=formats, scopes=[scope]
        )
        if pattern is not None:
            item["path_patterns"] = [pattern]


def author_spatial(root: Path) -> None:
    """Author all six layers of the imaging pipeline by editing the files."""

    def identity(data: dict[str, Any]) -> None:
        data["pipeline"].update(SPATIAL_IDENTITY)

    edit_draft_file(root, "bundle", identity)
    for code in ("xenium_rna", "cosmx_rna"):
        add_assay_capability(
            root,
            code,
            ADA,
            evidence="documented",
            rationale="README.md names the platform's output this route reads.",
            sources=("README.md:5",),
        )
    sync_identity(root, ADA)

    def inputs(data: dict[str, Any]) -> None:
        for parameter in iter_parameters(data):
            if parameter.name in SPATIAL_ACCESS:
                resolve(data, parameter.pointer)["x-splice-access"] = {
                    "editable_by": SPATIAL_ACCESS[parameter.name]
                }

    edit_draft_file(root, "inputs", inputs)
    edit_draft_file(root, "outputs", _author_outputs)
    edit_draft_file(
        root, "components", lambda data: data.update(require_downloadable_images=False)
    )

    def profiles(data: dict[str, Any]) -> None:
        data["profiles"] = [dict(K8S_PROFILE)]
        data["default_profile"] = "k8s"

    edit_draft_file(root, "execution-profiles", profiles)
    (root / CONFIGS_DIR / "default.draft.config").unlink()
    generate_minimal(root, ADA, at="2026-10-15T10:00:00Z")


def _published(root: Path, name: str) -> Any:
    return json.loads((root / "splice" / name).read_text(encoding="utf-8"))


# ------------------------------------------------------------ manual mode


def test_spatial_imaging_seeds_honestly_with_no_borrowed_defaults(
    tmp_path: Path,
) -> None:
    root = _copy(SPATIAL, tmp_path, "spatialcells")
    before = _hashes(root)
    report = initialise(root, ADA)
    assert set(report.created) == {
        "bundle",
        "inputs",
        "outputs",
        "components",
        "execution-profiles",
        "provenance",
    }
    # Assays come from the documentation, not from tool names, and both
    # platforms of the alternative routes are found.
    assessment = assess_assays(root)
    found = {
        item.registered_code
        for item in assessment.candidates
        if item.registered_code and item.status == "documented"
    }
    assert {"xenium_rna", "cosmx_rna"} <= found
    assert not _draft(root, "bundle")["pipeline"]["assay_capabilities"]
    # Categories are the pipeline's own directories; formats are open.
    outputs = {item["key"]: item for item in _draft(root, "outputs")["outputs"]}
    assert outputs["masks"]["category"] == "segmentation"
    assert outputs["matrix"]["category"] == "quantification"
    # Both platform routes are seeded: the catalogue is their union.
    assert {"xenium_preprocess_morphology", "cosmx_preprocess_morphology"} <= set(
        outputs
    )
    components = {
        item["name"]: item for item in _draft(root, "components")["components"]
    }
    assert set(components) >= {"segment_cells", "write_index"} or len(components) == 6
    # The default profile is a neutral scaffold: local, no site or tool.
    profile = _draft(root, "execution-profiles")["profiles"][0]
    assert profile["id"] == "default" and profile["executor"] in {None, "local"}
    seeded = " ".join(
        path.read_text(encoding="utf-8").lower()
        for path in (root / ".splice-local" / "drafts").rglob("*")
        if path.is_file()
    )
    assert not [word for word in _BORROWED if word in seeded]
    assert _hashes(root) == before  # the pipeline itself is untouched


def test_spatial_imaging_publishes_all_six_layers_ready_for_ingestion(
    tmp_path: Path,
) -> None:
    root = _copy(SPATIAL, tmp_path, "spatialcells")
    before = _hashes(root)
    initialise(root, ADA)
    author_spatial(root)
    promote(root, None, ADA)
    state = lifecycle(root)
    assert state.state == INGESTION_READY, state.reasons()

    bundle = _published(root, "bundle.json")
    capabilities = bundle["pipeline"]["assay_capabilities"]
    assert {item["registered_code"] for item in capabilities} == {
        "xenium_rna",
        "cosmx_rna",
    }
    modalities = {
        modality["label"] for item in capabilities for modality in item["modalities"]
    }
    assert {"Imaging", "Transcriptomics"} <= modalities

    catalogue = _published(root, "outputs.schema.json")["x-output-catalog"]
    formats = {fmt for item in catalogue["output_types"] for fmt in item["format"]}
    assert "ome-tiff" in formats
    profiles = _published(root, "execution-profiles.json")
    assert profiles["profiles"][0]["executor"] == "k8s"
    assert profiles["profiles"][0]["container_engine"] == "docker"
    deployment = state.readiness.dimensions["deployment"]
    assert any("write_index" in note for note in deployment.notes)
    assert _hashes(root) == before


def test_assays_are_never_inferred_from_familiar_tools(tmp_path: Path) -> None:
    root = _copy(SPATIAL, tmp_path, "undocumented")
    (root / "README.md").unlink()
    shutil.rmtree(root / "docs")
    config = root / "nextflow.config"
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            "Cell segmentation and cell-by-gene matrices for imaging-based spatial "
            "transcriptomics.",
            "Cell segmentation and quantification.",
        ),
        encoding="utf-8",
    )
    initialise(root, ADA)
    assessment = assess_assays(root)
    documented = [item for item in assessment.candidates if item.status == "documented"]
    assert not documented
    assert not _draft(root, "bundle")["pipeline"]["assay_capabilities"]


def test_a_minimal_custom_pipeline_is_handled_honestly(tmp_path: Path) -> None:
    root = _copy(MINIMAL, tmp_path, "slidetiler")
    report = initialise(root, ADA)
    notes = " ".join(report.notes)
    assert "nextflow_schema.json not found" in notes
    assert "modules.json not found" in notes
    identity = {item.code for item in validate_layer(root, "bundle").issues}
    assert "missing_required" in identity  # nothing is guessed
    inputs = validate_layer(root, "inputs").issues
    undeclared = [item for item in inputs if item.code == "undeclared_parameter"]
    assert {"params.slides", "params.tile_size"} <= {
        word for item in undeclared for word in item.message.split()
    }
    assert _draft(root, "inputs")["properties"] == {}  # never invented
    components = _draft(root, "components")["components"]
    assert [(item["type"], item["path"], item["process"]) for item in components] == [
        ("workflow_process", "main.nf", "TILE_SLIDE")
    ]
    assert components[0]["id"] == "main__nf__TILE_SLIDE"
    assert components[0]["container_id"]
    assert _draft(root, "components")["containers"][0]["source_images"] == {
        "docker": "quay.io/example/openslide-tiler:2.1.0"
    }

    def identity_fields(data: dict[str, Any]) -> None:
        data["pipeline"].update(
            id="slidetiler",
            name="slidetiler",
            version="1.0.0",
            repository_url="https://git.lab.ac.uk/pathology/slidetiler",
            description="Tiles H&E whole-slide images.",
            licence="Apache-2.0",
            released_at="2026-10-01T00:00:00Z",
        )

    edit_draft_file(root, "bundle", identity_fields)
    add_assay_capability(
        root,
        "he_wsi",
        ADA,
        evidence="asserted",
        rationale="The lab runs it on H&E whole-slide images.",
    )
    sync_identity(root, ADA)

    def binding(name: str) -> dict[str, str]:
        return {"engine": "nextflow", "binding": f"params.{name}"}

    def contract(data: dict[str, Any]) -> None:
        data["required"] = ["slides"]
        data["properties"] = {
            "slides": {
                "type": "string",
                "format": "file-path",
                "description": "Whole-slide image files.",
                "x-splice-access": {"editable_by": ["user"]},
                "x-splice-source": binding("slides"),
            },
            "outdir": {
                "type": "string",
                "format": "directory-path",
                "default": "results",
                "description": "Results directory.",
                "x-splice-access": {"editable_by": ["platform"]},
                "x-splice-source": binding("outdir"),
            },
            "tile_size": {
                "type": "integer",
                "default": 512,
                "minimum": 64,
                "description": "Tile edge in pixels.",
                "x-splice-access": {"editable_by": ["user"]},
                "x-splice-source": binding("tile_size"),
            },
        }

    edit_draft_file(root, "inputs", contract)

    def catalogue(data: dict[str, Any]) -> None:
        data["contract"]["schema_version"] = "1.0.0"
        data["outputs"][0].update(
            title="Slide tiles",
            description="Tiles of one whole-slide image as a Zarr store.",
            formats=["zarr"],
            entity_types=["directory"],
            scopes=["sample"],
            path_patterns=[r"^tiles/{sample}\.tiles\.zarr$"],
        )

    edit_draft_file(root, "outputs", catalogue)
    edit_draft_file(
        root, "components", lambda data: data.update(require_downloadable_images=False)
    )

    def profile(data: dict[str, Any]) -> None:
        data["profiles"][0].update(
            description="One workstation with Docker.",
            type="development",
            container_engine="docker",
        )

    edit_draft_file(root, "execution-profiles", profile)
    generate_minimal(root, ADA, at="2026-10-15T10:00:00Z")
    promote(root, None, ADA)
    state = lifecycle(root)
    assert state.state == INGESTION_READY, state.reasons()
    components_json = _published(root, "components.json")
    published = components_json["components"][0]
    assert (published["type"], published["path"], published["process"]) == (
        "workflow_process",
        "main.nf",
        "TILE_SLIDE",
    )


# ------------------------------------------------------------ agents


def spatial_agent(request: TurnRequest, tools: ToolInvoker) -> list[str]:
    """Scripted authoring of the imaging pipeline through the agent tools."""
    stage = str(request.stage)
    if request.purpose in {"question", "help"} or stage not in STAGE_ANALYSIS:
        return ["Nothing to do here."]

    def draft(layer: str) -> dict[str, Any]:
        result: dict[str, Any] = tools.call("read_draft", {"layer": layer})["data"]
        return result

    if stage == "identity":
        tools.call("set_identity", {"changes": dict(SPATIAL_IDENTITY)})
        for code in ("xenium_rna", "cosmx_rna"):
            tools.call(
                "add_assay_capability",
                {
                    "reference": code,
                    "evidence": "documented",
                    "rationale": "README.md names the platform this route reads.",
                    "sources": ["README.md:5"],
                },
            )
    elif stage == "inputs":
        tools.call("sync_identity", {})
        for who in (["user"], ["platform"]):
            names = [name for name, value in SPATIAL_ACCESS.items() if value == who]
            tools.call(
                "set_parameter_access", {"parameters": names, "editable_by": who}
            )
    elif stage == "outputs":
        current = draft("outputs")
        catalogue = {"outputs": [dict(item) for item in current["data"]["outputs"]]}
        _author_outputs(catalogue)
        tools.call(
            "replace_draft",
            {
                "layer": "outputs",
                "expected_sha256": current["sha256"],
                "section": "/outputs",
                "data": catalogue["outputs"],
            },
        )
    elif stage == "components":
        tools.call("set_image_policy", {"require_downloadable": False})
    elif stage == "profiles":
        current = draft("execution-profiles")
        written = tools.call(
            "replace_draft",
            {
                "layer": "execution-profiles",
                "expected_sha256": current["sha256"],
                "section": "/profiles",
                "data": [dict(K8S_PROFILE)],
            },
        )
        tools.call(
            "replace_draft",
            {
                "layer": "execution-profiles",
                "expected_sha256": written.get("sha256")
                or written.get("result", {}).get("sha256")
                or draft("execution-profiles")["sha256"],
                "section": "/default_profile",
                "data": "k8s",
            },
        )
    elif stage == "provenance":
        tools.call("analyse_ro_crate", {})
        tools.call("provenance_strategy", {"strategy": "regenerate"})
    follow_scope(tools)
    if request.purpose == "plan":
        submitted = tools.call(
            "submit_stage_proposal",
            {
                "summary": f"Author the {stage} layer.",
                "evidence": [STAGE_ANALYSIS[stage]],
            },
        )
        if submitted.get("staged_operations"):
            return [f"Proposed the {stage} layer."]
    tools.call("complete_review", review_arguments(stage))
    return [f"Reviewed the {stage} layer."]


def _session(root: Path, mode: InteractionMode) -> SessionEngine:
    return SessionEngine.create(
        root,
        mode=mode,
        provider=ScriptedProvider(spatial_agent),
        objective="Integrate the spatial imaging pipeline with SPLICE.",
        policy=ExecutionPolicy(),
        actor=ADA.actor,
    )


_CONTRACTS = (
    "inputs.schema.json",
    "outputs.schema.json",
    "components.json",
    "execution-profiles.json",
)


def test_the_three_modes_publish_the_same_contracts_for_the_same_content(
    tmp_path: Path,
) -> None:
    manual = _copy(SPATIAL, tmp_path, "manual")
    initialise(manual, ADA)
    author_spatial(manual)
    promote(manual, None, ADA)

    autonomous = _copy(SPATIAL, tmp_path, "autonomous")
    engine = _session(autonomous, InteractionMode.AUTONOMOUS)
    asyncio.run(engine.advance())
    report = engine.report()
    assert report["readiness"]["ingestion_ready"], report["statement"]
    assert report["provider_verification"].startswith("offline scripted provider")

    assisted = _copy(SPATIAL, tmp_path, "assisted")
    engine = _session(assisted, InteractionMode.ASSISTED)
    asyncio.run(engine.advance())
    for _ in range(20):
        if engine.state.pending is None:
            break
        asyncio.run(engine.approve(ADA.actor))
    assert lifecycle(assisted).state == INGESTION_READY, lifecycle(assisted).reasons()

    for name in _CONTRACTS:
        expected = (manual / "splice" / name).read_bytes()
        assert (autonomous / "splice" / name).read_bytes() == expected, name
        assert (assisted / "splice" / name).read_bytes() == expected, name


def test_an_autonomous_run_never_guesses_an_undocumented_assay(
    tmp_path: Path,
) -> None:
    root = _copy(MINIMAL, tmp_path, "slidetiler")

    def cautious(request: TurnRequest, tools: ToolInvoker) -> list[str]:
        if request.stage == "identity":
            assessment = tools.call("assess_assays", {})
            assert assessment["success"]
            tools.call(
                "record_blocker",
                {
                    "decision": "Which assays the pipeline processes",
                    "artefact": ".splice-local/drafts/bundle.draft.yaml",
                    "attempted_checks": ["assess_assays", "read_source main.nf"],
                    "suggested_resolution": "the developer names the slide stain "
                    "and imaging method",
                },
            )
            return ["The repository does not say which assay it processes."]
        return ["Waiting for the identity."]

    engine = SessionEngine.create(
        root,
        mode=InteractionMode.AUTONOMOUS,
        provider=ScriptedProvider(cautious),
        objective="integrate",
        policy=ExecutionPolicy(),
        actor=ADA.actor,
    )
    asyncio.run(engine.advance())
    assert not _draft(root, "bundle")["pipeline"]["assay_capabilities"]
    blockers = [item for item in engine.state.blockers if not item.resolved]
    assert any("assays" in item.decision for item in blockers)
    assert engine.report()["completion"] == "partial"
    # The useful partial work stays: every draft was seeded and kept.
    assert all(
        read_layer(root, layer).draft is not None
        for layer in ("bundle", "inputs", "outputs", "components", "provenance")
    )


def test_the_components_contract_types_inline_processes() -> None:
    from nf_splice.contracts import validate_contract_document

    example = json.loads(
        (
            Path(__file__).parents[1]
            / "docs"
            / "schemas"
            / "components"
            / "v0.3.0"
            / "example.json"
        ).read_text(encoding="utf-8")
    )
    assert validate_contract_document(example).valid
    process = next(
        item for item in example["components"] if item["type"] == "workflow_process"
    )
    module = next(
        item for item in example["components"] if item["type"] == "workflow_module"
    )

    def check(component: dict[str, Any]) -> bool:
        document = dict(example)
        document["components"] = [component]
        return validate_contract_document(document).valid

    assert not check({k: v for k, v in process.items() if k != "process"})
    assert not check(process | {"path": "workflows"})  # must name the .nf file
    assert not check(module | {"process": "FASTQC"})  # modules carry no process
    assert not check(process | {"type": "inline"})


def test_inline_component_ids_are_stable_across_reseeding(tmp_path: Path) -> None:
    root = _copy(MINIMAL, tmp_path, "slidetiler")
    initialise(root, ADA)

    def rename(data: dict[str, Any]) -> None:
        data["components"][0]["id"] = "slide_tiler"
        data["require_downloadable_images"] = False

    edit_draft_file(root, "components", rename)
    # Publish just the components, as an earlier bundle would have.
    validation = validate_layer(root, "components")
    assert not validation.files  # identity is not ready yet; publish by hand
    (root / "splice").mkdir(exist_ok=True)
    published = _draft(root, "components")
    document = {
        "components": [
            {k: v for k, v in item.items() if k != "unresolved"}
            for item in published["components"]
        ],
        "containers": [],
    }
    (root / "splice" / "components.json").write_text(
        json.dumps(document), encoding="utf-8"
    )
    shutil.rmtree(root / ".splice-local")
    initialise(root, ADA)
    component = _draft(root, "components")["components"][0]
    assert component["id"] == "slide_tiler"
    assert (component["path"], component["process"]) == ("main.nf", "TILE_SLIDE")
