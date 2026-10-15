"""Explicit, previewed, non-destructive migration of 0.1.0 authoring state.

The legacy ``splice/nf-splice.yaml`` (authoring schema 1.0) is read-only
migration input. Applying a migration creates only absent per-layer drafts
and review sidecars; the legacy file and every published file stay byte-for-
byte unchanged. Every transformed, defaulted, unmapped or blocked value is
reported, and permission mappings never widen access.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nf_splice.domain import (
    AuthoringDocument,
    DecisionStatus,
    load_authoring_document,
)
from nf_splice.domain.access import LEGACY_CLASSIFICATION_ACCESS
from nf_splice.domain.identity import derive_pipeline_id
from nf_splice.domain.inputs import InputClassification
from nf_splice.drafts import DRAFT_MARKER, dump_yaml_data, read_file, sha256
from nf_splice.drafts.patch import apply as apply_patch
from nf_splice.inspectors.containers import classify_reference
from nf_splice.layers.base import (
    LAYERS,
    ChangeContext,
    ReviewState,
    draft_marker,
    edit_draft,
    layer_spec,
    ops_for,
    read_layer,
    seed_draft,
    update_review_state,
)
from nf_splice.layers.bundle import seed_bundle_draft
from nf_splice.layers.components import container_id
from nf_splice.layers.execution import profile_id
from nf_splice.layers.inputs import (
    SOURCE as INPUT_SOURCE,
)
from nf_splice.layers.inputs import (
    import_inputs,
    iter_parameters,
    project_nextflow_schema,
)

LEGACY_STATE = "splice/nf-splice.yaml"
_REVIEWED = DecisionStatus.REVIEWED


class MigrationError(ValueError):
    """Raised when a legacy state cannot be migrated safely."""


@dataclass(frozen=True, slots=True)
class MigrationNote:
    """One reported transformation, default, unmapped value or blocker."""

    layer: str
    pointer: str
    kind: str
    message: str

    def to_json(self) -> dict[str, str]:
        return {
            "layer": self.layer,
            "pointer": self.pointer,
            "kind": self.kind,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class MigrationPlan:
    """Read-only migration preview."""

    source_sha256: str
    drafts: Mapping[str, str]
    notes: tuple[MigrationNote, ...]
    existing: tuple[str, ...] = field(default=())

    def to_json(self) -> dict[str, Any]:
        return {
            "source": LEGACY_STATE,
            "source_sha256": self.source_sha256,
            "drafts": sorted(self.drafts),
            "existing_drafts_preserved": list(self.existing),
            "notes": [item.to_json() for item in self.notes],
        }


def _legacy(root: Path) -> tuple[AuthoringDocument, str]:
    state = read_file(root, LEGACY_STATE)
    if state.payload is None:
        raise MigrationError(f"{LEGACY_STATE} does not exist")
    try:
        return load_authoring_document(state.payload.decode("utf-8")), str(state.sha256)
    except ValueError as error:
        raise MigrationError(f"{LEGACY_STATE} cannot be migrated: {error}") from error


def _reviewed(document: AuthoringDocument, layer: str) -> list[tuple[str, Any]]:
    item = next((entry for entry in document.layers if entry.name == layer), None)
    if item is None:
        return []
    decisions = {entry.id: entry for entry in document.decisions}
    return [
        (decision_id, decisions[decision_id].value)
        for decision_id in item.decision_ids
        if decisions[decision_id].status is _REVIEWED
    ]


def _rejected(document: AuthoringDocument, layer: str) -> list[tuple[str, Any, str]]:
    item = next((entry for entry in document.layers if entry.name == layer), None)
    if item is None:
        return []
    decisions = {entry.id: entry for entry in document.decisions}
    return [
        (decision_id, decisions[decision_id].value, str(decisions[decision_id].reason))
        for decision_id in item.decision_ids
        if decisions[decision_id].status is DecisionStatus.REJECTED
    ]


def _identity(
    document: AuthoringDocument,
) -> tuple[dict[str, Any], list[MigrationNote]]:
    pipeline = document.pipeline
    explicit = {
        key: value
        for key, value in {
            "name": pipeline.name,
            "version": pipeline.version,
            "repository_url": pipeline.repository_url,
            "release_url": pipeline.release_url,
        }.items()
        if value is not None
    }
    notes = []
    if pipeline.name:
        explicit["id"] = derive_pipeline_id(pipeline.name)
        notes.append(
            MigrationNote(
                "bundle",
                "/pipeline/id",
                "transformed",
                f"id {explicit['id']!r} fixed from the 0.1.0 name-derived bundle id",
            )
        )
    notes.append(
        MigrationNote(
            "bundle",
            "/pipeline",
            "default",
            "new 0.3.0 identity fields (description, authors, funders, citation, "
            "licence, minimum Nextflow version) are seeded from evidence and need "
            "review",
        )
    )
    return explicit, notes


def _input_changes(
    document: AuthoringDocument, schema: Mapping[str, Any]
) -> tuple[dict[str, dict[str, Any]], list[MigrationNote]]:
    by_name = {item.name: item for item in iter_parameters(schema)}
    changes: dict[str, dict[str, Any]] = {}
    notes = []
    for _decision, value in _reviewed(document, "inputs"):
        name = str(value["name"])
        classification = InputClassification(value["classification"])
        principals, visibility = LEGACY_CLASSIFICATION_ACCESS[classification]
        parameter = by_name.get(name)
        if parameter is None:
            notes.append(
                MigrationNote(
                    "inputs",
                    f"/{name}",
                    "unmapped",
                    f"legacy parameter {name!r} is no longer in {INPUT_SOURCE}",
                )
            )
            continue
        update: dict[str, Any] = {
            "x-splice-access": {
                "editable_by": sorted(item.value for item in principals)
            }
        }
        if visibility is not None:
            update["x-splice-ui"] = {"visibility": visibility.value}
        fragment = value.get("schema_fragment") or {}
        for key in ("type", "description"):
            if key in fragment and fragment[key] != parameter.schema.get(key):
                update[key] = fragment[key]
                notes.append(
                    MigrationNote(
                        "inputs",
                        f"{parameter.pointer}/{key}",
                        "transformed",
                        f"reviewed 0.1.0 {key} override retained",
                    )
                )
        changes[parameter.pointer] = update
        notes.append(
            MigrationNote(
                "inputs",
                f"{parameter.pointer}/x-splice-access",
                "permission",
                f"{classification.value} -> editable_by "
                f"{sorted(item.value for item in principals)} (never widened)",
            )
        )
    for name, parameter in sorted(by_name.items()):
        if parameter.pointer not in changes:
            notes.append(
                MigrationNote(
                    "inputs",
                    f"{parameter.pointer}/x-splice-access",
                    "blocker",
                    f"{name!r} had no reviewed 0.1.0 classification",
                )
            )
    return changes, notes


_LEGACY_SCOPE = {"run": "job", "sample": "sample"}


def _outputs(
    document: AuthoringDocument, *, map_library_to_run: bool
) -> tuple[dict[str, Any], dict[str, Any], list[MigrationNote]]:
    outputs = []
    notes = []
    for index, (_decision, value) in enumerate(
        sorted(_reviewed(document, "outputs"), key=lambda item: str(item[1].get("key")))
    ):
        output = dict(value)
        pointer = f"/outputs/{index}"
        scopes = []
        for scope in output.get("scopes", []):
            if scope in _LEGACY_SCOPE:
                scopes.append(_LEGACY_SCOPE[scope])
                if scope == "run":
                    notes.append(
                        MigrationNote(
                            "outputs",
                            f"{pointer}/scopes",
                            "transformed",
                            "legacy workflow-wide scope 'run' -> 'job' (source "
                            "authoring schema 1.0)",
                        )
                    )
            elif scope == "library" and map_library_to_run:
                scopes.append("run")
                output["path_patterns"] = [
                    item.replace("{library}", "{run}")
                    for item in output["path_patterns"]
                ]
                notes.append(
                    MigrationNote(
                        "outputs",
                        f"{pointer}/scopes",
                        "transformed",
                        "legacy 'library' -> platform 'run' by explicit reviewed "
                        "mapping (library identifiers are platform run identifiers)",
                    )
                )
            elif scope == "library":
                notes.append(
                    MigrationNote(
                        "outputs",
                        f"{pointer}/scopes",
                        "blocker",
                        f"{output['key']!r} used legacy 'library' scope; map it to a "
                        "platform run only with a reviewed file-level identifier "
                        "(--map-library-to-run) or choose another scope",
                    )
                )
        output["scopes"] = sorted(set(scopes), key=["job", "sample", "run"].index)
        if output.get("category") == "run_report":
            output["category"] = "job_report"
            notes.append(
                MigrationNote(
                    "outputs",
                    f"{pointer}/category",
                    "transformed",
                    "legacy category 'run_report' -> suggested 'job_report'",
                )
            )
        if not output.get("labels"):
            output.pop("labels", None)
        if output.get("stage") is None:
            output.pop("stage", None)
        outputs.append(output)
    version = (
        document.output_contract.schema_version if document.output_contract else None
    )
    if version is None:
        notes.append(
            MigrationNote(
                "outputs",
                "/contract/schema_version",
                "blocker",
                "no reviewed output-contract version in 0.1.0 state",
            )
        )
    candidates = {
        decision: {"status": "rejected", "reason": reason, "candidate": value}
        for decision, value, reason in _rejected(document, "outputs")
    }
    draft = {
        "contract": {"schema_version": version},
        "categories": {},
        "outputs": outputs,
    }
    return draft, candidates, notes


def _components(
    document: AuthoringDocument,
) -> tuple[dict[str, Any], list[MigrationNote]]:
    containers: dict[str, dict[str, Any]] = {}
    components = []
    notes = []
    for _decision, value in sorted(
        _reviewed(document, "components"), key=lambda item: str(item[1].get("id"))
    ):
        uri = value.get("container_uri")
        component: dict[str, Any] = {
            "id": str(value["id"]).removeprefix("component:"),
            "type": "workflow_module",
            "name": value["name"],
            "path": value["path"],
            "namespace": value["namespace"],
            "tool": {"name": value["tool_name"]}
            | ({"version": value["version"]} if value.get("version") else {}),
            "evidence": list(value.get("evidence_locations") or []),
        }
        if value.get("conda_packages"):
            component["conda_packages"] = list(value["conda_packages"])
        if uri:
            identifier = container_id(uri)
            kind = classify_reference(uri)
            runtime = (
                "singularity"
                if kind.value in {"https_image", "oras", "local_image"}
                else "docker"
            )
            containers.setdefault(
                identifier,
                {
                    "id": identifier,
                    "source_images": {runtime: uri},
                    "distribution": None,
                },
            )
            component["container_id"] = identifier
            notes.append(
                MigrationNote(
                    "components",
                    f"/containers/{identifier}",
                    "review",
                    f"0.1.0 inferred the container type of {uri!r} heuristically; "
                    f"recorded as a {runtime} source with the same id; any "
                    "downloadable image must be verified",
                )
            )
        components.append(component)
    notes.append(
        MigrationNote(
            "components",
            "/require_downloadable_images",
            "blocker",
            "decide whether ingestion requires verified downloadable images",
        )
    )
    return (
        {
            "require_downloadable_images": None,
            "containers": list(containers.values()),
            "components": components,
        },
        notes,
    )


def _execution(
    document: AuthoringDocument,
) -> tuple[dict[str, Any], list[MigrationNote]]:
    profiles = []
    for _decision, value in sorted(
        _reviewed(document, "execution_profiles"), key=lambda item: str(item[1]["id"])
    ):
        profiles.append(
            {
                "id": value["id"],
                "name": value["name"],
                "description": value["description"],
                "type": value["type"],
                "engine": value.get("engine", "nextflow"),
                "executor": value["executor"],
                "container_engine": value["container_engine"],
                "source_profile": value["source_profile"],
                "config": {"strategy": "adopted", "source": value["config_source"]},
                "site_parameters": [],
                "evidence": list(value.get("evidence_locations") or []),
            }
        )
        assert profile_id(value["source_profile"]) == value["id"]
    notes = [
        MigrationNote(
            "execution-profiles",
            "/default_profile",
            "blocker",
            "0.1.0 had no default profile; select one explicitly (never the first)",
        ),
        MigrationNote(
            "execution-profiles",
            "/profiles",
            "default",
            "existing unchanged config sources kept as the adopted route",
        ),
    ]
    return {"default_profile": None, "profiles": profiles}, notes


def _provenance(
    root: Path, document: AuthoringDocument
) -> tuple[dict[str, Any], list[MigrationNote]]:
    if not _reviewed(document, "provenance"):
        return {"strategy": None, "source": None, "crate": None}, [
            MigrationNote(
                "provenance", "/strategy", "blocker", "no reviewed provenance"
            )
        ]
    path = root / "ro-crate-metadata.json"
    digest = sha256(path.read_bytes()) if path.is_file() else None
    return (
        {
            "strategy": "include",
            "source": {"path": "ro-crate-metadata.json", "sha256": digest},
            "crate": None,
        },
        [
            MigrationNote(
                "provenance",
                "/strategy",
                "transformed",
                "approved unchanged inclusion kept as strategy 'include'; the crate "
                "is re-analysed against reviewed identity before promotion",
            )
        ],
    )


def plan_draft_migration(
    repository_root: str | Path, *, map_library_to_run: bool = False
) -> MigrationPlan:
    """Preview the drafts a legacy state would produce (no writes)."""
    root = Path(repository_root).resolve()
    document, digest = _legacy(root)
    notes: list[MigrationNote] = []
    identity, identity_notes = _identity(document)
    notes.extend(identity_notes)
    outputs, _candidates, output_notes = _outputs(
        document, map_library_to_run=map_library_to_run
    )
    notes.extend(output_notes)
    components, component_notes = _components(document)
    notes.extend(component_notes)
    execution, execution_notes = _execution(document)
    notes.extend(execution_notes)
    provenance, provenance_notes = _provenance(root, document)
    notes.extend(provenance_notes)
    upstream = root / INPUT_SOURCE
    inputs_text = ""
    if upstream.is_file():
        schema, _ = project_nextflow_schema(
            json.loads(upstream.read_text(encoding="utf-8")), None
        )
        changes, input_notes = _input_changes(document, schema)
        notes.extend(input_notes)
        projected = apply_patch(
            schema,
            ops_for(
                schema,
                {
                    f"{pointer}/{key}": value
                    for pointer, update in changes.items()
                    for key, value in update.items()
                },
            ),
        )
        inputs_text = dump_yaml_data(
            {DRAFT_MARKER: draft_marker("inputs"), **projected}
        )
    else:
        notes.append(
            MigrationNote("inputs", "", "blocker", f"{INPUT_SOURCE} is required")
        )
    drafts = {
        layer_spec("bundle").draft: dump_yaml_data(
            {DRAFT_MARKER: draft_marker("bundle"), "pipeline": identity}
        ),
        layer_spec("outputs").draft: dump_yaml_data(
            {DRAFT_MARKER: draft_marker("outputs"), **outputs}
        ),
        layer_spec("components").draft: dump_yaml_data(
            {DRAFT_MARKER: draft_marker("components"), **components}
        ),
        layer_spec("execution-profiles").draft: dump_yaml_data(
            {DRAFT_MARKER: draft_marker("execution-profiles"), **execution}
        ),
        layer_spec("provenance").draft: dump_yaml_data(
            {DRAFT_MARKER: draft_marker("provenance"), **provenance}
        ),
        layer_spec("inputs").draft: inputs_text,
    }
    existing = tuple(spec.draft for spec in LAYERS if (root / spec.draft).exists())
    return MigrationPlan(digest, drafts, tuple(notes), existing)


def apply_draft_migration(
    repository_root: str | Path,
    context: ChangeContext,
    *,
    map_library_to_run: bool = False,
) -> MigrationPlan:
    """Create absent drafts from legacy state; never edit existing files."""
    if not context.approved:
        raise MigrationError("applying a migration requires explicit approval")
    root = Path(repository_root).resolve()
    plan = plan_draft_migration(root, map_library_to_run=map_library_to_run)
    document, digest = _legacy(root)
    legacy_before = (root / LEGACY_STATE).read_bytes()
    record = {"source": LEGACY_STATE, "sha256": digest, "authoring_schema": "1.0"}

    def provenance_note(state: ReviewState) -> None:
        state.document["migrated_from"] = record

    identity, _ = _identity(document)
    seed_bundle_draft(root, explicit=identity)
    update_review_state(root, "bundle", provenance_note)
    outputs, candidates, _ = _outputs(document, map_library_to_run=map_library_to_run)

    def output_review(state: ReviewState) -> None:
        provenance_note(state)
        for key, value in candidates.items():
            state.candidates.setdefault(key, value)

    seed_draft(root, "outputs", outputs, review=output_review)
    components, _ = _components(document)
    seed_draft(root, "components", components, review=provenance_note)
    execution, _ = _execution(document)
    seed_draft(root, "execution-profiles", execution, review=provenance_note)
    provenance, _ = _provenance(root, document)
    seed_draft(root, "provenance", provenance, review=provenance_note)
    if (root / INPUT_SOURCE).is_file() and import_inputs(root):
        state = read_layer(root, "inputs")
        assert state.draft is not None
        changes, _ = _input_changes(document, state.draft.data)
        operations = ops_for(
            state.draft.data,
            {
                f"{pointer}/{key}": value
                for pointer, update in changes.items()
                for key, value in update.items()
            },
        )
        if operations:
            edit_draft(
                root,
                "inputs",
                operations,
                ChangeContext(
                    actor=context.actor,
                    origin=context.origin,
                    approved=True,
                    approved_by=context.approved_by,
                ),
                action="migrate_access",
            )
        update_review_state(root, "inputs", provenance_note)
    if (root / LEGACY_STATE).read_bytes() != legacy_before:
        raise MigrationError("legacy state changed during migration")
    return plan
