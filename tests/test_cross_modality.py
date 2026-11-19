"""The same integration journey for unrelated scientific domains.

One test body, no fixture-specific branches in nf-splice: each fixture only
supplies what a person would decide (its assay, the outputs it publishes,
who may set which parameter). The fixtures are a histopathology imaging
pipeline, a whole-genome bisulfite (DNA methylation) pipeline with a
different structure, and a pipeline whose assay cannot be established.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]
from typer.testing import CliRunner

from nf_splice.cli import app
from nf_splice.interfaces.tui import NfSpliceApp
from nf_splice.interfaces.tui.navigation import PAGE_IDS
from nf_splice.layers.base import read_layer
from nf_splice.layers.inputs import iter_parameters
from nf_splice.layers.outputs import route_coverage
from tui_helpers import page_text, screenshot, settle

FIXTURES = Path(__file__).parent / "fixtures"
runner = CliRunner()


@dataclass(frozen=True)
class Journey:
    fixture: str
    identity: dict[str, Any]
    assay: str
    assay_source: str
    outputs: list[dict[str, Any]]
    access: list[dict[str, Any]]
    #: Words that must never appear in this pipeline's drafts.
    foreign_words: tuple[str, ...] = ()
    groups: int = 0
    required: tuple[str, ...] = ()
    enums: dict[str, list[str]] = field(default_factory=dict)
    #: Routes the person leaves out, with a reason (written in the YAML).
    exclusions: list[dict[str, str]] = field(default_factory=list)


HISTOLOGY = Journey(
    "histology-imaging-0.3.0",
    {
        "name": "example-org/histoseg",
        "version": "0.4.0",
        "repository_url": "https://github.com/example-org/histoseg",
        "licence": "Apache-2.0",
    },
    "he_wsi",
    "docs/usage.md:3",
    [
        {
            "key": "normalised_slide",
            "title": "Stain-normalised slide",
            "description": "The slide after stain normalisation (pyramidal OME-TIFF).",
            "category": "images",
            "formats": ["ome-tiff"],
            "scopes": ["sample"],
            "entity_types": ["file"],
            "path_patterns": [r"^normalised/{sample}\.normalised\.ome\.tiff$"],
        },
        {
            "key": "nuclear_masks",
            "title": "Nuclear label masks",
            "description": "One label per segmented nucleus, aligned to the slide.",
            "category": "segmentation",
            "formats": ["ome-tiff"],
            "scopes": ["sample"],
            "entity_types": ["file"],
            "path_patterns": [r"^masks/{sample}\.nuclei\.ome\.tiff$"],
        },
        {
            "key": "nuclear_features",
            "title": "Per-nucleus morphology",
            "description": "Area, shape and stain intensity per nucleus.",
            "category": "features",
            "formats": ["parquet"],
            "scopes": ["sample"],
            "entity_types": ["file"],
            "path_patterns": [r"^features/{sample}\.nuclei\.parquet$"],
        },
        {
            "key": "slide_report",
            "title": "Slide report",
            "description": "Summary of every slide's segmentation.",
            "category": "report",
            "formats": ["html"],
            "scopes": ["job"],
            "entity_types": ["file"],
            "path_patterns": [r"^report/slide_report\.html$"],
        },
    ],
    [
        {"parameter": "input", "editable_by": ["user"]},
        {"parameter": "outdir", "editable_by": ["platform"]},
    ],
    foreign_words=("fastq", "rna", "gene", "aligner", "transcript"),
    groups=2,
    required=("input", "outdir"),
    enums={"normalisation": ["macenko", "vahadane", "none"]},
)
METHYLATION = Journey(
    "methylation-wgbs-0.3.0",
    {
        "name": "example-org/methylseq-lite",
        "version": "2.1.0",
        "repository_url": "https://github.com/example-org/methylseq-lite",
        "licence": "MIT",
    },
    "wgbs",
    "docs/usage.md:3",
    [
        {
            "key": "bisulfite_alignments",
            "title": "Bisulfite alignments",
            "description": "Bismark alignments; final when deduplication is skipped.",
            "category": "alignment",
            "formats": ["bam"],
            "scopes": ["sample"],
            "entity_types": ["file"],
            "path_patterns": [r"^alignments/{sample}\.bismark\.bam$"],
        },
        {
            "key": "deduplicated_alignments",
            "title": "Deduplicated bisulfite alignments",
            "description": "Bismark alignments after PCR-duplicate removal.",
            "category": "alignment",
            "formats": ["bam"],
            "scopes": ["sample"],
            "entity_types": ["file"],
            "path_patterns": [r"^deduplicated/{sample}\.deduplicated\.bam$"],
        },
        {
            "key": "methylation_calls",
            "title": "Cytosine methylation calls",
            "description": "Methylation level per cytosine in the chosen context.",
            "category": "methylation",
            "formats": ["bedgraph"],
            "scopes": ["sample"],
            "entity_types": ["file"],
            "path_patterns": [r"^methylation/{sample}_{any}\.bedGraph$"],
        },
        {
            "key": "methylation_summary",
            "title": "Methylation summary",
            "description": "Summary of methylation across samples.",
            "category": "report",
            "formats": ["html", "tsv"],
            "scopes": ["job"],
            "entity_types": ["file"],
            "path_patterns": [r"^summary/methylation_summary\.(html|tsv)$"],
        },
    ],
    [
        {"parameter": "input", "editable_by": ["user"]},
        {"parameter": "outdir", "editable_by": ["platform"]},
        {"parameter": "genome", "editable_by": ["platform"]},
    ],
    foreign_words=("rna", "gene", "transcript", "image"),
    required=("input", "outdir", "genome"),
    enums={"context": ["CpG", "CHG", "CHH"]},
    exclusions=[
        {
            "glob": "alignments/{meta.id}.bismark_report.txt",
            "kind": "false_positive",
            "reason": "conf/publish.config's saveAs publishes only the BAM files.",
        }
    ],
)


def _copy(tmp_path: Path, journey: Journey) -> Path:
    root = tmp_path / journey.fixture
    shutil.copytree(FIXTURES / journey.fixture / "repository", root)
    return root


def _run(*arguments: str) -> str:
    result = runner.invoke(app, ["--user", "Ada", *arguments])
    assert result.exit_code == 0, result.output
    return result.output


def _data(root: Path, layer: str) -> dict[str, Any]:
    state = read_layer(root, layer)
    assert state.draft is not None, state.error
    data: dict[str, Any] = state.draft.data
    return data


@pytest.mark.parametrize("journey", [HISTOLOGY, METHYLATION], ids=lambda j: j.fixture)
def test_the_same_journey_authors_and_publishes_any_domain(
    tmp_path: Path, journey: Journey
) -> None:
    root = _copy(tmp_path, journey)
    _run("init", "--in-place", "--repository", str(root))

    # Exact, declared metadata only; nothing scientific inferred.
    pipeline = _data(root, "bundle")["pipeline"]
    for key, value in journey.identity.items():
        assert pipeline[key] == value, key
    assert pipeline["assay_capabilities"] == []
    outputs = _data(root, "outputs")
    assert outputs["outputs"] == []
    assert outputs["contract"]["schema_version"] is None

    # The input contract keeps what the schema declares.
    inputs = _data(root, "inputs")
    parameters = {item.name: item.schema for item in iter_parameters(inputs)}
    assert len(inputs.get("$defs") or {}) == journey.groups
    for name, values in journey.enums.items():
        assert parameters[name]["enum"] == values
    required = set(inputs.get("required") or [])
    for group in (inputs.get("$defs") or {}).values():
        required.update(group.get("required") or [])
    assert required == set(journey.required)
    assert all(
        schema["x-splice-access"]["editable_by"] == [] for schema in parameters.values()
    )

    # Routes are evidence, named as the code names them.
    coverage = route_coverage(root)
    assert coverage.routes and coverage.covered == 0
    routes = _run("draft", "routes", "--repository", str(root))
    assert "{sample}" not in routes

    # A person decides the science and the policy.
    _run(
        "configure", "identity", "--repository", str(root),
        "--add-assay", journey.assay, "--assay-evidence", "documented",
        "--assay-source", journey.assay_source,
        "--assay-rationale", "The usage guide states what the pipeline processes.",
    )  # fmt: skip
    catalogue = tmp_path / "outputs.yaml"
    catalogue.write_text(yaml.safe_dump(journey.outputs), encoding="utf-8")
    access = tmp_path / "access.json"
    access.write_text(json.dumps(journey.access), encoding="utf-8")
    _run(
        "configure", "outputs", "--repository", str(root),
        "--contract-version", "1.0.0", "--add-output", str(catalogue),
    )  # fmt: skip
    _run(
        "configure", "inputs", "--repository", str(root), "--decision-file", str(access)
    )
    _run(
        "configure", "execution-profiles", "--repository", str(root),
        "--set", "default.type=production",
        "--set", "default.container_engine=docker",
        "--set", "default.description=Default execution.", "--default", "default",
    )  # fmt: skip
    _run("configure", "components", "--repository", str(root),
         "--require-downloadable", "false")  # fmt: skip
    if journey.exclusions:
        from layer_fixtures import edit_draft_file

        edit_draft_file(
            root,
            "outputs",
            lambda data: data.update(excluded_routes=list(journey.exclusions)),
        )
    # A release date is the person's fact; nf-splice never guesses it.
    _run("configure", "identity", "--repository", str(root),
         "--set", "released_at=2026-10-01T09:00:00Z")  # fmt: skip
    _run("configure", "provenance", "--repository", str(root),
         "--strategy", "regenerate")  # fmt: skip

    for layer in ("bundle", "inputs", "outputs", "components", "execution-profiles"):
        validation = _run("draft", "validate", layer, "--repository", str(root))
        assert ": ready" in validation.splitlines()[0], validation
    built = _run("build", "all", "--repository", str(root))
    assert "Built" in built
    report = _run("validate", "--repository", str(root))
    assert "structurally valid, scientifically classified, ready for ingestion." in (
        report
    ), report
    assert "output coverage: ready" in report

    # No vocabulary from another domain was injected into the drafts.
    drafts = " ".join(
        path.read_text(encoding="utf-8").lower()
        for path in (root / ".splice-local" / "drafts").glob("*.yaml")
        if path.name != "provenance.draft.yaml"
    )
    for word in journey.foreign_words:
        assert not re.search(rf"\b{word}\b", drafts), word


def test_an_ambiguous_pipeline_gets_no_assay_and_no_outputs(tmp_path: Path) -> None:
    root = tmp_path / "ambiguous"
    shutil.copytree(FIXTURES / "ambiguous-reads-0.3.0" / "repository", root)
    _run("init", "--in-place", "--repository", str(root))
    pipeline = _data(root, "bundle")["pipeline"]
    assert pipeline["assay_capabilities"] == []
    # The description is the declared metadata key, never the README prose.
    assert pipeline["description"] == (
        "Aligns reads to a reference and counts them per annotated feature."
    )
    assert _data(root, "outputs")["outputs"] == []
    result = runner.invoke(
        app, ["--user", "Ada", "draft", "validate", "bundle", "--repository", str(root)]
    )
    assert result.exit_code == 2
    assert "missing_assay_classification" in result.output


@pytest.mark.asyncio
@pytest.mark.parametrize("journey", [HISTOLOGY, METHYLATION], ids=lambda j: j.fixture)
async def test_every_workspace_page_opens_for_any_domain(
    tmp_path: Path, journey: Journey
) -> None:
    root = _copy(tmp_path, journey)
    _run("init", "--in-place", "--repository", str(root))
    workspace = NfSpliceApp(root, user="Ada", start="overview")
    async with workspace.run_test(size=(100, 32)) as pilot:
        await settle(workspace, pilot)
        for page_id in PAGE_IDS:
            workspace.show_page(page_id)
            await settle(workspace, pilot)
            assert page_text(workspace)
        screenshot(workspace, f"{journey.fixture}-review")
