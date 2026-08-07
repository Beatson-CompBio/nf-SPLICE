"""Deterministic SPLICE bundle entry point, documentation, and lock rendering."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass

from nf_splice import __version__
from nf_splice.domain import AuthoringDocument, DecisionStatus


class BundleRenderError(ValueError):
    """Raised when reviewed state cannot identify a complete bundle."""


@dataclass(frozen=True, slots=True)
class RenderedBundle:
    """Byte-stable top-level bundle artefacts."""

    bundle: bytes
    readme: bytes
    lock: bytes


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _pipeline_id(name: str) -> str:
    identifier = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not identifier:
        raise BundleRenderError("pipeline name cannot form a stable bundle id")
    return identifier


def _identity(document: AuthoringDocument) -> tuple[str, str, str]:
    missing = [
        field
        for field in ("name", "version", "repository_url")
        if getattr(document.pipeline, field) is None
    ]
    if missing:
        raise BundleRenderError(
            "reviewed pipeline identity is missing: " + ", ".join(missing)
        )
    return (
        str(document.pipeline.name),
        str(document.pipeline.version),
        str(document.pipeline.repository_url),
    )


def _bundle_document(document: AuthoringDocument) -> dict[str, object]:
    name, version, _repository_url = _identity(document)
    return {
        "bundle_format": "splice-pipeline-bundle",
        "schema_version": "1.0",
        "pipeline": {
            "id": _pipeline_id(name),
            "name": name,
            "version": version,
            "engine": "nextflow",
        },
        "files": {
            "inputs_schema": "inputs.schema.json",
            "outputs_catalogue": "outputs.yaml",
            "outputs_schema": "outputs.schema.json",
            "ro_crate": "ro-crate-metadata.json",
            "components": "components.json",
            "execution_profiles": "execution-profiles.json",
        },
    }


def _readme(document: AuthoringDocument, generated: Mapping[str, bytes]) -> str:
    name, _version, _repository_url = _identity(document)
    configs = sorted(path for path in generated if path.startswith("configs/"))
    rows = [
        ("bundle.json", "Static bundle entry point."),
        ("inputs.schema.json", "Reviewed platform-configurable inputs."),
        ("outputs.yaml", "Reviewed output catalogue."),
        ("outputs.schema.json", "Schema for per-run analysis_output.json."),
        ("ro-crate-metadata.json", "Developer-generated workflow RO-Crate."),
        ("components.json", "Reviewed software and container inventory."),
        ("execution-profiles.json", "Supported execution profile catalogue."),
        ("nf-splice.lock.json", "Generator, source, and content provenance."),
        *((path, "Reviewed execution configuration.") for path in configs),
    ]
    table = "\n".join(f"| `{path}` | {purpose} |" for path, purpose in rows)
    return (
        f"# {name} SPLICE pipeline bundle\n\n"
        "This directory is the static integration harness consumed by the SPLICE "
        "platform. It complements the pipeline's native Nextflow and nf-core files.\n\n"
        "## Contents\n\n"
        "| File | Purpose |\n| --- | --- |\n"
        f"{table}\n\n"
        "## Ownership\n\n"
        "`nf-splice.yaml` records reviewed developer decisions. Generated contracts "
        "must be changed by reviewing source evidence and rebuilding, not by editing "
        "materialised files directly. The root RO-Crate and selected source configs "
        "remain developer-owned and are copied unchanged.\n\n"
        "Run-specific results, reports, logs, and `analysis_output.json` belong in a "
        "completed run's output directory, not in this static bundle.\n"
    )


def _selected_evidence(document: AuthoringDocument) -> list[dict[str, object]]:
    selected_ids = {
        evidence_id
        for decision in document.decisions
        if decision.status is DecisionStatus.REVIEWED
        for evidence_id in decision.evidence_ids
    }
    return [
        {
            "id": item.id,
            "source": item.provenance.source,
            "location": item.provenance.location,
            "repository_revision": item.provenance.repository_revision,
            "confidence": item.confidence,
        }
        for item in sorted(document.evidence, key=lambda value: value.id)
        if item.id in selected_ids
    ]


def render_bundle(
    document: AuthoringDocument,
    *,
    repository_revision: str | None,
    generated_files: Mapping[str, bytes],
    source_files: Mapping[str, bytes],
) -> RenderedBundle:
    """Render bundle metadata around already-rendered reviewed layer payloads."""
    _name, _version, repository_url = _identity(document)
    bundle = (
        json.dumps(_bundle_document(document), indent=2, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    readme = _readme(document, generated_files).encode("utf-8")
    managed = dict(generated_files)
    managed["bundle.json"] = bundle
    managed["README.md"] = readme
    lock_document = {
        "schema_version": "1.0",
        "generator": {"name": "nf-splice", "version": __version__},
        "repository": {
            "url": repository_url,
            "revision": repository_revision,
        },
        "selected_evidence": _selected_evidence(document),
        "sources": {
            path: {"sha256": _sha256(payload)}
            for path, payload in sorted(source_files.items())
        },
        "managed_files": {
            path: {"sha256": _sha256(payload)}
            for path, payload in sorted(managed.items())
        },
    }
    lock = (json.dumps(lock_document, indent=2, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )
    return RenderedBundle(bundle=bundle, readme=readme, lock=lock)
