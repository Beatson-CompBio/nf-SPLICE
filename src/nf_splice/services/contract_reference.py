"""The complete authorable structure of each draft, for people and agents.

Generated from the same models and contracts the validators use, so an agent
editing a whole draft sees every field it may write (not a partial view), and
which values the build owns instead.
"""

from __future__ import annotations

import json
from typing import Any

from nf_splice.contracts import INPUTS_FAMILY, meta_schema
from nf_splice.domain import ReviewedOutput
from nf_splice.domain.components import ReviewedContainer
from nf_splice.domain.execution import (
    ContainerEngine,
    ExecutionExecutor,
    ExecutionProfileType,
)
from nf_splice.domain.identity import (
    PIPELINE_FIELD_ORDER,
    REQUIRED_PIPELINE_FIELDS,
    Maintainer,
    PipelineMetadata,
)
from nf_splice.layers.base import layer_spec

_COMMON = (
    "Keep the x-splice-draft block exactly as it is. Unknown values stay null "
    "or empty; never invent identifiers, checksums, URLs or scientific facts."
)


def _schema(model: Any) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(json.dumps(model.model_json_schema()))
    return loaded


def _bundle() -> dict[str, Any]:
    pipeline = _schema(PipelineMetadata)
    pipeline["properties"].pop("assay_capabilities", None)
    return {
        "draft_fields": {
            "pipeline": "the pipeline's identity and description (below)",
            "maintainers": "public contacts; published only when "
            "maintainers_publication_approved is true",
            "maintainers_publication_approved": "a person's consent; agents "
            "never set it",
        },
        "pipeline_field_order": list(PIPELINE_FIELD_ORDER),
        "required_for_ingestion": list(REQUIRED_PIPELINE_FIELDS),
        "pipeline_schema": pipeline,
        "maintainer_schema": _schema(Maintainer),
        "assay_capabilities": {
            "entry": {
                "code": "a registered assay code (polya_rnaseq), or",
                "entity_id": "a vocabulary assay entity id (ASSAY_METHOD or "
                "ASSAY_TYPE)",
                "evidence": "asserted (a person only) | confirmed (a person's "
                "answer) | documented | detected",
                "rationale": "one sentence: why the pipeline supports it",
                "sources": "path:line evidence (required except for asserted)",
            },
            "how": "change only with add_assay_capability / "
            "remove_assay_capability, which resolve entries against the "
            "vocabulary; search with search_assay_catalogue and show_assay",
        },
        "build_owned": [
            "generated_by",
            "contract identifiers and digests",
            "file index and lock",
            "assay labels, types and paths (resolved from the vocabulary)",
        ],
        "notes": _COMMON,
    }


def _inputs() -> dict[str, Any]:
    contract = meta_schema(INPUTS_FAMILY)
    definitions = contract.get("$defs", {})
    return {
        "document": "a JSON Schema 2020-12 document of job parameters (YAML "
        "form): $schema, $id, x-splice-contract, x-splice-pipeline, then the "
        "nf-schema structure ($defs groups, allOf, properties)",
        "parameter_extensions": definitions.get("parameter"),
        "access": {
            "editable_by": "who may change the value when a job is submitted: "
            "any of user, platform, agent; [] means nobody (a valid policy)",
            "runtime_agent": "'agent' is a runtime principal of the SPLICE "
            "platform, not the assistant authoring this draft; never grant it "
            "because an AI wrote the draft",
            "visibility": "x-splice-ui.visibility: standard | advanced | hidden "
            "(presentation only; never an authorisation)",
        },
        "build_owned": ["x-splice-contract", "x-splice-pipeline", "$id"],
        "notes": _COMMON
        + " Keep every declared parameter; never drop one because users should "
        "not see it.",
    }


def _outputs() -> dict[str, Any]:
    return {
        "draft_fields": {
            "contract": {
                "schema_version": "the per-pipeline analysis-output "
                "schema version, X.Y.Z"
            },
            "categories": "optional {category: {title, description}} for "
            "categories outputs use",
            "outputs": "the output catalogue: the union of outputs the pipeline "
            "may publish across all supported routes (entries below)",
            "excluded_routes": "draft-only: published routes deliberately left "
            "out, each {glob: <published glob> | process: <instance>, reason}",
        },
        "output_schema": _schema(ReviewedOutput),
        "placeholders": "path_patterns are regular expressions that must start "
        "with ^ and end with $, relative to the job's publish directory "
        "(^report/summary\\.html$). Placeholders: {sample} and {run} capture the "
        "owning unit; {any} matches one path segment and {anypath} any depth; "
        "{library}, {aligner}, {stage} and {read} are optional named labels",
        "excluded_route_globs": "an excluded_routes glob is copied exactly as "
        "route_coverage or analyse_routes shows it, {meta.id} included",
        "scopes": {
            "job": "belongs to one whole Nextflow job",
            "sample": "one biological sample (or its aggregate result); "
            "patterns capture {sample}",
            "run": "one platform file-level run of a sample; patterns capture {run}",
        },
        "notes": _COMMON
        + " Categories and stages are free labels. Do not list files that are "
        "only intermediates (declared but never published).",
    }


def _components() -> dict[str, Any]:
    return {
        "draft_fields": {
            "require_downloadable_images": "true when ingestion needs a "
            "verified downloadable image per container (deployment decision)",
            "containers": "logical images, each with per-runtime source_images",
            "components": "every module or inline process: id, type "
            "(workflow_module: path is the module directory; workflow_process: "
            "path is the .nf file and process the process name), name, "
            "namespace, tool {name, version}, evidence, container_id, "
            "conda_packages; draft-only 'unresolved' lists open problems",
        },
        "container_schema": _schema(ReviewedContainer),
        "distribution": "written only by `nf-splice containers verify` or the "
        "image workflow after downloading and hashing the real file; never "
        "enter a checksum or URL by hand",
        "notes": _COMMON
        + " Software version, conda build, OCI tag, image digest and module "
        "revision are different things.",
    }


def _profiles() -> dict[str, Any]:
    return {
        "draft_fields": {
            "default_profile": "the id of the single default profile",
            "profiles": "metadata and a config reference per profile",
        },
        "profile": {
            "id": "lower-case letters, digits, - and _, starting with a letter",
            "name": "display name",
            "description": "what the profile is for",
            "type": [item.value for item in ExecutionProfileType],
            "engine": "nextflow",
            "executor": [item.value for item in ExecutionExecutor],
            "container_engine": [item.value for item in ContainerEngine],
            "config": "{draft: <name>.draft.config} (a native file in "
            ".splice-local/drafts/configs/, edited with write_config) or "
            "{adopt: <repository .config>} (published unchanged)",
            "site_parameters": "optional [{name, description}] the deployment supplies",
        },
        "config_files": "complete Nextflow configuration; the '// ***** User "
        "Pipeline Input Params *****' and '// ***** SPLICE Pipeline Input "
        "Params *****' params sections hold user-editable and deployment "
        "values",
        "notes": _COMMON
        + " Never put configuration settings in the YAML; never write secrets, "
        "personal paths or literal accounts into a config.",
    }


def _provenance() -> dict[str, Any]:
    return {
        "draft_fields": {
            "origin": "adopted | generated | nf-core | authored (how the graph began)",
            "source": "{path, sha256} of the repository-root crate it was based "
            "on, or null",
            "crate": "the RO-Crate JSON-LD graph (@context, @graph); data-entity "
            "IDs relative to the pipeline directory",
        },
        "profiles": [
            "https://w3id.org/ro/crate/1.1",
            "https://w3id.org/workflowhub/workflow-ro-crate/1.0",
        ],
        "build_owned": ["the splice/ Dataset and its File entities (added on build)"],
        "notes": _COMMON
        + " Distinguish the scientific workflow's authors from the integration "
        "reviewer and from nf-splice; never invent an ORCID, licence or DOI.",
    }


_BUILDERS = {
    "bundle": _bundle,
    "inputs": _inputs,
    "outputs": _outputs,
    "components": _components,
    "execution-profiles": _profiles,
    "provenance": _provenance,
}


def authorable_contract(layer: str) -> dict[str, Any]:
    """The authorable structure of one layer's draft."""
    spec = layer_spec(layer)
    return {"layer": spec.name, "draft": spec.draft, **_BUILDERS[spec.name]()}
