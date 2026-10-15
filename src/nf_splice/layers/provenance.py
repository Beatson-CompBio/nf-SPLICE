"""Provenance layer: ``ro-crate-metadata.draft.yaml`` and the published crate.

The developer's repository-root ``ro-crate-metadata.json`` is never modified.
Three reviewed strategies exist: ``include`` (publish the root bytes
unchanged once they agree with the reviewed identity), ``enriched`` (a
reviewed, corrected projection of the root graph) and ``generated`` (a
minimal Workflow RO-Crate built from reviewed facts when no source exists).
Integration-review provenance is a namespaced ``CreateAction`` whose time is
captured at approval, so rebuilding never changes the published bytes.
"""

from __future__ import annotations

import copy
import json
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nf_splice import __version__
from nf_splice.domain.identity import PipelineMetadata, is_placeholder
from nf_splice.drafts import canonical_json, dump_yaml_data, load_yaml_draft
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
from nf_splice.services.audit import timestamp

LAYER = "provenance"
SOURCE = "ro-crate-metadata.json"
CONTEXT = "https://w3id.org/ro/crate/1.1/context"
CRATE_PROFILE = "https://w3id.org/ro/crate/1.1"
WORKFLOW_PROFILE = "https://w3id.org/workflowhub/workflow-ro-crate/1.0"
TOOL_ENTITY = "#nf-splice"
_STRATEGIES = ("include", "enriched", "generated")


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
        if isinstance(value, Mapping):
            value = value.get("@id")
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
    return validation.metadata if validation.ready else None


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


def _seed(root: Path) -> None:
    seed_draft(root, LAYER, {"strategy": None, "source": None, "crate": None})


def _set(
    root: Path, changes: Mapping[str, Any], context: ChangeContext, action: str
) -> EditResult:
    _seed(root)
    state = read_layer(root, LAYER)
    if state.draft is None:
        raise LayerError("ro-crate-metadata.draft.yaml is malformed")
    return edit_draft(
        root, LAYER, ops_for(state.draft.data, changes), context, action=action
    )


def choose_include(repository_root: str | Path, context: ChangeContext) -> EditResult:
    """Approve unchanged inclusion of a current, standards-compliant root crate."""
    root = Path(repository_root).resolve()
    analysis = analyse_ro_crate(root)
    if not analysis.present:
        raise LayerError("no repository-root ro-crate-metadata.json to include")
    if analysis.blocking:
        raise LayerError(
            "root RO-Crate has blocking differences; review an enriched copy instead: "
            + "; ".join(item.message for item in analysis.blocking)
        )
    return _set(
        root,
        {
            "/strategy": "include",
            "/source": {"path": SOURCE, "sha256": analysis.sha256},
            "/crate": None,
        },
        context,
        "choose_include",
    )


def _apply_corrections(crate: dict[str, Any], metadata: PipelineMetadata) -> None:
    by_id = _graph(crate)
    root = by_id.setdefault("./", {"@id": "./", "@type": "Dataset"})
    root["name"] = metadata.name
    root["version"] = metadata.version
    if metadata.description:
        root["description"] = metadata.description
    if metadata.licence_url or metadata.licence:
        root["license"] = metadata.licence_url or metadata.licence
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


def prepare_enrichment(
    repository_root: str | Path,
    context: ChangeContext,
    *,
    at: str | None = None,
) -> EditResult:
    """Record a reviewed, corrected projection of the root crate in the draft."""
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
    projection["@graph"].extend(
        _tool_entities(
            context, at or _review_time(context), analysis.sha256, "enrichment"
        )
    )
    _ensure_round_trip(projection)
    return _set(
        root,
        {
            "/strategy": "enriched",
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
    """Build a minimal Workflow RO-Crate from reviewed identity only."""
    root = Path(repository_root).resolve()
    metadata = _identity(root)
    if metadata is None:
        raise LayerError(
            "bundle.draft.yaml identity must be ready to generate an RO-Crate"
        )
    if not (root / main_workflow).is_file():
        raise LayerError(f"workflow file {main_workflow} does not exist")
    crate: dict[str, Any] = {
        "@context": CONTEXT,
        "@graph": [
            {
                "@id": SOURCE,
                "@type": "CreativeWork",
                "about": {"@id": "./"},
                "conformsTo": [{"@id": CRATE_PROFILE}, {"@id": WORKFLOW_PROFILE}],
            },
            {
                "@id": "./",
                "@type": "Dataset",
                "mainEntity": {"@id": main_workflow},
            },
            {
                "@id": main_workflow,
                "@type": ["File", "SoftwareSourceCode", "ComputationalWorkflow"],
                "name": metadata.name,
                "programmingLanguage": {"@id": "#nextflow"},
            },
            {
                "@id": "#nextflow",
                "@type": "ComputerLanguage",
                "name": "Nextflow",
                "url": "https://www.nextflow.io/",
            },
        ],
    }
    _apply_corrections(crate, metadata)
    crate["@graph"].extend(
        _tool_entities(context, at or _review_time(context), None, "generation")
    )
    _ensure_round_trip(crate)
    return _set(
        root,
        {"/strategy": "generated", "/source": None, "/crate": crate},
        context,
        "generate_minimal",
    )


def generate_with_nf_core(
    repository_root: str | Path,
    *,
    approve: bool,
    runner: Callable[[Sequence[str], Path], int] | None = None,
) -> None:
    """Run the public ``nf-core pipelines rocrate .`` command (opt-in)."""
    if not approve:
        raise LayerError("running nf-core needs explicit approval")
    root = Path(repository_root).resolve()
    if (root / SOURCE).exists():
        raise LayerError("a root RO-Crate already exists; it is developer-owned")
    execute = runner or (
        lambda command, cwd: (
            subprocess.run(list(command), cwd=cwd, check=False).returncode
        )
    )
    code = execute(["nf-core", "pipelines", "rocrate", "."], root)
    if code != 0 or not (root / SOURCE).is_file():
        raise LayerError(f"nf-core pipelines rocrate failed with exit code {code}")


def _ensure_round_trip(crate: Mapping[str, Any]) -> None:
    text = dump_yaml_data({"crate": crate})
    if load_yaml_draft(text).data != {"crate": json.loads(json.dumps(crate))}:
        raise LayerError("RO-Crate graph cannot be represented losslessly in YAML")


def validate_provenance_draft(repository_root: str | Path) -> LayerValidation:
    """Validate the reviewed provenance strategy and compile the final crate."""
    root = Path(repository_root).resolve()
    state = read_layer(root, LAYER)
    if state.draft is None or not isinstance(state.draft.data, dict):
        code = "missing_draft" if not state.file.exists else "syntax"
        return LayerValidation(
            LAYER, (issue(LAYER, "", code, str(state.error or code)),)
        )
    data = strip_marker(state.draft.data)
    strategy = data.get("strategy")
    issues: list[DraftIssue] = []
    if strategy not in _STRATEGIES:
        return LayerValidation(
            LAYER,
            (
                issue(
                    LAYER,
                    "/strategy",
                    "missing_required",
                    "choose include, enriched or generated provenance",
                ),
            ),
        )
    analysis = analyse_ro_crate(root)
    source = data.get("source") or {}
    if strategy in {"include", "enriched"}:
        if not analysis.present:
            return LayerValidation(
                LAYER,
                (
                    issue(
                        LAYER, "/source", "missing_source", "root RO-Crate is missing"
                    ),
                ),
            )
        if source.get("sha256") != analysis.sha256:
            issues.append(
                issue(
                    LAYER,
                    "/source/sha256",
                    "stale_source",
                    "the root RO-Crate changed since it was reviewed; review again",
                )
            )
    if strategy == "include":
        for finding in analysis.findings:
            issues.append(
                issue(
                    LAYER,
                    finding.pointer,
                    finding.code,
                    finding.message,
                    finding.severity,
                    path=SOURCE,
                )
            )
        payload = (root / SOURCE).read_bytes() if analysis.present else b""
    else:
        crate = data.get("crate")
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
            issues.append(
                issue(LAYER, "", "identity_not_ready", "identity is not ready")
            )
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
        payload = canonical_json(crate)
    if any(item.severity is Severity.ERROR for item in issues):
        return LayerValidation(LAYER, tuple(issues))
    return LayerValidation(LAYER, tuple(issues), {SOURCE: payload})
