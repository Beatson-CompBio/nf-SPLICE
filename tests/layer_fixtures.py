"""Shared builders for file-first layer tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

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
    "licence": "MIT",
    "released_at": "2026-10-15T10:00:00Z",
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


def edit_draft_file(root: Path, layer: str, mutate: Any) -> None:
    """Edit a draft as a person would in an editor: read, change, save.

    No nf-splice service is involved, so nothing is confirmed or approved;
    the next validation reads the file from disk.
    """
    from nf_splice.drafts import dump_yaml_data, load_yaml_draft
    from nf_splice.layers.base import layer_spec

    path = root / layer_spec(layer).draft
    data = load_yaml_draft(path.read_text(encoding="utf-8")).data
    mutate(data)
    path.write_text(dump_yaml_data(data), encoding="utf-8")


REPORT_OUTPUT = {
    "key": "report",
    "title": "Report",
    "description": "Job report.",
    "category": "job_report",
    "formats": ["html"],
    "scopes": ["job"],
    "entity_types": ["file"],
    "path_patterns": [r"^reports/report\.html$"],
}
LOCAL_PROFILE = {
    "id": "local",
    "name": "Local",
    "description": "Local development.",
    "type": "development",
    "engine": "nextflow",
    "executor": "local",
    "container_engine": "singularity",
    "config": {"adopt": "conf/local.config"},
}


def ready_repository(root: Path) -> None:
    """Initialise, then author every draft directly (no candidate decisions)."""
    from nf_splice.layers.execution import CONFIGS_DIR
    from nf_splice.services.workspace import initialise

    write_pipeline(root)
    ready_identity(root)
    initialise(root, ADA, contract_version="1.0.0")

    def inputs(data: dict[str, Any]) -> None:
        group = data["$defs"]["analysis"]["properties"]
        group["threshold"]["x-splice-access"] = {"editable_by": ["agent", "user"]}
        group["threshold"]["x-splice-ui"] = {"visibility": "standard"}
        group["outdir"]["x-splice-access"] = {"editable_by": ["platform"]}

    def outputs(data: dict[str, Any]) -> None:
        data["outputs"] = [dict(REPORT_OUTPUT)]
        data["categories"] = {}

    def components(data: dict[str, Any]) -> None:
        data["require_downloadable_images"] = False

    def profiles(data: dict[str, Any]) -> None:
        data["profiles"] = [dict(LOCAL_PROFILE)]
        data["default_profile"] = "local"

    edit_draft_file(root, "inputs", inputs)
    edit_draft_file(root, "outputs", outputs)
    edit_draft_file(root, "components", components)
    edit_draft_file(root, "execution-profiles", profiles)
    (root / CONFIGS_DIR / "default.draft.config").unlink()


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
                "description": f"The {name} pipeline.",
                "license": "MIT",
                "datePublished": "2026-10-15",
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


def review_turn(stage: str, purpose: str = "plan") -> dict[str, Any]:
    """A scripted review turn: inspect a source file, then complete the review.

    Orchestration only; it proves the engine records and requires reviews,
    not that any model reasoned about the pipeline.
    """
    return {
        "stage": stage,
        "purpose": purpose,
        "steps": [
            {"tool": "read_source", "arguments": {"path": "main.nf"}},
            {
                "tool": "complete_review",
                "arguments": {
                    "summary": f"The {stage} draft matches the pipeline.",
                    "checked": ["main.nf"],
                },
            },
        ],
    }


def review_turns(*stages: str, purpose: str = "plan") -> list[dict[str, Any]]:
    return [review_turn(stage, purpose) for stage in stages]
