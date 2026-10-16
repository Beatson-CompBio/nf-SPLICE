"""Shared builders for file-first layer tests."""

from __future__ import annotations

from pathlib import Path

from nf_splice.domain import Actor
from nf_splice.layers import ChangeContext
from nf_splice.layers.bundle import seed_bundle_draft, validate_bundle_draft

ADA = ChangeContext(actor=Actor(label="Ada"))
IDENTITY = {
    "id": "rnaquant",
    "name": "rnaquant",
    "version": "1.2.0",
    "repository_url": "https://github.com/org/rnaquant",
    "description": "Quantifies RNA-seq reads.",
}


def ready_identity(root: Path) -> None:
    """Create an explicitly authored, ready bundle.draft.yaml."""
    seed_bundle_draft(root, explicit=IDENTITY)
    from nf_splice.layers.bundle import add_assay_capability

    add_assay_capability(
        root,
        "polya_rnaseq",
        ADA,
        evidence="asserted",
        rationale="The rnaquant developers process poly(A)-selected libraries.",
    )
    validation = validate_bundle_draft(root)
    assert validation.ready, validation.issues


SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$defs": {
        "analysis": {
            "title": "Analysis",
            "type": "object",
            "required": ["threshold"],
            "properties": {
                "threshold": {
                    "type": "number",
                    "description": "Analysis threshold.",
                    "default": 0.8,
                },
                "outdir": {"type": "string", "description": "Output directory."},
            },
        }
    },
    "allOf": [{"$ref": "#/$defs/analysis"}],
}


def write_pipeline(root: Path) -> None:
    """Write a compact but realistic Nextflow pipeline repository."""
    import json

    (root / "main.nf").write_text(
        'process REPORT {\n    publishDir "${params.outdir}/reports"\n    output:\n'
        '    path "report.html", emit: report\n}\n\nworkflow { REPORT() }\n',
        encoding="utf-8",
    )
    (root / "nextflow_schema.json").write_text(json.dumps(SCHEMA), encoding="utf-8")
    module = root / "modules" / "local" / "tool"
    module.mkdir(parents=True)
    (module / "meta.yml").write_text("name: tool\n", encoding="utf-8")
    (module / "main.nf").write_text(
        "process TOOL {\n    container 'quay.io/example/tool:1.0'\n\n    input:\n}\n",
        encoding="utf-8",
    )
    (root / "modules.json").write_text(
        json.dumps(
            {
                "items": [
                    {"kind": "module", "path": "modules/local/tool", "tool": "tool"}
                ]
            }
        ),
        encoding="utf-8",
    )
    (root / "conf").mkdir()
    (root / "conf" / "local.config").write_bytes(
        b"process { executor = 'local' }\r\nsingularity.enabled = true\r\n"
    )
    (root / "nextflow.config").write_text(
        "profiles { local { includeConfig 'conf/local.config' } }\n", encoding="utf-8"
    )


def ready_repository(root: Path) -> None:
    """Author every layer to readiness through the shared services."""
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
    from nf_splice.layers.outputs import accept_output, discover_outputs
    from nf_splice.layers.provenance import generate_minimal

    write_pipeline(root)
    ready_identity(root)
    import_inputs(root)
    set_access(root, ["threshold"], ["user", "agent"], ADA)
    set_access(root, ["outdir"], ["platform"], ADA)
    discovery = discover_outputs(root, schema_version="1.0.0")
    for candidate in discovery.pending:
        if candidate.suggested_key == "report":
            accept_output(
                root,
                candidate.id,
                {
                    "key": "report",
                    "title": "Report",
                    "description": "Job report.",
                    "category": "job_report",
                    "formats": ["html"],
                    "scopes": ["job"],
                    "entity_types": ["file"],
                    "path_patterns": [r"^reports/report\.html$"],
                },
                ADA,
            )
        else:
            from nf_splice.layers.outputs import reject_output

            reject_output(root, candidate.id, "Not a platform output", ADA)
    discover_components(root)
    accept_unambiguous_components(root, ADA)
    set_image_policy(root, False, ADA)
    discover_execution(root)
    review_profile(
        root,
        "profile:local",
        ADA,
        profile_type="development",
        description="Local development.",
        executor="local",
        container_engine="singularity",
        config_source="conf/local.config",
    )
    set_default_profile(root, "profile-local-6c6f63616c", ADA)
    generate_minimal(root, ADA, at="2026-10-15T10:00:00Z")


def write_root_crate(root: Path, name: str, version: str) -> None:
    """A current, standards-compliant repository-root RO-Crate."""
    import json

    crate = {
        "@context": "https://w3id.org/ro/crate/1.1/context",
        "@graph": [
            {
                "@id": "ro-crate-metadata.json",
                "@type": "CreativeWork",
                "about": {"@id": "./"},
                "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"},
            },
            {
                "@id": "./",
                "@type": "Dataset",
                "name": name,
                "version": version,
                "mainEntity": {"@id": "main.nf"},
            },
            {
                "@id": "main.nf",
                "@type": ["File", "SoftwareSourceCode", "ComputationalWorkflow"],
                "name": name,
                "version": version,
            },
        ],
    }
    (root / "ro-crate-metadata.json").write_text(
        json.dumps(crate, indent=2) + "\n", encoding="utf-8"
    )
