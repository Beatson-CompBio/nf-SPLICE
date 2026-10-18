"""Shared authoring of the multi-route fixture through the real services."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from layer_fixtures import ADA
from nf_splice.layers import ChangeContext
from nf_splice.layers.bundle import set_identity_fields

FIXTURE = Path(__file__).parent / "fixtures" / "multi-route-0.3.0"
EXAMPLE = FIXTURE / "example-star"
IDENTITY = {
    "id": "multiroute",
    "name": "multiroute",
    "version": "1.0.0",
    "repository_url": "https://github.com/org/multiroute",
    "description": "Aligns RNA-seq reads with STAR or HISAT2.",
    "licence": "MIT",
    "released_at": "2026-10-15T10:00:00Z",
}
ACCESS = {
    "input": ["user"],
    "outdir": ["platform"],
    "aligner": ["user"],
    "skip_qc": ["user"],
    "run_salmon": ["user"],
    "publish_dir_mode": ["platform"],
}
#: Reviewed meaning for each published route, by the route's emit name.
OUTPUTS: dict[str, dict[str, Any]] = {
    "html": {
        "key": "fastqc_report",
        "title": "FastQC report",
        "description": "Read quality report per sample.",
        "category": "quality_control",
        "formats": ["html"],
        "scopes": ["sample"],
        "path_patterns": [r"^fastqc/(?P<sample_id>[^/]+)_fastqc\.html$"],
    },
    "zip": {
        "key": "fastqc_archive",
        "title": "FastQC archive",
        "description": "Read quality data per sample.",
        "category": "quality_control",
        "formats": ["zip"],
        "scopes": ["sample"],
        "path_patterns": [r"^fastqc/(?P<sample_id>[^/]+)_fastqc\.zip$"],
    },
    "star_align_bam": {
        "key": "star_alignment",
        "title": "STAR alignment",
        "description": "Coordinate-sorted STAR alignment per sample.",
        "category": "alignment",
        "formats": ["bam"],
        "scopes": ["sample"],
        "path_patterns": [
            r"^star/(?P<sample_id>[^/]+)\.Aligned\.sortedByCoord\.out\.bam$"
        ],
    },
    "log_final": {
        "key": "star_log",
        "title": "STAR log",
        "description": "STAR alignment summary per sample.",
        "category": "alignment_qc",
        "formats": ["txt"],
        "scopes": ["sample"],
        "path_patterns": [r"^star/(?P<sample_id>[^/]+)\.Log\.final\.out$"],
    },
    "hisat2_align_bam": {
        "key": "hisat2_alignment",
        "title": "HISAT2 alignment",
        "description": "HISAT2 alignment per sample.",
        "category": "alignment",
        "formats": ["bam"],
        "scopes": ["sample"],
        "path_patterns": [r"^hisat2/(?P<sample_id>[^/]+)\.bam$"],
    },
    "quant": {
        "key": "salmon_quantification",
        "title": "Salmon quantification",
        "description": "Transcript quantification per sample.",
        "category": "quantification",
        "formats": ["tsv"],
        "scopes": ["sample"],
        "path_patterns": [r"^salmon/(?P<sample_id>[^/]+)/quant\.sf$"],
    },
    "report": {
        "key": "multiqc_report",
        "title": "MultiQC report",
        "description": "Aggregate quality-control report.",
        "category": "quality_control",
        "formats": ["html"],
        "scopes": ["job"],
        "path_patterns": [r"^multiqc/multiqc_report\.html$"],
    },
}

#: Assays the fixture's documentation names, by registered code.
ASSAYS = {"polya_rnaseq": "poly(A) RNA-seq", "total_rnaseq": "Total RNA-seq"}
#: Published path globs of each route, as static analysis reports them.
GLOBS = {
    "html": ("fastqc/{sample}_fastqc.html",),
    "zip": ("fastqc/{sample}_fastqc.zip",),
    "hisat2_align_bam": ("hisat2/{sample}.bam",),
    "report": ("multiqc/multiqc_report.html",),
    "quant": ("salmon/{sample}/quant.sf",),
    "star_align_bam": ("star/{sample}.Aligned.sortedByCoord.out.bam",),
    "log_final": ("star/{sample}.Log.final.out",),
}


def copy_fixture(tmp_path: Path) -> Path:
    root = tmp_path / "multiroute"
    shutil.copytree(FIXTURE / "repository", root)
    return root


def reviewed_output(candidate: Any) -> dict[str, Any] | None:
    """The complete reviewed output for a candidate, or None to reject it."""
    base = OUTPUTS.get(candidate.suggested_key)
    if base is None or candidate.path_pattern is None:
        return None
    return base | {"entity_types": ["file"]}


def author_all(root: Path, context: ChangeContext = ADA) -> None:
    """Initialise the fixture, then author every draft directly.

    Only the assay capabilities go through a tool (they are resolved
    against the vocabulary); everything else is written into the files as a
    person would in an editor. No candidate is accepted or rejected.
    """
    from layer_fixtures import edit_draft_file
    from nf_splice.inspectors.outputs import discover_output_candidates
    from nf_splice.layers.bundle import add_assay_capability
    from nf_splice.layers.execution import CONFIGS_DIR
    from nf_splice.layers.inputs import iter_parameters
    from nf_splice.layers.provenance import generate_minimal
    from nf_splice.services.workspace import initialise

    initialise(root, context, identity=IDENTITY, contract_version="1.0.0")
    set_identity_fields(root, {}, context)
    for code in ("polya_rnaseq", "total_rnaseq"):
        add_assay_capability(
            root,
            code,
            context,
            evidence="asserted",
            rationale="The pipeline aligns poly(A)-selected and total RNA libraries.",
        )

    def inputs(data: dict[str, Any]) -> None:
        from nf_splice.drafts import resolve

        for parameter in iter_parameters(data):
            if parameter.name in ACCESS:
                target = resolve(data, parameter.pointer)
                target["x-splice-access"] = {"editable_by": ACCESS[parameter.name]}

    outputs: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    for item in discover_output_candidates(root):
        output = reviewed_output(item.candidate)
        if output is not None:
            if output["key"] not in {entry["key"] for entry in outputs}:
                outputs.append(output)
        else:
            for process in item.candidate.processes:
                if process not in {entry.get("process") for entry in excluded}:
                    excluded.append(
                        {"process": process, "reason": "Not a platform output"}
                    )

    def catalogue(data: dict[str, Any]) -> None:
        data["outputs"] = outputs
        data["categories"] = {}
        data["excluded_routes"] = excluded

    def components(data: dict[str, Any]) -> None:
        data["require_downloadable_images"] = False

    def profiles(data: dict[str, Any]) -> None:
        data["profiles"] = [
            {
                "id": "local",
                "name": "Local",
                "description": "Local development.",
                "type": "development",
                "engine": "nextflow",
                "executor": "local",
                "container_engine": "singularity",
                "config": {"adopt": "conf/local.config"},
            }
        ]
        data["default_profile"] = "local"

    edit_draft_file(root, "inputs", inputs)
    edit_draft_file(root, "outputs", catalogue)
    edit_draft_file(root, "components", components)
    edit_draft_file(root, "execution-profiles", profiles)
    (root / CONFIGS_DIR / "default.draft.config").unlink()
    generate_minimal(root, context, at="2026-10-15T10:00:00Z")


def build(root: Path, context: ChangeContext = ADA) -> None:
    from nf_splice.services.lifecycle import promote, validate_bundle

    promote(root, None, context)
    report = validate_bundle(root)
    assert report.valid, [item.to_json() for item in report.issues]
