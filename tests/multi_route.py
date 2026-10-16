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
}
ACCESS = {
    "input": ["user"],
    "outdir": ["platform"],
    "aligner": ["user"],
    "skip_qc": ["user"],
    "run_salmon": ["user"],
    "publish_dir_mode": ["platform"],
}
#: Reviewed meaning for each discovered candidate key.
OUTPUTS: dict[str, dict[str, Any]] = {
    "html": {
        "key": "fastqc_report",
        "title": "FastQC report",
        "description": "Read quality report per sample.",
        "category": "quality_control",
        "formats": ["html"],
        "scopes": ["sample"],
    },
    "zip": {
        "key": "fastqc_archive",
        "title": "FastQC archive",
        "description": "Read quality data per sample.",
        "category": "quality_control",
        "formats": ["zip"],
        "scopes": ["sample"],
    },
    "star_align_bam": {
        "key": "star_alignment",
        "title": "STAR alignment",
        "description": "Coordinate-sorted STAR alignment per sample.",
        "category": "alignment",
        "formats": ["bam"],
        "scopes": ["sample"],
    },
    "log_final": {
        "key": "star_log",
        "title": "STAR log",
        "description": "STAR alignment summary per sample.",
        "category": "alignment_qc",
        "formats": ["txt"],
        "scopes": ["sample"],
    },
    "hisat2_align_bam": {
        "key": "hisat2_alignment",
        "title": "HISAT2 alignment",
        "description": "HISAT2 alignment per sample.",
        "category": "alignment",
        "formats": ["bam"],
        "scopes": ["sample"],
    },
    "quant": {
        "key": "salmon_quantification",
        "title": "Salmon quantification",
        "description": "Transcript quantification per sample.",
        "category": "quantification",
        "formats": ["tsv"],
        "scopes": ["sample"],
    },
    "report": {
        "key": "multiqc_report",
        "title": "MultiQC report",
        "description": "Aggregate quality-control report.",
        "category": "quality_control",
        "formats": ["html"],
        "scopes": ["job"],
    },
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
    return base | {
        "entity_types": ["file"],
        "path_patterns": [candidate.path_pattern],
    }


def author_all(root: Path, context: ChangeContext = ADA) -> None:
    """Review every layer of the fixture to readiness."""
    from nf_splice.layers.bundle import seed_bundle_draft
    from nf_splice.layers.components import (
        accept_unambiguous_components,
        discover_components,
        set_image_policy,
    )
    from nf_splice.layers.execution import (
        discover_execution,
        review_profile,
        set_default_profile,
    )
    from nf_splice.layers.inputs import import_inputs, set_access
    from nf_splice.layers.outputs import accept_output, discover_outputs, reject_output
    from nf_splice.layers.provenance import generate_minimal

    seed_bundle_draft(root, explicit=IDENTITY)
    set_identity_fields(root, {}, context)
    from nf_splice.layers.bundle import add_assay_capability

    for code in ("polya_rnaseq", "total_rnaseq"):
        add_assay_capability(
            root,
            code,
            context,
            evidence="asserted",
            rationale="The pipeline aligns poly(A)-selected and total RNA libraries.",
        )
    import_inputs(root)
    for name, principals in ACCESS.items():
        set_access(root, [name], principals, context)
    discovery = discover_outputs(root, schema_version="1.0.0")
    for candidate in discovery.pending:
        output = reviewed_output(candidate)
        if output is None:
            reject_output(root, candidate.id, "Not a platform output", context)
        else:
            accept_output(root, candidate.id, output, context)
    discover_components(root)
    accept_unambiguous_components(root, context)
    set_image_policy(root, False, context)
    discover_execution(root)
    review_profile(
        root,
        "profile:local",
        context,
        profile_type="development",
        description="Local development.",
        executor="local",
        container_engine="singularity",
        config_source="conf/local.config",
    )
    from nf_splice.layers.execution import pending_profiles, profile_id

    assert not pending_profiles(root)
    set_default_profile(root, profile_id("local"), context)
    generate_minimal(root, context, at="2026-10-15T10:00:00Z")


def build(root: Path, context: ChangeContext = ADA) -> None:
    from nf_splice.services.lifecycle import promote, validate_bundle

    promote(root, None, context)
    report = validate_bundle(root)
    assert report.valid, [item.to_json() for item in report.issues]
