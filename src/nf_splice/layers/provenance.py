"""Provenance layer: one authored RO-Crate graph, published with the bundle.

``.splice-local/drafts/provenance.draft.yaml`` holds the pipeline's
RO-Crate graph (``crate``), written by people or agents; its data-entity IDs
are relative to the pipeline directory. ``source`` records the
repository-root crate it was based on (evidence, never changed) and
``origin`` how it began: ``adopted`` (a copy of the root crate), ``generated``
(built from the identity), ``nf-core`` (nf-core's generator, run on an
isolated copy) or ``authored``.

Building adds deterministic entities for the ``splice/`` bundle and
publishes ``splice/ro-crate-metadata.json``; a complete-pipeline archive
places the same document at its root, where RO-Crate tools look for it
(ADR-0057). Integration-review provenance is a namespaced ``CreateAction``
whose time is captured when the action is taken, so rebuilding never
changes the published bytes.
"""

from __future__ import annotations

import copy
import json
import os
import re
import shutil
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from nf_splice import __version__
from nf_splice.domain.identity import PipelineMetadata, is_placeholder
from nf_splice.drafts import ABSENT, canonical_json, dump_yaml_data, load_yaml_draft
from nf_splice.drafts.store import sha256
from nf_splice.layers.base import (
    ChangeContext,
    DraftIssue,
    EditResult,
    LayerError,
    LayerValidation,
    Severity,
    edit_draft,
    issue,
    ops_for,
    read_layer,
    seed_draft,
    strip_marker,
)
from nf_splice.layers.bundle import validate_bundle_draft
from nf_splice.layout import PRIVATE_DIR, PUBLISHED_DIR
from nf_splice.services.audit import timestamp

LAYER = "provenance"
SOURCE = "ro-crate-metadata.json"
CONTEXT = "https://w3id.org/ro/crate/1.1/context"
CRATE_PROFILE = "https://w3id.org/ro/crate/1.1"
WORKFLOW_PROFILE = "https://w3id.org/workflowhub/workflow-ro-crate/1.0"
TOOL_ENTITY = "#nf-splice"


@dataclass(frozen=True, slots=True)
class CrateFinding:
    """One field-level or structural RO-Crate finding with a suggestion."""

    pointer: str
    code: str
    severity: Severity
    message: str
    crate_value: Any = None
    reviewed_value: Any = None

    def to_json(self) -> dict[str, Any]:
        return {
            "pointer": self.pointer,
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
            "crate_value": self.crate_value,
            "reviewed_value": self.reviewed_value,
        }


def _graph(crate: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    graph = crate.get("@graph")
    if not isinstance(graph, list):
        return {}
    return {
        str(item["@id"]): item
        for item in graph
        if isinstance(item, dict) and isinstance(item.get("@id"), str)
    }


def _ref(value: Any) -> str | None:
    if isinstance(value, Mapping) and isinstance(value.get("@id"), str):
        return str(value["@id"])
    return value if isinstance(value, str) else None


def structural_findings(crate: Any) -> list[CrateFinding]:
    """Check RO-Crate 1.1 and Workflow RO-Crate structural requirements."""
    error = Severity.ERROR
    if not isinstance(crate, Mapping):
        return [CrateFinding("", "structure", error, "RO-Crate must be a JSON object")]
    findings = []
    if "@context" not in crate:
        findings.append(
            CrateFinding("/@context", "structure", error, "missing @context")
        )
    graph = crate.get("@graph")
    if not isinstance(graph, list) or not all(isinstance(item, dict) for item in graph):
        return [
            *findings,
            CrateFinding(
                "/@graph", "structure", error, "@graph must be an object array"
            ),
        ]
    identifiers = [item.get("@id") for item in graph]
    if not all(isinstance(item, str) and item for item in identifiers):
        findings.append(
            CrateFinding("/@graph", "structure", error, "every entity needs an @id")
        )
    duplicates = sorted(
        {str(item) for item in identifiers if identifiers.count(item) > 1}
    )
    for item in duplicates:
        findings.append(
            CrateFinding("/@graph", "duplicate_id", error, f"duplicate @id {item!r}")
        )
    by_id = _graph(crate)
    descriptor = by_id.get(SOURCE)
    if descriptor is None:
        findings.append(
            CrateFinding(
                "/@graph", "structure", error, "missing metadata descriptor entity"
            )
        )
    else:
        if _ref(descriptor.get("about")) != "./":
            findings.append(
                CrateFinding(
                    "/@graph", "structure", error, "descriptor must be about ./"
                )
            )
        conforms = descriptor.get("conformsTo")
        conforms_ids = {
            _ref(item)
            for item in (conforms if isinstance(conforms, list) else [conforms])
        }
        if not any(
            str(item).startswith("https://w3id.org/ro/crate/1.")
            for item in conforms_ids
        ):
            findings.append(
                CrateFinding(
                    "/@graph",
                    "conforms_to",
                    Severity.WARNING,
                    "descriptor should declare conformsTo RO-Crate 1.1 or later",
                )
            )
    root = by_id.get("./")
    if root is None:
        findings.append(
            CrateFinding("/@graph", "structure", error, "missing root dataset ./")
        )
    else:
        for key, why in (
            ("name", "a name"),
            ("description", "a description"),
            ("license", "a licence (a URL or SPDX identifier)"),
            ("datePublished", "the ISO 8601 date this version is published"),
        ):
            if not root.get(key):
                findings.append(
                    CrateFinding(
                        f"/@graph/./{key}",
                        "root_property",
                        Severity.WARNING,
                        f"RO-Crate 1.1 requires the root dataset to have {key} "
                        f"({why}); standards validators reject the crate until it "
                        "is set (never guess it)",
                    )
                )
        main = _ref(root.get("mainEntity"))
        if main is None:
            findings.append(
                CrateFinding(
                    "/@graph",
                    "main_entity",
                    Severity.WARNING,
                    "Workflow RO-Crate expects mainEntity naming the workflow file",
                )
            )
        elif main not in by_id:
            findings.append(
                CrateFinding(
                    "/@graph", "main_entity", error, f"mainEntity {main!r} is missing"
                )
            )
        else:
            types = by_id[main].get("@type")
            types = types if isinstance(types, list) else [types]
            if "ComputationalWorkflow" not in types:
                findings.append(
                    CrateFinding(
                        "/@graph",
                        "main_entity",
                        Severity.WARNING,
                        "mainEntity should be typed ComputationalWorkflow",
                    )
                )
    for entity in graph:
        for key in ("name", "description"):
            value = entity.get(key)
            if isinstance(value, str) and is_placeholder(value):
                findings.append(
                    CrateFinding(
                        f"/@graph/{entity.get('@id')}/{key}",
                        "placeholder",
                        error,
                        f"placeholder {key} {value!r}",
                        value,
                    )
                )
        types = entity.get("@type")
        if types == "Person" or (isinstance(types, list) and "Person" in types):
            identifier = str(entity.get("@id", ""))
            if (
                identifier.startswith("https://orcid.org/")
                and len(identifier.rsplit("/", 1)[-1]) != 19
            ):
                findings.append(
                    CrateFinding(
                        f"/@graph/{identifier}",
                        "contributor_id",
                        error,
                        "malformed ORCID identifier",
                        identifier,
                    )
                )
    return findings


def identity_findings(
    crate: Mapping[str, Any], metadata: PipelineMetadata
) -> list[CrateFinding]:
    """Compare crate values with reviewed identity, field by field."""
    by_id = _graph(crate)
    root = by_id.get("./", {})
    main = by_id.get(_ref(root.get("mainEntity")) or "", {})
    findings = []

    def compare(
        entity: Mapping[str, Any],
        label: str,
        key: str,
        expected: Any,
        severity: Severity,
    ) -> None:
        if expected is None:
            return
        value = entity.get(key)
        # JSON-LD allows any property to be an array: compare its values.
        values = value if isinstance(value, list) else [value]
        values = [
            item.get("@id") if isinstance(item, Mapping) else item for item in values
        ]
        values = [item for item in values if item is not None]
        value = (
            None
            if not values
            else values[0]
            if len(set(map(str, values))) == 1
            else values
        )
        if value is None:
            findings.append(
                CrateFinding(
                    f"/@graph/{label}/{key}",
                    "missing_value",
                    Severity.WARNING,
                    f"{label} has no {key}; reviewed value is {expected!r}",
                    None,
                    expected,
                )
            )
        elif str(value).rstrip("/") != str(expected).rstrip("/"):
            findings.append(
                CrateFinding(
                    f"/@graph/{label}/{key}",
                    "stale_value",
                    severity,
                    f"{label} {key} {value!r} differs from reviewed {expected!r}",
                    value,
                    expected,
                )
            )

    compare(root, "./", "name", metadata.name, Severity.WARNING)
    compare(root, "./", "version", metadata.version, Severity.ERROR)
    compare(root, "./", "description", metadata.description, Severity.WARNING)
    compare(
        root,
        "./",
        "license",
        metadata.licence_url or metadata.licence,
        Severity.WARNING,
    )
    if main:
        compare(main, "mainEntity", "version", metadata.version, Severity.ERROR)
        compare(main, "mainEntity", "url", metadata.repository_url, Severity.WARNING)
    creators = root.get("creator") or root.get("author") or []
    creators = creators if isinstance(creators, list) else [creators]
    names = {
        str((by_id.get(_ref(item) or "") or item or {}).get("name", "")).casefold()
        for item in creators
        if isinstance(item, Mapping)
    }
    for author in metadata.authors:
        if author.name.casefold() not in names:
            findings.append(
                CrateFinding(
                    "/@graph/./creator",
                    "missing_author",
                    Severity.WARNING,
                    f"reviewed author {author.name!r} is not credited in the RO-Crate",
                    None,
                    author.name,
                )
            )
    return findings


@dataclass(frozen=True, slots=True)
class CrateAnalysis:
    """Read-only analysis of the repository-root RO-Crate."""

    present: bool
    sha256: str | None
    findings: tuple[CrateFinding, ...]

    @property
    def blocking(self) -> tuple[CrateFinding, ...]:
        return tuple(item for item in self.findings if item.severity is Severity.ERROR)


def _identity(root: Path) -> PipelineMetadata | None:
    validation = validate_bundle_draft(root)
    return validation.metadata if validation.usable else None


def analyse_ro_crate(repository_root: str | Path) -> CrateAnalysis:
    """Analyse the root RO-Crate against standards and reviewed identity."""
    root = Path(repository_root).resolve()
    path = root / SOURCE
    if path.is_symlink() or not path.is_file():
        return CrateAnalysis(False, None, ())
    payload = path.read_bytes()
    try:
        crate = json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        return CrateAnalysis(
            True,
            sha256(payload),
            (CrateFinding("", "json", Severity.ERROR, f"invalid JSON: {error}"),),
        )
    findings = structural_findings(crate)
    metadata = _identity(root)
    if metadata is not None and isinstance(crate, Mapping):
        findings.extend(identity_findings(crate, metadata))
    return CrateAnalysis(True, sha256(payload), tuple(findings))


def _tool_entities(
    context: ChangeContext, at: str, source_sha: str | None, action: str
) -> list[dict[str, Any]]:
    tool = {
        "@id": TOOL_ENTITY,
        "@type": "SoftwareApplication",
        "name": "nf-splice",
        "version": __version__,
        "url": "https://github.com/Beatson-CompBio/nf-SPLICE",
    }
    event: dict[str, Any] = {
        "@id": f"#nf-splice-{action}",
        "@type": "CreateAction",
        "name": f"nf-splice {action} of the SPLICE integration RO-Crate",
        "instrument": {"@id": TOOL_ENTITY},
        "endTime": at,
        "result": {"@id": SOURCE},
        "agent": {"@id": f"#reviewer-{context.actor.label}"},
    }
    if source_sha is not None:
        event["object"] = {"@id": f"#source-{source_sha[:12]}"}
    entities = [
        tool,
        event,
        {
            "@id": f"#reviewer-{context.actor.label}",
            "@type": "Person"
            if context.actor.kind.value == "human"
            else "SoftwareApplication",
            "name": context.actor.label,
        },
    ]
    if source_sha is not None:
        entities.append(
            {
                "@id": f"#source-{source_sha[:12]}",
                "@type": "CreativeWork",
                "name": "Developer repository-root ro-crate-metadata.json",
                "sha256": source_sha,
            }
        )
    return entities


def _merge_entities(crate: dict[str, Any], entities: list[dict[str, Any]]) -> None:
    graph = crate.setdefault("@graph", [])
    known = {item.get("@id") for item in graph if isinstance(item, dict)}
    for entity in entities:
        if entity["@id"] in known:
            for item in graph:
                if isinstance(item, dict) and item.get("@id") == entity["@id"]:
                    item.clear()
                    item.update(entity)
        else:
            graph.append(entity)
            known.add(entity["@id"])


def _apply_corrections(crate: dict[str, Any], metadata: PipelineMetadata) -> None:
    by_id = _graph(crate)
    root = by_id.setdefault("./", {"@id": "./", "@type": "Dataset"})
    root["name"] = metadata.name
    root["version"] = metadata.version
    if metadata.description:
        root["description"] = metadata.description
    if metadata.licence_url or metadata.licence:
        root["license"] = metadata.licence_url or metadata.licence
    if metadata.released_at:
        root["datePublished"] = metadata.released_at
    main_id = _ref(root.get("mainEntity"))
    if main_id and main_id in by_id:
        by_id[main_id]["version"] = metadata.version
        by_id[main_id]["url"] = metadata.repository_url
    graph = crate["@graph"]
    existing = {item.get("@id") for item in graph}
    creators = []
    for author in metadata.authors:
        identifier = author.orcid or f"#author-{author.name.replace(' ', '-').lower()}"
        creators.append({"@id": identifier})
        if identifier not in existing:
            entity: dict[str, Any] = {
                "@id": identifier,
                "@type": "Organization"
                if author.type.value == "organization"
                else "Person",
                "name": author.name,
            }
            if author.affiliation:
                entity["affiliation"] = author.affiliation
            graph.append(entity)
            existing.add(identifier)
    if creators:
        root["creator"] = creators
    for entity in graph:
        for key in ("name", "description"):
            value = entity.get(key)
            if isinstance(value, str) and is_placeholder(value):
                entity.pop(key)


def _review_time(context: ChangeContext) -> str:
    del context
    return timestamp()


def _identity_draft(root: Path) -> dict[str, Any]:
    """The identity draft's pipeline values, reviewed or not (for seeding)."""
    state = read_layer(root, "bundle")
    if state.draft is None or not isinstance(state.draft.data, dict):
        return {}
    pipeline = state.draft.data.get("pipeline")
    return dict(pipeline) if isinstance(pipeline, dict) else {}


def _nf_core_hosted(root: Path) -> bool:
    """Whether the pipeline says it is an nf-core pipeline."""
    for name in (".nf-core.yml", "nextflow.config"):
        path = root / name
        if path.is_file() and not path.is_symlink():
            text = path.read_text(encoding="utf-8", errors="replace")
            if re.search(r"""name\s*[:=]\s*['"]nf-core/""", text):
                return True
    return False


def _strip_nf_core_claims(crate: dict[str, Any], root: Path) -> list[str]:
    """Remove nf-co.re hosting claims from a crate of a non-nf-core pipeline.

    The upstream generator assumes nf-core naming and URLs; a custom
    pipeline must not be advertised at an invented nf-co.re address.
    """
    if _nf_core_hosted(root):
        return []
    removed = []
    for entity in crate.get("@graph") or []:
        if not isinstance(entity, dict):
            continue
        for key in list(entity):
            value = entity[key]
            values = value if isinstance(value, list) else [value]
            hosted = [
                item
                for item in values
                if "nf-co.re" in str(_ref(item) or item)
                or "github.com/nf-core/" in str(_ref(item) or item)
            ]
            if hosted:
                kept = [item for item in values if item not in hosted]
                if kept:
                    entity[key] = kept if isinstance(value, list) else kept[0]
                else:
                    entity.pop(key)
                removed.append(f"{entity.get('@id')}.{key}")
    return removed


def minimal_crate(
    root: Path,
    identity: Mapping[str, Any],
    *,
    main_workflow: str = "main.nf",
) -> dict[str, Any]:
    """A Workflow RO-Crate of the pipeline from identity values (base: root).

    Data-entity IDs are relative to the pipeline directory: the same graph
    is published as ``splice/ro-crate-metadata.json`` and placed at the root
    of the complete-pipeline archive. Only values present are used; nothing
    is invented.
    """
    name = identity.get("name")
    root_entity: dict[str, Any] = {
        "@id": "./",
        "@type": "Dataset",
        "mainEntity": {"@id": main_workflow},
        "hasPart": [{"@id": main_workflow}],
    }
    for key, target in (
        ("name", "name"),
        ("version", "version"),
        ("description", "description"),
    ):
        if identity.get(key):
            root_entity[target] = identity[key]
    licence = identity.get("licence_url") or identity.get("licence")
    if licence:
        root_entity["license"] = licence
    if identity.get("released_at"):
        root_entity["datePublished"] = identity["released_at"]
    workflow: dict[str, Any] = {
        "@id": main_workflow,
        "@type": ["File", "SoftwareSourceCode", "ComputationalWorkflow"],
        "programmingLanguage": {"@id": "#nextflow"},
    }
    if name:
        workflow["name"] = name
    if identity.get("version"):
        workflow["version"] = identity["version"]
    if identity.get("repository_url"):
        workflow["url"] = identity["repository_url"]
    graph: list[dict[str, Any]] = [
        {
            "@id": SOURCE,
            "@type": "CreativeWork",
            "about": {"@id": "./"},
            "conformsTo": [{"@id": CRATE_PROFILE}, {"@id": WORKFLOW_PROFILE}],
        },
        root_entity,
        workflow,
        {
            "@id": "#nextflow",
            "@type": "ComputerLanguage",
            "name": "Nextflow",
            "url": "https://www.nextflow.io/",
        },
    ]
    creators = []
    for author in identity.get("authors") or []:
        if not isinstance(author, Mapping) or not author.get("name"):
            continue
        identifier = (
            author.get("orcid")
            or f"#author-{str(author['name']).replace(' ', '-').lower()}"
        )
        creators.append({"@id": identifier})
        entity: dict[str, Any] = {
            "@id": identifier,
            "@type": "Organization"
            if author.get("type") == "organization"
            else "Person",
            "name": author["name"],
        }
        if author.get("affiliation"):
            entity["affiliation"] = author["affiliation"]
        graph.append(entity)
    if creators:
        root_entity["creator"] = creators
    if not (root / main_workflow).is_file():
        root_entity.pop("mainEntity")
        root_entity.pop("hasPart")
        graph.remove(workflow)
    return {"@context": CONTEXT, "@graph": graph}


def seed_provenance(repository_root: str | Path) -> list[str]:
    """Create the provenance draft once, with a meaningful crate.

    A parseable repository-root crate is adopted as the baseline (a copy:
    the developer's file is never changed). Otherwise a Workflow RO-Crate is
    built from the identity draft. Either way the crate is the author's to
    edit; findings against the reviewed identity are reported by validation.
    """
    root = Path(repository_root).resolve()
    if read_layer(root, LAYER).file.exists:
        return []
    analysis = analyse_ro_crate(root)
    notes: list[str] = []
    crate: Any = None
    source = None
    origin = "generated"
    if analysis.present and not any(item.code == "json" for item in analysis.findings):
        loaded = json.loads((root / SOURCE).read_text(encoding="utf-8"))
        if isinstance(loaded, dict) and isinstance(loaded.get("@graph"), list):
            crate = loaded
            source = {"path": SOURCE, "sha256": analysis.sha256}
            origin = "adopted"
            notes.append(
                f"adopted a copy of the repository-root {SOURCE} as the provenance "
                "baseline (the original is not changed)"
            )
    if crate is None:
        crate = minimal_crate(root, _identity_draft(root))
        notes.append(
            "generated a Workflow RO-Crate from the identity draft; nf-splice "
            "never regenerates it: edit it, or replace it with nf-core's "
            "generator (`nf-splice configure provenance --with-nf-core`)"
        )
    _ensure_round_trip(crate)
    seed_draft(
        root,
        LAYER,
        {"origin": origin, "source": source, "crate": crate},
        header=(
            "nf-SPLICE provenance draft (authoritative, editable RO-Crate graph).",
            "IDs are relative to the pipeline directory. nf-splice adds the splice/",
            "bundle entities when it publishes; never edit the published file.",
        ),
    )
    return notes


def _set(
    root: Path, changes: Mapping[str, Any], context: ChangeContext, action: str
) -> EditResult:
    seed_provenance(root)
    state = read_layer(root, LAYER)
    if state.draft is None:
        raise LayerError("provenance.draft.yaml is malformed")
    return edit_draft(
        root, LAYER, ops_for(state.draft.data, changes), context, action=action
    )


def _origin_changes(data: Mapping[str, Any], origin: str) -> dict[str, Any]:
    changes: dict[str, Any] = {"/origin": origin}
    if "strategy" in data:
        changes["/strategy"] = ABSENT
    return changes


def choose_include(repository_root: str | Path, context: ChangeContext) -> EditResult:
    """Optional: adopt the current repository-root crate as the authored graph."""
    root = Path(repository_root).resolve()
    analysis = analyse_ro_crate(root)
    if not analysis.present:
        raise LayerError("no repository-root ro-crate-metadata.json to include")
    if analysis.blocking:
        raise LayerError(
            "root RO-Crate has blocking differences; review an enriched copy instead: "
            + "; ".join(item.message for item in analysis.blocking)
        )
    crate = json.loads((root / SOURCE).read_text(encoding="utf-8"))
    _ensure_round_trip(crate)
    seed_provenance(root)
    state = read_layer(root, LAYER)
    data = state.draft.data if state.draft is not None else {}
    return _set(
        root,
        {
            **_origin_changes(data, "adopted"),
            "/source": {"path": SOURCE, "sha256": analysis.sha256},
            "/crate": crate,
        },
        context,
        "choose_include",
    )


def prepare_enrichment(
    repository_root: str | Path,
    context: ChangeContext,
    *,
    at: str | None = None,
) -> EditResult:
    """Optional: correct a copy of the root crate from the reviewed identity."""
    root = Path(repository_root).resolve()
    analysis = analyse_ro_crate(root)
    if not analysis.present:
        raise LayerError("no repository-root ro-crate-metadata.json to enrich")
    metadata = _identity(root)
    if metadata is None:
        raise LayerError("bundle.draft.yaml identity must be ready before enrichment")
    crate = json.loads((root / SOURCE).read_text(encoding="utf-8"))
    if not isinstance(crate.get("@graph"), list):
        raise LayerError("root RO-Crate graph cannot be enriched safely")
    projection = copy.deepcopy(crate)
    _apply_corrections(projection, metadata)
    _merge_entities(
        projection,
        _tool_entities(
            context, at or _review_time(context), analysis.sha256, "enrichment"
        ),
    )
    _ensure_round_trip(projection)
    seed_provenance(root)
    state = read_layer(root, LAYER)
    data = state.draft.data if state.draft is not None else {}
    return _set(
        root,
        {
            **_origin_changes(data, "adopted"),
            "/source": {"path": SOURCE, "sha256": analysis.sha256},
            "/crate": projection,
        },
        context,
        "prepare_enrichment",
    )


def generate_minimal(
    repository_root: str | Path,
    context: ChangeContext,
    *,
    main_workflow: str = "main.nf",
    at: str | None = None,
) -> EditResult:
    """Optional: replace the crate with one built from the reviewed identity."""
    root = Path(repository_root).resolve()
    metadata = _identity(root)
    if metadata is None:
        raise LayerError(
            "bundle.draft.yaml identity must be ready to generate an RO-Crate"
        )
    if not (root / main_workflow).is_file():
        raise LayerError(f"workflow file {main_workflow} does not exist")
    crate = minimal_crate(
        root, metadata.model_dump(mode="json"), main_workflow=main_workflow
    )
    _apply_corrections(crate, metadata)
    _merge_entities(
        crate, _tool_entities(context, at or _review_time(context), None, "generation")
    )
    _ensure_round_trip(crate)
    seed_provenance(root)
    state = read_layer(root, LAYER)
    data = state.draft.data if state.draft is not None else {}
    return _set(
        root,
        {**_origin_changes(data, "generated"), "/source": None, "/crate": crate},
        context,
        "generate_minimal",
    )


# ------------------------------------------------- nf-core generator adapter

#: nf-core/tools releases whose ``pipelines rocrate`` this adapter was checked
#: against (options ``--json_path``; no interactive prompt when a licence
#: exists; version check disabled through the environment).
NF_CORE_SUPPORTED = ("3.3", "3.4", "3.5", "4.0", "4.1")


@dataclass(frozen=True, slots=True)
class GeneratorRun:
    """Outcome of one isolated ``nf-core pipelines rocrate`` run."""

    command: tuple[str, ...]
    version: str | None
    returncode: int
    crate: dict[str, Any] | None
    removed_claims: tuple[str, ...]
    log: str


Runner = Callable[[Sequence[str], Path, Mapping[str, str], float], tuple[int, str]]


def _default_runner(
    command: Sequence[str], cwd: Path, environment: Mapping[str, str], timeout: float
) -> tuple[int, str]:
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        env=dict(environment),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return completed.returncode, (completed.stdout + completed.stderr)[-4000:]


def _isolated_copy(root: Path, target: Path) -> None:
    """Copy the pipeline's own files (not .git, drafts, splice/ or caches)."""
    skipped = {".git", ".splice-local", ".nf-splice-local", "work", ".nextflow"}
    for current, directories, names in os.walk(root, followlinks=False):
        relative = Path(current).relative_to(root)
        directories[:] = [
            name
            for name in directories
            if name not in skipped and not (relative == Path(".") and name == "splice")
        ]
        (target / relative).mkdir(parents=True, exist_ok=True)
        for name in names:
            path = Path(current) / name
            if path.is_symlink() or not path.is_file():
                continue
            if name == SOURCE and relative == Path("."):
                continue
            shutil.copy2(path, target / relative / name)


def generate_with_nf_core(
    repository_root: str | Path,
    context: ChangeContext,
    *,
    approve: bool,
    executable: str = "nf-core",
    runner: Runner | None = None,
    timeout: float = 300.0,
    write: bool = True,
) -> GeneratorRun:
    """Generate a candidate crate with nf-core's generator, safely (opt-in).

    The generator runs on an isolated copy below ``.splice-local/tmp/`` with
    no terminal input and nf-core's update check disabled, so it can neither
    change the pipeline nor wait for a prompt. Its output is a *candidate*:
    reviewed identity values are applied, nf-co.re hosting claims are removed
    from non-nf-core pipelines, and the result replaces the draft's crate.
    The generator is not a validator; validate the draft afterwards.
    """
    if not approve:
        raise LayerError("running nf-core needs explicit approval")
    root = Path(repository_root).resolve()
    found = shutil.which(executable) if runner is None else executable
    if found is None:
        raise LayerError(
            f"{executable} is not installed; install nf-core/tools yourself "
            "(nf-splice never installs software), or edit the crate by hand"
        )
    execute = runner or _default_runner
    environment = {
        key: value
        for key, value in os.environ.items()
        if key in {"PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT"}
    } | {"NFCORE_NO_VERSION_CHECK": "1", "GIT_TERMINAL_PROMPT": "0"}
    code, version_text = execute([found, "--version"], root, environment, 60.0)
    match = re.search(r"version\s+(\d+\.\d+(?:\.\d+)?)", version_text)
    version = match.group(1) if match else None
    workspace = root / PRIVATE_DIR / "tmp" / "nf-core-rocrate"
    shutil.rmtree(workspace, ignore_errors=True)
    copy_root = workspace / "pipeline"
    output = workspace / SOURCE
    _isolated_copy(root, copy_root)
    command = (
        found,
        "pipelines",
        "rocrate",
        str(copy_root),
        "--json_path",
        str(output),
    )
    code, log = execute(command, workspace, environment, timeout)
    crate = None
    removed: list[str] = []
    if code == 0 and output.is_file():
        loaded = json.loads(output.read_text(encoding="utf-8"))
        if isinstance(loaded, dict) and isinstance(loaded.get("@graph"), list):
            crate = loaded
            removed = _strip_nf_core_claims(crate, root)
            metadata = _identity(root)
            if metadata is not None:
                _apply_corrections(crate, metadata)
            _merge_entities(
                crate,
                _tool_entities(context, _review_time(context), None, "generation"),
            )
            _ensure_round_trip(crate)
    shutil.rmtree(workspace, ignore_errors=True)
    run = GeneratorRun(
        command=("nf-core", "pipelines", "rocrate", "<isolated copy>", "--json_path"),
        version=version,
        returncode=code,
        crate=crate,
        removed_claims=tuple(removed),
        log=log,
    )
    if crate is None:
        raise LayerError(
            f"nf-core pipelines rocrate (version {version or 'unknown'}) did not "
            f"produce a crate (exit code {code}); the draft is unchanged. "
            f"Output: {log[-500:]}"
        )
    if write:
        seed_provenance(root)
        state = read_layer(root, LAYER)
        data = state.draft.data if state.draft is not None else {}
        _set(
            root,
            {**_origin_changes(data, "nf-core"), "/source": None, "/crate": crate},
            context,
            "generate_with_nf_core",
        )
    return run


def _ensure_round_trip(crate: Mapping[str, Any]) -> None:
    text = dump_yaml_data({"crate": crate})
    if load_yaml_draft(text).data != {"crate": json.loads(json.dumps(crate))}:
        raise LayerError("RO-Crate graph cannot be represented losslessly in YAML")


# ------------------------------------------------- SPLICE bundle entities

_FORMATS = {
    ".json": "application/json",
    ".yaml": "application/yaml",
    ".md": "text/markdown",
    ".config": "text/plain",
}
_DESCRIPTIONS = {
    "bundle.json": "SPLICE workflow bundle index: identity, assay capabilities "
    "and the bundle's files",
    "inputs.schema.json": "Runtime input contract (JSON Schema 2020-12)",
    "outputs.schema.json": "Output catalogue as a JSON Schema for one job's "
    "analysis_output.json",
    "outputs.yaml": "Developer-readable output catalogue",
    "components.json": "Software components and container images",
    "execution-profiles.json": "Execution profiles and their configurations",
    "README.md": "Human-readable summary of the bundle",
    "nf-splice.lock.json": "nf-splice build lock: hashes of the published files",
}


def bundle_files(root: Path) -> tuple[str, ...]:
    """Files the bundle publishes besides the crate (paths below ``splice/``)."""
    files = [
        "bundle.json",
        "README.md",
        "nf-splice.lock.json",
        "inputs.schema.json",
        "outputs.yaml",
        "outputs.schema.json",
        "components.json",
        "execution-profiles.json",
    ]
    state = read_layer(root, "execution-profiles")
    if state.draft is not None and isinstance(state.draft.data, dict):
        for profile in state.draft.data.get("profiles") or []:
            if isinstance(profile, dict) and isinstance(profile.get("id"), str):
                files.append(f"configs/{profile['id']}.config")
    return tuple(sorted(set(files)))


def splice_entities(root: Path, crate: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Deterministic graph entities for the ``splice/`` integration bundle.

    Build-owned, like a file index: the author never maintains them. No
    checksums are included, so the crate and ``bundle.json`` (which records
    the crate's hash) never depend on each other.
    """
    by_id = _graph(crate)
    main = _ref(by_id.get("./", {}).get("mainEntity"))
    parts = []
    entities: list[dict[str, Any]] = []
    for name in bundle_files(root):
        identifier = f"{PUBLISHED_DIR}/{name}"
        parts.append({"@id": identifier})
        entity: dict[str, Any] = {
            "@id": identifier,
            "@type": "File",
            "name": name,
            "encodingFormat": _FORMATS.get(PurePosixPath(name).suffix, "text/plain"),
        }
        description = _DESCRIPTIONS.get(name) or (
            "Nextflow configuration of an execution profile"
            if name.startswith("configs/")
            else None
        )
        if description:
            entity["description"] = description
        entities.append(entity)
    bundle: dict[str, Any] = {
        "@id": f"{PUBLISHED_DIR}/",
        "@type": "Dataset",
        "name": "SPLICE workflow bundle",
        "description": "The pipeline's SPLICE integration: versioned contracts "
        "(bundle, inputs, outputs, components, execution profiles) and this "
        "RO-Crate metadata, produced by nf-splice.",
        "hasPart": parts,
    }
    if main:
        bundle["about"] = {"@id": main}
    return [bundle, *entities]


def compile_crate(root: Path, crate: Mapping[str, Any]) -> dict[str, Any]:
    """The published crate: the authored graph plus the bundle entities."""
    compiled = copy.deepcopy(dict(crate))
    entities = splice_entities(root, compiled)
    graph = [
        item
        for item in compiled.get("@graph") or []
        if not (
            isinstance(item, dict)
            and str(item.get("@id", "")).startswith(f"{PUBLISHED_DIR}/")
        )
    ]
    compiled["@graph"] = graph
    root_entity = next(
        (item for item in graph if isinstance(item, dict) and item.get("@id") == "./"),
        None,
    )
    if root_entity is not None:
        existing = root_entity.get("hasPart")
        existing_list = (
            existing if isinstance(existing, list) else ([existing] if existing else [])
        )
        kept = [
            item
            for item in existing_list
            if not str(_ref(item) or "").startswith(f"{PUBLISHED_DIR}/")
        ]
        root_entity["hasPart"] = [*kept, {"@id": f"{PUBLISHED_DIR}/"}]
    graph.extend(entities)
    return compiled


def _draft_crate(
    root: Path, data: Mapping[str, Any]
) -> tuple[Any, str | None, list[DraftIssue]]:
    """The authored graph, its origin and any problem with the draft's shape.

    Reads the current shape (``origin``/``source``/``crate``) and the earlier
    ``strategy`` one of the same unreleased contract: ``include`` with no
    crate means the repository-root crate is the graph.
    """
    issues: list[DraftIssue] = []
    unknown = sorted(set(data) - {"origin", "strategy", "source", "crate"})
    issues.extend(
        issue(LAYER, f"/{name}", "unknown_field", f"unknown field {name!r}")
        for name in unknown
    )
    origin = data.get("origin") or data.get("strategy")
    crate = data.get("crate")
    if crate is None and data.get("strategy") == "include":
        path = root / SOURCE
        if path.is_file() and not path.is_symlink():
            try:
                crate = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as error:
                issues.append(
                    issue(LAYER, "", "json", f"invalid JSON: {error}", path=SOURCE)
                )
    if crate is None:
        issues.append(
            issue(
                LAYER,
                "/crate",
                "missing_required",
                "the provenance draft has no RO-Crate graph; write one under "
                "crate, or run `nf-splice init` on a copy without this draft",
            )
        )
    return crate, str(origin) if origin else None, issues


def validate_provenance_draft(repository_root: str | Path) -> LayerValidation:
    """Validate the authored crate and compile the published crate."""
    root = Path(repository_root).resolve()
    state = read_layer(root, LAYER)
    if state.draft is None or not isinstance(state.draft.data, dict):
        code = "missing_draft" if not state.file.exists else "syntax"
        return LayerValidation(
            LAYER, (issue(LAYER, "", code, str(state.error or code)),)
        )
    data = strip_marker(state.draft.data)
    crate, _origin, issues = _draft_crate(root, data)
    if crate is None:
        return LayerValidation(LAYER, tuple(issues))
    analysis = analyse_ro_crate(root)
    source = data.get("source") or {}
    if (
        isinstance(source, Mapping)
        and source.get("sha256")
        and analysis.present
        and source.get("sha256") != analysis.sha256
    ):
        issues.append(
            issue(
                LAYER,
                "/source/sha256",
                "source_changed",
                "the repository-root RO-Crate changed since this graph was based "
                "on it; compare them and update the draft if needed",
                Severity.WARNING,
            )
        )
    for finding in structural_findings(crate):
        issues.append(
            issue(
                LAYER,
                f"/crate{finding.pointer}",
                finding.code,
                finding.message,
                finding.severity,
            )
        )
    metadata = _identity(root)
    if metadata is None:
        issues.append(issue(LAYER, "", "identity_not_ready", "identity is not ready"))
    elif isinstance(crate, Mapping):
        for finding in identity_findings(crate, metadata):
            issues.append(
                issue(
                    LAYER,
                    f"/crate{finding.pointer}",
                    finding.code,
                    finding.message,
                    finding.severity,
                )
            )
    if any(item.severity is Severity.ERROR for item in issues) or not isinstance(
        crate, Mapping
    ):
        return LayerValidation(LAYER, tuple(issues))
    return LayerValidation(
        LAYER, tuple(issues), {SOURCE: canonical_json(compile_crate(root, crate))}
    )


def crate_origin(repository_root: str | Path) -> str | None:
    """How the authored crate began (adopted, generated, nf-core, authored)."""
    state = read_layer(Path(repository_root).resolve(), LAYER)
    if state.draft is None or not isinstance(state.draft.data, dict):
        return None
    value = state.draft.data.get("origin") or state.draft.data.get("strategy")
    return str(value) if value else None
