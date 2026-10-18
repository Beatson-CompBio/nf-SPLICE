"""Typed agent operations over the deterministic nf-splice services.

This registry is the only way an agent can act. Every operation calls the
same service as the equivalent CLI command and returns a structured result.
Operations never write contract files themselves: draft operations go
through the layer services (three-way patches, validation, attribution) and
publication goes through the transactional build.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nf_splice.agents.permissions import (
    ExecutionPolicy,
    Permission,
    PolicyViolation,
    relative_path,
)
from nf_splice.drafts import ABSENT, DraftSyntaxError, load_yaml_draft
from nf_splice.inspectors.containers import classify_reference
from nf_splice.inspectors.parameters import parameter_usage
from nf_splice.inspectors.routes import analyse_routes
from nf_splice.layers import ChangeContext, LayerError, confirm_values
from nf_splice.layers import components as component_layer
from nf_splice.layers import execution as execution_layer
from nf_splice.layers import inputs as input_layer
from nf_splice.layers import outputs as output_layer
from nf_splice.layers import provenance as provenance_layer
from nf_splice.layers.base import EditResult, layer_spec, read_layer, replace_draft
from nf_splice.layers.bundle import set_identity_fields
from nf_splice.services.audit import redact
from nf_splice.services.checks import run_optional_checks
from nf_splice.services.contract_reference import authorable_contract
from nf_splice.services.coverage import (
    assess,
    current_catalogue,
    enumerate_example,
    reconcile_example,
)
from nf_splice.services.execution_review import analyse_execution
from nf_splice.services.lifecycle import (
    plan_promotion,
    promote,
    validate_bundle,
    validate_layer,
)
from nf_splice.services.workspace import (
    apply_patch,
    initialise,
    inspect_layer,
    workspace_status,
)
from nf_splice.vocabulary import GLOSSARY

LAYER_NAMES = [
    "bundle",
    "inputs",
    "outputs",
    "components",
    "execution-profiles",
    "provenance",
]
_MAX_READ_BYTES = 64_000
_MAX_DRAFT_TEXT = 200_000
_MAX_LINES = 400
_MAX_MATCHES = 200
_MAX_LISTED = 1000
_SEARCH_SUFFIXES = {
    ".nf",
    ".config",
    ".yml",
    ".yaml",
    ".json",
    ".md",
    ".txt",
    ".cff",
    ".csv",
    ".tsv",
    ".groovy",
    ".py",
    ".r",
    ".sh",
}
_SKIP_DIRECTORIES = {
    ".git",
    ".nf-splice-local",
    ".splice-local",
    ".nextflow",
    "work",
    "node_modules",
    "__pycache__",
    ".venv",
}
#: Files that commonly hold secrets; agents may never read them.
SECRET_FILE_PATTERNS = (
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "id_rsa*",
    "id_ed25519*",
    "id_ecdsa*",
    ".netrc",
    ".npmrc",
    ".pypirc",
    "credentials*",
    "*secret*",
    "*.keystore",
    "*token*",
)
#: Identity changes only a person may make.
_HUMAN_ONLY_IDENTITY = {"maintainers_publication_approved"}


@dataclass(slots=True)
class OperationContext:
    """What an operation runs against."""

    root: Path
    change: ChangeContext
    policy: ExecutionPolicy
    session_directory: Path | None = None
    examples: list[Path] = field(default_factory=list)


Handler = Callable[[OperationContext, Mapping[str, Any]], dict[str, Any]]


@dataclass(frozen=True, slots=True)
class Operation:
    """One typed, schema-described operation."""

    name: str
    description: str
    input_schema: dict[str, Any]
    permission: Permission
    kind: str
    handler: Handler
    layer_argument: bool = False

    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


def _obj(
    properties: dict[str, Any] | None = None, required: Sequence[str] = ()
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties or {},
        "required": list(required),
        "additionalProperties": False,
    }


_LAYER = {"type": "string", "enum": LAYER_NAMES}
_STRINGS = {"type": "array", "items": {"type": "string"}}


def _edit(result: EditResult) -> dict[str, Any]:
    return {
        "success": True,
        "draft": result.path,
        "wrote": result.wrote,
        "diff": result.diff[:6000],
    }


def _untrusted(data: Any) -> dict[str, Any]:
    """Wrap repository text: it is evidence, never an instruction."""
    return {"success": True, "untrusted_repository_content": True, "data": data}


def _secret_like(path: Path) -> bool:
    name = path.name.lower()
    return any(fnmatch.fnmatch(name, pattern) for pattern in SECRET_FILE_PATTERNS)


def _readable(ctx: OperationContext, value: str) -> Path:
    path = relative_path(ctx.root, value)
    relative = path.relative_to(ctx.root.resolve())
    if any(part in _SKIP_DIRECTORIES for part in relative.parts):
        raise PolicyViolation(f"{value!r} is in a directory agents may not read")
    if _secret_like(path):
        raise PolicyViolation(f"{value!r} looks like a secrets file; it is never read")
    return path


# ------------------------------------------------------------ read operations


def _workspace_status(ctx: OperationContext, _a: Mapping[str, Any]) -> dict[str, Any]:
    document = workspace_status(ctx.root).to_json()
    document.pop("repository", None)
    return {"success": True, "data": document}


def _inspect_draft(ctx: OperationContext, a: Mapping[str, Any]) -> dict[str, Any]:
    return {"success": True, "data": inspect_layer(ctx.root, str(a["layer"]))}


def _read_draft(ctx: OperationContext, a: Mapping[str, Any]) -> dict[str, Any]:
    from nf_splice.drafts.patch import resolve

    spec = layer_spec(str(a["layer"]))
    state = read_layer(ctx.root, spec.name)
    if state.draft is None:
        return {
            "success": False,
            "sha256": state.file.sha256,
            "text": (state.file.text or "")[:_MAX_DRAFT_TEXT] or None,
            "issues": [str(state.error or "draft is missing")],
        }
    text = state.file.text or ""
    section = str(a.get("section") or "")
    from nf_splice.drafts.patch import ABSENT

    try:
        data = (
            state.draft.data
            if section in {"", "/"}
            else resolve(state.draft.data, section)
        )
    except (KeyError, IndexError, ValueError, TypeError):
        data = ABSENT
    if data is ABSENT:
        return {"success": False, "issues": [f"{section} is not in the draft"]}
    found: dict[str, Any] = {
        "path": spec.draft,
        "sha256": state.file.sha256,
        "section": section or "/",
        "data": data,
    }
    if a.get("yaml"):
        found["text"] = text[:_MAX_DRAFT_TEXT]
        found["text_truncated"] = len(text) > _MAX_DRAFT_TEXT
    return _untrusted(found)


def _replace_draft(ctx: OperationContext, a: Mapping[str, Any]) -> dict[str, Any]:
    layer = layer_spec(str(a["layer"])).name
    section = a.get("section")
    content = a.get("content")
    data = a.get("data", ABSENT) if "data" in a else ABSENT
    if layer == "bundle":
        _guard_capabilities(ctx.root, section, content, data)
    result = replace_draft(
        ctx.root,
        layer,
        ctx.change,
        expected_sha256=a.get("expected_sha256"),
        content=str(content) if content is not None else None,
        data=data,
        section=str(section) if section else None,
    )
    validation = validate_layer(ctx.root, layer)
    return _edit(result) | {
        "validation": {
            "ready": validation.ready,
            "issues": [item.to_json() for item in validation.issues][:60],
        },
        "note": "saved; the draft does not have to validate yet. Read the issues, "
        "revise and replace again until it does.",
    }


def _guard_capabilities(root: Path, section: Any, content: Any, data: Any) -> None:
    """Assay capabilities change only through the vocabulary-checked tools."""
    current = read_layer(root, "bundle")
    before = (
        (current.draft.data.get("pipeline") or {}).get("assay_capabilities")
        if current.draft is not None and isinstance(current.draft.data, dict)
        else None
    )
    if section is not None:
        pointer = str(section)
        if pointer in {
            "/pipeline",
            "/pipeline/assay_capabilities",
        } or pointer.startswith("/pipeline/assay_capabilities/"):
            after = (
                data.get("assay_capabilities")
                if pointer == "/pipeline" and isinstance(data, Mapping)
                else data
                if pointer == "/pipeline/assay_capabilities"
                else ABSENT
            )
            if after is ABSENT or after != before:
                raise PolicyViolation(
                    "assay capabilities change only through add_assay_capability "
                    "and remove_assay_capability, which check them against the "
                    "vocabulary and the evidence rules"
                )
        return
    if content is not None:
        try:
            parsed = load_yaml_draft(str(content)).data
        except DraftSyntaxError:
            return
    else:
        parsed = data
    after = (
        (parsed.get("pipeline") or {}).get("assay_capabilities")
        if isinstance(parsed, Mapping)
        else None
    )
    if after != before:
        raise PolicyViolation(
            "assay capabilities change only through add_assay_capability and "
            "remove_assay_capability; keep the existing entries unchanged here"
        )


def _read_source(ctx: OperationContext, a: Mapping[str, Any]) -> dict[str, Any]:
    path = _readable(ctx, str(a["path"]))
    if not path.is_file():
        return {"success": False, "issues": [f"{a['path']} is not a file"]}
    raw = path.read_bytes()
    if b"\0" in raw[:8192]:
        return {"success": False, "issues": [f"{a['path']} is a binary file"]}
    lines = raw.decode("utf-8", errors="replace").splitlines()
    start = max(int(a.get("start_line") or 1), 1)
    end = min(int(a.get("end_line") or start + _MAX_LINES - 1), start + _MAX_LINES - 1)
    selected = lines[start - 1 : end]
    text = "\n".join(
        f"{number}: {line}" for number, line in enumerate(selected, start=start)
    )
    data: dict[str, Any] = {
        "path": str(a["path"]),
        "lines": [start, min(end, len(lines))],
        "total_lines": len(lines),
        "text": redact(text[:_MAX_READ_BYTES]),
    }
    if end < len(lines):
        # The toolbox clip (24 000 chars) fires before this byte cap is ever
        # reached through an agent, and its hint names these same arguments;
        # within a window that does fit, say plainly that more lines exist.
        data["next_start_line"] = end + 1
        data["note"] = (
            f"lines {start}-{min(end, len(lines))} of {len(lines)}: call again "
            f"with start_line={end + 1} to continue"
        )
    return _untrusted(data)


def _glob_matches(name: str, relative: str, glob: str) -> bool:
    """A glob matches a file's name (``*.config``) or its relative path
    (``conf/*.config``, ``modules/**/main.nf``; ``**`` spans folders)."""
    return (
        fnmatch.fnmatch(name, glob)
        or fnmatch.fnmatch(relative, glob)
        or (glob.startswith("**/") and fnmatch.fnmatch(relative, glob[3:]))
    )


def _list_files(ctx: OperationContext, a: Mapping[str, Any]) -> dict[str, Any]:
    root = ctx.root.resolve()
    base = _readable(ctx, str(a.get("directory") or "."))
    if not base.is_dir():
        return {"success": False, "issues": [f"{a.get('directory')} is not a folder"]}
    glob = str(a.get("glob") or "*")
    files: list[str] = []
    for current, directories, names in os.walk(base, followlinks=False):
        directories[:] = sorted(
            item for item in directories if item not in _SKIP_DIRECTORIES
        )
        for name in sorted(names):
            path = Path(current) / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink() or _secret_like(path):
                continue
            if _glob_matches(name, relative, glob):
                files.append(relative)
            if len(files) >= _MAX_LISTED:
                return _untrusted({"files": files, "truncated": True})
    return _untrusted(
        {
            "files": files,
            "truncated": False,
            "note": "splice/ holds an earlier published bundle, if any: nf-splice's "
            "own output, never evidence of what the pipeline does",
        }
    )


def _search_source(ctx: OperationContext, a: Mapping[str, Any]) -> dict[str, Any]:
    pattern_text = str(a["pattern"])
    if len(pattern_text) > 200:
        return {"success": False, "issues": ["pattern is longer than 200 characters"]}
    try:
        pattern = re.compile(pattern_text)
    except re.error as error:
        return {"success": False, "issues": [f"invalid regular expression: {error}"]}
    glob = str(a.get("glob") or "*")
    matches: list[str] = []
    root = ctx.root.resolve()
    for current, directories, names in os.walk(root, followlinks=False):
        directories[:] = sorted(
            item for item in directories if item not in _SKIP_DIRECTORIES
        )
        for name in sorted(names):
            path = Path(current) / name
            if (
                path.is_symlink()
                or path.suffix.lower() not in _SEARCH_SUFFIXES
                or _secret_like(path)
                or not _glob_matches(name, path.relative_to(root).as_posix(), glob)
            ):
                continue
            try:
                if path.stat().st_size > 2_000_000:
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            relative = path.relative_to(root).as_posix()
            for number, line in enumerate(text.splitlines(), start=1):
                if pattern.search(line):
                    matches.append(f"{relative}:{number}: {redact(line.strip())[:300]}")
                    if len(matches) >= _MAX_MATCHES:
                        return _untrusted({"matches": matches, "truncated": True})
    return _untrusted({"matches": matches, "truncated": False})


def _list_pending(ctx: OperationContext, a: Mapping[str, Any]) -> dict[str, Any]:
    layer = layer_spec(str(a["layer"])).name
    data: list[Any]
    if layer == "components":
        data = [
            {
                "id": item.id,
                "name": item.name,
                "versions": list(item.versions),
                "proposed_sources": dict(item.proposed_sources),
                "problems": list(item.problems),
            }
            for item in component_layer.pending_components(ctx.root)
        ]
    elif layer == "execution-profiles":
        data = [
            item.model_dump(mode="json")
            for item in execution_layer.pending_profiles(ctx.root)
        ]
    else:
        return {"success": False, "issues": [f"{layer} has no candidate list"]}
    return {"success": True, "count": len(data), "data": data}


def _page(items: list[Any], a: Mapping[str, Any], default: int = 40) -> dict[str, Any]:
    offset = max(int(a.get("offset") or 0), 0)
    limit = min(max(int(a.get("limit") or default), 1), 200)
    page = items[offset : offset + limit]
    following = offset + len(page)
    return {
        "items": page,
        "total": len(items),
        "offset": offset,
        "next_offset": following if following < len(items) else None,
    }


def _route_row(route: Mapping[str, Any]) -> dict[str, Any]:
    publication = route.get("publication") or {}
    return {
        "process": route.get("process"),
        "instance": route.get("instance"),
        "emit": route.get("emit"),
        "declared_path": route.get("declared_path"),
        "published_glob": route.get("published_glob"),
        "status": route.get("status"),
        "conditions": route.get("conditions"),
        "location": publication.get("location"),
        "save_as": publication.get("save_as"),
    }


def _analyse_routes(ctx: OperationContext, a: Mapping[str, Any]) -> dict[str, Any]:
    data = analyse_routes(ctx.root).to_json()
    wanted = str(a.get("process") or "").casefold()

    def selected(route: Mapping[str, Any]) -> bool:
        return not wanted or wanted in str(route.get("instance", "")).casefold()

    detail = bool(a.get("detail"))
    published = [
        route if detail else _route_row(route)
        for route in data["published"]
        if selected(route)
    ]
    return {
        "success": True,
        "data": {
            "entry_workflow": data["entry_workflow"],
            "files_scanned": data["files_scanned"],
            "basis": (
                "one row per declared output nf-splice identified statically; "
                "status_counts counts these. route_coverage counts published "
                "(process instance, published glob) pairs, so its totals "
                "differ from rows and counts here"
            ),
            "status_counts": data["status_counts"],
            "notes": data["notes"],
            "published": _page(published, a),
            "declared_only": _page(
                [
                    {
                        "process": route.get("process"),
                        "emit": route.get("emit"),
                        "declared_path": route.get("declared_path"),
                    }
                    for route in data["unpublished"]
                    if selected(route)
                ],
                {"offset": 0, "limit": a.get("limit")},
            ),
        },
        "note": "page with offset/limit; filter with process; detail=true returns "
        "full records (publication rules, invocations)",
    }


def _route_coverage(ctx: OperationContext, a: Mapping[str, Any]) -> dict[str, Any]:
    from nf_splice.inspectors.routes import glob_examples

    data = output_layer.route_coverage(ctx.root).to_json()
    state = read_layer(ctx.root, "outputs")
    patterns = [
        str(pattern)
        for item in (
            state.draft.data.get("outputs") or []
            if state.draft is not None and isinstance(state.draft.data, dict)
            else []
        )
        if isinstance(item, dict)
        for pattern in item.get("path_patterns") or []
    ]
    for item in data.get("uncovered") or []:
        # The concrete paths each glob was checked as: no pattern matched them.
        item["checked_as"] = {
            glob: glob_examples(glob, patterns)[:4] for glob in item.get("globs") or []
        }
    kind = str(a.get("kind") or "")
    uncovered = [
        item
        for item in data.get("uncovered") or []
        if not kind or item.get("kind") == kind
    ]
    data["uncovered"] = _page(uncovered, a)
    return {"success": True, "data": data}


def _example(ctx: OperationContext, a: Mapping[str, Any]) -> Path:
    index = int(a.get("example", 0))
    if not ctx.examples:
        raise PolicyViolation("no example output was authorised for this session")
    if not 0 <= index < len(ctx.examples):
        raise PolicyViolation(f"example {index} was not authorised")
    return ctx.examples[index]


def _list_examples(ctx: OperationContext, a: Mapping[str, Any]) -> dict[str, Any]:
    enumeration = enumerate_example(_example(ctx, a))
    limit = int(a.get("limit") or 500)
    return {
        "success": True,
        "kind": enumeration.kind.value,
        "entries": len(enumeration.entries),
        "paths": [
            item.path + ("/" if item.is_directory else "")
            for item in enumeration.entries[:limit]
        ],
        "limitations": list(enumeration.limitations),
    }


def _reconcile(ctx: OperationContext, a: Mapping[str, Any]) -> dict[str, Any]:
    catalogue = current_catalogue(ctx.root)
    if catalogue is None:
        return {"success": False, "issues": ["no outputs catalogue exists yet"]}
    result = reconcile_example(catalogue, enumerate_example(_example(ctx, a)))
    return {"success": True, "data": result.to_json()}


def _preview_build(ctx: OperationContext, a: Mapping[str, Any]) -> dict[str, Any]:
    plan = plan_promotion(ctx.root, a.get("layer"))
    document = plan.to_json()
    for change in document["changes"]:
        change["diff"] = change["diff"][:1500]
    return {"success": True, "data": document}


def _validate_layer(ctx: OperationContext, a: Mapping[str, Any]) -> dict[str, Any]:
    validation = validate_layer(ctx.root, layer_spec(str(a["layer"])).name)
    return {
        "success": validation.ready,
        "ready": validation.ready,
        "issues": [item.to_json() for item in validation.issues],
    }


def _validate_bundle(ctx: OperationContext, _a: Mapping[str, Any]) -> dict[str, Any]:
    report = validate_bundle(ctx.root)
    return {
        "success": report.valid,
        "valid": report.valid,
        "issues": [item.to_json() for item in report.issues],
    }


def _assess(ctx: OperationContext, _a: Mapping[str, Any]) -> dict[str, Any]:
    directory = (
        ctx.session_directory / "analysis-output"
        if ctx.session_directory is not None
        else None
    )
    if directory is not None:
        directory.mkdir(parents=True, exist_ok=True)
    result = assess(
        ctx.root,
        examples=ctx.examples,
        permitted=[item.value for item in ctx.policy.grants],
        analysis_output_directory=directory,
        run_checks=False,
    )
    return {"success": True, "data": result.to_json()}


def _explain(_ctx: OperationContext, a: Mapping[str, Any]) -> dict[str, Any]:
    term = str(a["term"]).lower()
    if term not in GLOSSARY:
        return {
            "success": False,
            "issues": [f"unknown term; known: {sorted(GLOSSARY)}"],
        }
    return {"success": True, "data": GLOSSARY[term]}


def _classify(_ctx: OperationContext, a: Mapping[str, Any]) -> dict[str, Any]:
    return {"success": True, "data": classify_reference(str(a["reference"])).value}


def _crate(ctx: OperationContext, _a: Mapping[str, Any]) -> dict[str, Any]:
    from nf_splice.services.crate_review import assess_crate

    return _untrusted(assess_crate(ctx.root))


def _check_crate(ctx: OperationContext, _a: Mapping[str, Any]) -> dict[str, Any]:
    from nf_splice.services.crate_review import check_crate

    return {
        "success": True,
        "data": check_crate(
            ctx.root, permitted=[item.value for item in ctx.policy.grants]
        ),
    }


def _generate_crate(ctx: OperationContext, a: Mapping[str, Any]) -> dict[str, Any]:
    # nf-core's generator is an external program that may use the network.
    ctx.policy.require(Permission.NETWORK)
    run = provenance_layer.generate_with_nf_core(ctx.root, ctx.change, approve=True)
    return {
        "success": True,
        "generator": {
            "version": run.version,
            "returncode": run.returncode,
            "removed_claims": list(run.removed_claims),
        },
        "note": "the generated graph replaced the draft's crate and was corrected "
        "from the reviewed identity; inspect it and run validate_ro_crate",
    }


def _read_skill(_ctx: OperationContext, a: Mapping[str, Any]) -> dict[str, Any]:
    from nf_splice.agents.skills import skill_text

    return {"success": True, "data": skill_text(str(a["name"]))}


def _run_checks(ctx: OperationContext, _a: Mapping[str, Any]) -> dict[str, Any]:
    results = run_optional_checks(
        ctx.root, permitted=[item.value for item in ctx.policy.grants]
    )
    return {"success": True, "data": [item.to_json() for item in results]}


# ------------------------------------------------------------ draft operations


def _initialise(ctx: OperationContext, a: Mapping[str, Any]) -> dict[str, Any]:
    report = initialise(
        ctx.root,
        ctx.change,
        identity=dict(a.get("identity") or {}),
        accept_detected=bool(a.get("accept_detected", False)),
        contract_version=a.get("contract_version"),
    )
    return {
        "success": True,
        "created": list(report.created),
        "preserved": list(report.preserved),
        "identity_conflicts": list(report.identity.conflicts),
        "notes": list(report.notes),
    }


def _search_assays(_ctx: OperationContext, a: Mapping[str, Any]) -> dict[str, Any]:
    from nf_splice.catalogue import default_catalogue

    catalogue = default_catalogue()
    return {
        "success": True,
        "vocabulary": catalogue.provenance.reference(),
        "results": [item.to_json() for item in catalogue.search(str(a["text"]))][:40],
    }


def _vocabulary_assays(_ctx: OperationContext, _a: Mapping[str, Any]) -> dict[str, Any]:
    from nf_splice.catalogue import default_catalogue

    catalogue = default_catalogue()
    codes = {
        item.assay.entity_id: item.registration.code
        for item in catalogue.assays(None, registered_only=True)
        if item.registration is not None
    }
    return {
        "success": True,
        "vocabulary": catalogue.provenance.reference(),
        "assays": [
            {
                "reference": codes.get(
                    item.assay.entity_id, f"entity:{item.assay.entity_id}"
                ),
                "label": item.assay.label,
                "description": item.assay.description,
                "entity_type": item.assay.entity_type.value,
                "modalities": [
                    entry["label"] for entry in item.to_json()["modalities"]
                ],
                "subtypes": [
                    entry["label"] for entry in item.to_json()["modality_subtypes"]
                ],
            }
            for item in catalogue.assays(None, registered_only=False)
        ],
        "note": "the assays a pipeline may declare (reference: a registered code "
        "where one exists, else entity:<id>); which apply is decided from the "
        "pipeline's own code and documentation, never from this list",
    }


def _show_assay(_ctx: OperationContext, a: Mapping[str, Any]) -> dict[str, Any]:
    from nf_splice.catalogue import CatalogueError, default_catalogue

    catalogue = default_catalogue()
    try:
        resolved = catalogue.resolve_reference(str(a["reference"]))
    except CatalogueError as error:
        return {"success": False, "error": error.to_json()}
    registration = resolved.registration
    return {
        "success": True,
        "capability": resolved.to_json(),
        "description": resolved.assay.description,
        "deployment_current": registration.current if registration else None,
        "note": "deployment_current is one deployment's ingestion support; it does "
        "not limit what a pipeline may declare",
    }


def _add_assay(ctx: OperationContext, a: Mapping[str, Any]) -> dict[str, Any]:
    from nf_splice.agents.review_scope import own_output_citations
    from nf_splice.layers.bundle import add_assay_capability

    circular = own_output_citations([str(item) for item in a.get("sources") or ()])
    if circular:
        raise ValueError(
            "an earlier SPLICE bundle or nf-splice's drafts are not evidence of "
            f"the assays a pipeline supports ({', '.join(circular[:3])}); cite "
            "the pipeline's code, configuration or documentation. "
            "read_draft(layer=...) shows what the draft claims, which is your "
            "own output to inspect, never independent evidence"
        )

    return _edit(
        add_assay_capability(
            ctx.root,
            str(a["reference"]),
            ctx.change,
            evidence=str(a["evidence"]),
            rationale=str(a["rationale"]),
            sources=tuple(str(item) for item in a.get("sources") or ()),
        )
    )


def _remove_assay(ctx: OperationContext, a: Mapping[str, Any]) -> dict[str, Any]:
    from nf_splice.layers.bundle import remove_assay_capability

    return _edit(remove_assay_capability(ctx.root, str(a["reference"]), ctx.change))


def _set_identity(ctx: OperationContext, a: Mapping[str, Any]) -> dict[str, Any]:
    changes = dict(a["changes"])
    forbidden = sorted(set(changes) & _HUMAN_ONLY_IDENTITY)
    if forbidden:
        raise PolicyViolation(
            f"{', '.join(forbidden)} is a person's consent decision "
            "(human_consent); an agent can never make it"
        )
    return _edit(set_identity_fields(ctx.root, changes, ctx.change))


def _confirm(ctx: OperationContext, a: Mapping[str, Any]) -> dict[str, Any]:
    layer = layer_spec(str(a["layer"])).name
    pointers = [str(item) for item in a["pointers"]]
    event = confirm_values(ctx.root, layer, pointers, ctx.change)
    return {"success": True, "confirmed": pointers, "event": event.id}


def _sync_identity(ctx: OperationContext, _a: Mapping[str, Any]) -> dict[str, Any]:
    return _edit(input_layer.sync_identity(ctx.root, ctx.change))


def _reimport(ctx: OperationContext, _a: Mapping[str, Any]) -> dict[str, Any]:
    if not (ctx.root / layer_spec("inputs").draft).exists():
        created = input_layer.import_inputs(ctx.root)
        return {"success": created, "imported": created}
    return _edit(input_layer.apply_reimport(ctx.root, ctx.change))


def _set_access(ctx: OperationContext, a: Mapping[str, Any]) -> dict[str, Any]:
    return _edit(
        input_layer.set_access(
            ctx.root,
            [str(item) for item in a["parameters"]],
            [str(item) for item in a["editable_by"]],
            ctx.change,
            visibility=a.get("visibility"),
        )
    )


def _contract_version(ctx: OperationContext, a: Mapping[str, Any]) -> dict[str, Any]:
    """Set the version only with its basis; a chosen value is a proposal."""
    from nf_splice.inspectors.outputs import published_catalogue

    version, basis = str(a["version"]), str(a["basis"])
    rationale = str(a.get("rationale") or "").strip()
    if not rationale:
        raise ValueError("say why this version: rationale is required")
    if basis == "published_catalogue":
        published = published_catalogue(ctx.root)
        declared = published.schema_version if published is not None else None
        if declared != version:
            raise ValueError(
                "basis published_catalogue needs splice/outputs.yaml to declare "
                f"{version}; it declares {declared or 'no version'}"
            )
    result = _edit(output_layer.set_contract_version(ctx.root, version, ctx.change))
    result["basis"] = basis
    if basis == "proposed_initial":
        result["proposed_decision"] = (
            f"Proposed decision: analysis-output schema version {version} (no "
            f"source states one): {rationale}"
        )
    return result


def _add_output(ctx: OperationContext, a: Mapping[str, Any]) -> dict[str, Any]:
    return _edit(output_layer.add_output(ctx.root, dict(a["output"]), ctx.change))


def _remove_output(ctx: OperationContext, a: Mapping[str, Any]) -> dict[str, Any]:
    return _edit(output_layer.remove_output(ctx.root, str(a["key"]), ctx.change))


def _update_output(ctx: OperationContext, a: Mapping[str, Any]) -> dict[str, Any]:
    return _edit(
        output_layer.update_output(
            ctx.root, str(a["key"]), dict(a["changes"]), ctx.change
        )
    )


def _discover_components(
    ctx: OperationContext, _a: Mapping[str, Any]
) -> dict[str, Any]:
    found = component_layer.discover_components(ctx.root)
    return {"success": True, "pending": [item.id for item in found]}


def _accept_component(ctx: OperationContext, a: Mapping[str, Any]) -> dict[str, Any]:
    sources = a.get("sources")
    return _edit(
        component_layer.accept_component(
            ctx.root,
            str(a["candidate_id"]),
            ctx.change,
            version=a.get("version"),
            sources=dict(sources) if sources else None,
        )
    )


def _accept_unambiguous(ctx: OperationContext, _a: Mapping[str, Any]) -> dict[str, Any]:
    accepted = component_layer.accept_unambiguous_components(ctx.root, ctx.change)
    return {"success": True, "accepted": list(accepted)}


def _reject_component(ctx: OperationContext, a: Mapping[str, Any]) -> dict[str, Any]:
    component_layer.reject_component(
        ctx.root, str(a["candidate_id"]), str(a["reason"]), ctx.change
    )
    return {"success": True, "rejected": a["candidate_id"]}


def _image_policy(ctx: OperationContext, a: Mapping[str, Any]) -> dict[str, Any]:
    return _edit(
        component_layer.set_image_policy(
            ctx.root, bool(a["require_downloadable"]), ctx.change
        )
    )


def _discover_profiles(ctx: OperationContext, _a: Mapping[str, Any]) -> dict[str, Any]:
    found = execution_layer.discover_execution(ctx.root)
    return {"success": True, "pending": [item.id for item in found]}


def _review_profile(ctx: OperationContext, a: Mapping[str, Any]) -> dict[str, Any]:
    generate: dict[str, dict[str, Any]] | None = (
        {"process": {}, "user_params": {}, "platform_params": {}}
        if a.get("generate")
        else None
    )
    return _edit(
        execution_layer.review_profile(
            ctx.root,
            str(a["candidate_id"]),
            ctx.change,
            profile_type=str(a["profile_type"]),
            description=str(a["description"]),
            executor=str(a["executor"]),
            container_engine=a.get("container_engine"),
            config_source=a.get("config_source"),
            generate=generate,
        )
    )


def _reject_profile(ctx: OperationContext, a: Mapping[str, Any]) -> dict[str, Any]:
    execution_layer.reject_profile(
        ctx.root, str(a["candidate_id"]), str(a["reason"]), ctx.change
    )
    return {"success": True, "rejected": a["candidate_id"]}


def _update_profile(ctx: OperationContext, a: Mapping[str, Any]) -> dict[str, Any]:
    return _edit(
        execution_layer.update_profile(
            ctx.root, str(a["identifier"]), dict(a["changes"]), ctx.change
        )
    )


def _default_profile(ctx: OperationContext, a: Mapping[str, Any]) -> dict[str, Any]:
    return _edit(
        execution_layer.set_default_profile(ctx.root, str(a["profile_id"]), ctx.change)
    )


def _slurm(ctx: OperationContext, _a: Mapping[str, Any]) -> dict[str, Any]:
    return _edit(execution_layer.add_slurm_default_candidate(ctx.root, ctx.change))


def _provenance(ctx: OperationContext, a: Mapping[str, Any]) -> dict[str, Any]:
    from nf_splice.services.crate_review import STRATEGIES

    strategy = STRATEGIES.get(str(a["strategy"]))
    if strategy == "adopt":
        result = provenance_layer.choose_include(ctx.root, ctx.change)
    elif strategy == "correct":
        result = provenance_layer.prepare_enrichment(ctx.root, ctx.change)
    elif strategy == "regenerate":
        result = provenance_layer.generate_minimal(
            ctx.root,
            ctx.change,
            main_workflow=str(a.get("main_workflow") or "main.nf"),
        )
    else:
        raise LayerError("strategy must be adopt, correct or regenerate")
    return _edit(result)


def _patch(ctx: OperationContext, a: Mapping[str, Any]) -> dict[str, Any]:
    layer = layer_spec(str(a["layer"])).name
    for operation in a["operations"]:
        path = str(dict(operation).get("path", ""))
        if layer == "bundle" and path.startswith(
            ("/pipeline/assay_capabilities", "/pipeline/modality")
        ):
            raise PolicyViolation(
                "assay capabilities change only through add_assay_capability and "
                "remove_assay_capability, which check them against the vocabulary"
            )
    operations = [dict(item) for item in a["operations"]]
    result = apply_patch(
        ctx.root,
        layer_spec(str(a["layer"])).name,
        operations,
        ctx.change,
    )
    payload = _edit(result)
    if not result.wrote and isinstance(result.data, dict):
        from nf_splice.drafts.patch import PatchOp, replay_note

        # A patch that changed nothing because the draft already held the
        # values is tolerated; a caller who named wrong bases must hear so.
        note = replay_note(
            result.data, [PatchOp.from_json(item) for item in operations]
        )
        if note:
            payload["note"] = note
    return payload


def _build(ctx: OperationContext, a: Mapping[str, Any]) -> dict[str, Any]:
    replace = bool(a.get("replace_existing", False))
    overwrite = [str(item) for item in a.get("overwrite_edited") or []]
    if replace or overwrite:
        ctx.policy.require(Permission.OVERWRITE)
    result = promote(
        ctx.root,
        None,
        ctx.change,
        replace_existing=replace,
        overwrite_edited=overwrite,
    )
    report = validate_bundle(ctx.root)
    return {
        "success": report.valid,
        "wrote": [f"splice/{item}" for item in result.wrote],
        "valid": report.valid,
        "issues": [item.to_json() for item in report.issues],
    }


def _git_commit(ctx: OperationContext, a: Mapping[str, Any]) -> dict[str, Any]:
    from nf_splice import __version__
    from nf_splice.services import gitops

    session = ctx.session_directory.name if ctx.session_directory else "manual"
    result = gitops.commit(
        ctx.root,
        str(a.get("message") or "Publish the SPLICE workflow bundle"),
        trailer=f"Prepared-with: nf-splice {__version__} ({session})",
    )
    return {"success": True, **result}


# ------------------------------------------------------------ registry


def _read_config(ctx: OperationContext, a: Mapping[str, Any]) -> dict[str, Any]:
    if not a.get("name"):
        return {
            "success": True,
            "data": {
                "configs": list(execution_layer.list_config_drafts(ctx.root)),
                "note": "authored Nextflow configs of the execution profiles; "
                "read one by name",
            },
        }
    found = execution_layer.read_config_draft(ctx.root, str(a["name"]))
    if found["text"] is not None:
        found["text"] = redact(str(found["text"]))[:_MAX_READ_BYTES]
    return _untrusted(found)


def _write_config(ctx: OperationContext, a: Mapping[str, Any]) -> dict[str, Any]:
    result = execution_layer.write_config_draft(
        ctx.root,
        str(a["name"]),
        str(a["text"]),
        ctx.change,
        expected_sha256=a.get("expected_sha256"),
    )
    validation = validate_layer(ctx.root, "execution-profiles")
    return _edit(result) | {
        "validation": {
            "ready": validation.ready,
            "issues": [item.to_json() for item in validation.issues][:60],
        }
    }


def _parameter_usage(ctx: OperationContext, a: Mapping[str, Any]) -> dict[str, Any]:
    state = read_layer(ctx.root, "inputs")
    declared = (
        {item.name for item in input_layer.iter_parameters(state.draft.data)}
        if state.draft is not None and isinstance(state.draft.data, dict)
        else set()
    )
    usage = parameter_usage(ctx.root)
    name = str(a.get("name") or "").removeprefix("params.")
    if name:
        reference = usage.references.get(name)
        return {
            "success": True,
            "data": reference.to_json(declared)
            if reference is not None
            else {"name": name, "classification": "not referenced", "code": []},
        }
    return {"success": True, "data": usage.to_json(declared)}


def _contract_reference(_ctx: OperationContext, a: Mapping[str, Any]) -> dict[str, Any]:
    return {"success": True, "data": authorable_contract(str(a["layer"]))}


def _component_inventory(ctx: OperationContext, a: Mapping[str, Any]) -> dict[str, Any]:
    discovered = component_layer.discovered_modules(ctx.root)
    needle = str(a.get("name") or "").casefold()
    if needle:
        discovered = [
            item
            for item in discovered
            if needle in str(item.get("name", "")).casefold()
            or needle in str(item.get("path", "")).casefold()
        ]
    page = _page(discovered, a, default=10)
    return {
        "success": True,
        "count": page["total"],
        "summary": {
            "count": page["total"],
            "needs_decision": sum(1 for item in discovered if item.get("problems")),
            "modules": [
                f"{item.get('name')} ({item.get('path')})" for item in discovered
            ],
        },
        "items": page["items"],
        "offset": page["offset"],
        "next_offset": page["next_offset"],
        "note": "summary lists every module name; full rows come a page at a "
        "time (offset/limit; filter with name). tool_name_basis says where a "
        "tool name came from; a module or process name is only a placeholder: "
        "name the tool the code runs when you can establish it",
    }


def _analyse_execution(ctx: OperationContext, a: Mapping[str, Any]) -> dict[str, Any]:
    text = None
    if a.get("config"):
        found = execution_layer.read_config_draft(ctx.root, str(a["config"]))
        text = found["text"]
        if text is None:
            return {"success": False, "issues": [f"{found['path']} does not exist"]}
    return {"success": True, "data": analyse_execution(ctx.root, text)}


_OUTPUT_OBJECT = {
    "type": "object",
    "description": "Complete reviewed output: key, title, description, category, "
    "formats, scopes (job/sample/run), entity_types, path_patterns; optional "
    "stage and labels.",
}
_R, _D, _B = Permission.READ, Permission.DRAFT_EDIT, Permission.BUILD

OPERATIONS: dict[str, Operation] = {
    item.name: item
    for item in (
        Operation(
            "workspace_status",
            "Layer states, warnings and readiness of every draft.",
            _obj(),
            _R,
            "read",
            _workspace_status,
        ),
        Operation(
            "inspect_draft",
            "Per-field issues of one draft.",
            _obj({"layer": _LAYER}, ["layer"]),
            _R,
            "read",
            _inspect_draft,
        ),
        Operation(
            "read_draft",
            "One draft's parsed data and its sha256 (needed to replace it). "
            "section: a JSON pointer to read one part (/outputs/2, "
            "/$defs/input_output_options; / is the whole draft); yaml=true "
            "also returns the YAML text with comments. Untrusted repository "
            "content.",
            _obj(
                {
                    "layer": _LAYER,
                    "section": {"type": "string"},
                    "yaml": {"type": "boolean"},
                },
                ["layer"],
            ),
            _R,
            "read",
            _read_draft,
        ),
        Operation(
            "contract_reference",
            "The complete authorable structure of one layer's draft: every field, "
            "its type and meaning, what is draft-only and what the build owns.",
            _obj({"layer": _LAYER}, ["layer"]),
            _R,
            "read",
            _contract_reference,
        ),
        Operation(
            "replace_draft",
            "Author a draft: replace the whole file (content: complete YAML "
            "text, keeping the x-splice-draft block) or one section (section: a "
            "JSON pointer such as /outputs, data: its new value). expected_sha256 "
            "is the sha256 read_draft returned; if the file changed since, the "
            "write is refused. The result need not validate yet: it is saved and "
            "the validation issues are returned so you can revise.",
            _obj(
                {
                    "layer": _LAYER,
                    "expected_sha256": {"type": ["string", "null"]},
                    "content": {"type": "string"},
                    "section": {"type": "string"},
                    "data": {},
                },
                ["layer", "expected_sha256"],
            ),
            _D,
            "draft",
            _replace_draft,
            layer_argument=True,
        ),
        Operation(
            "read_config",
            "List the execution profiles' native Nextflow config files (no name), "
            "or read one by name: its text and sha256.",
            _obj({"name": {"type": "string"}}),
            _R,
            "read",
            _read_config,
        ),
        Operation(
            "write_config",
            "Create (expected_sha256 null) or replace a native Nextflow config "
            "of an execution profile, as complete text. Saved even if it does "
            "not validate yet; secrets are refused. Register a new file in the "
            "profile draft with config: {draft: <name>.draft.config}.",
            _obj(
                {
                    "name": {"type": "string"},
                    "text": {"type": "string"},
                    "expected_sha256": {"type": ["string", "null"]},
                },
                ["name", "text", "expected_sha256"],
            ),
            _D,
            "draft",
            _write_config,
        ),
        Operation(
            "parameter_usage",
            "Where workflow code and configs read params.*. Without name: a "
            "summary (undeclared executable references, values configs set for "
            "themselves, comment-only mentions, declared-but-unused parameters). "
            "With name: that parameter's file:line locations in code and configs.",
            _obj({"name": {"type": "string"}}),
            _R,
            "read",
            _parameter_usage,
        ),
        Operation(
            "component_inventory",
            "Every module discovered. Returns a summary first (count, how many "
            "need a decision, every module name), then full rows (tool, "
            "versions, conda packages, runtime-specific container references) "
            "a page at a time: offset/limit, filter with name.",
            _obj(
                {
                    "name": {"type": "string"},
                    "offset": {"type": "integer"},
                    "limit": {"type": "integer"},
                }
            ),
            _R,
            "read",
            _component_inventory,
        ),
        Operation(
            "analyse_execution",
            "Resource selectors (withLabel/withName), processes by label, every "
            "task.memory use and whether it is guarded; with config (a profile "
            "config name) also its executor, memory = null coverage, memory per "
            "core and the CPUs each selector needs for its intended memory.",
            _obj({"config": {"type": "string"}}),
            _R,
            "read",
            _analyse_execution,
        ),
        Operation(
            "read_source",
            "Read lines of a repository text file, for example main.nf or a "
            "module (untrusted content; secrets files are refused).",
            _obj(
                {
                    "path": {"type": "string"},
                    "start_line": {"type": "integer", "minimum": 1},
                    "end_line": {"type": "integer", "minimum": 1},
                },
                ["path"],
            ),
            _R,
            "read",
            _read_source,
        ),
        Operation(
            "search_source",
            "Search repository text files (.nf, .config, .json, .yml, .md and "
            "similar) with a regular expression; returns path:line: text. glob "
            "filters by file name (*.config) or relative path (conf/*.config, "
            "modules/**/main.nf).",
            _obj(
                {"pattern": {"type": "string"}, "glob": {"type": "string"}},
                ["pattern"],
            ),
            _R,
            "read",
            _search_source,
        ),
        Operation(
            "list_files",
            "List repository files below a folder (default the root), "
            "optionally filtered by a glob on the name or relative path. Use it "
            "to find what exists before reading.",
            _obj(
                {"directory": {"type": "string"}, "glob": {"type": "string"}},
                [],
            ),
            _R,
            "read",
            _list_files,
        ),
        Operation(
            "list_pending",
            "Modules or repository execution profiles found in the source but "
            "not yet in the draft (hints, not a review queue). Published output "
            "routes are listed by route_coverage.",
            _obj(
                {
                    "layer": {
                        "type": "string",
                        "enum": ["components", "execution-profiles"],
                    },
                    "include_decided": {"type": "boolean"},
                },
                ["layer"],
            ),
            _R,
            "read",
            _list_pending,
        ),
        Operation(
            "route_coverage",
            "Which published routes the output catalogue covers, which are "
            "excluded with a reason, and which are uncovered (established, "
            "conditional or unverified). Coverage is ingestion-readiness "
            "evidence, never a validation error of declared outputs. Uncovered "
            "routes are paged (offset, limit), filtered by kind, and show the "
            "example paths each glob was checked as ({meta.id} as ID1, * as x).",
            _obj(
                {
                    "kind": {
                        "type": "string",
                        "enum": ["established", "conditional", "unverified"],
                    },
                    "offset": {"type": "integer", "minimum": 0},
                    "limit": {"type": "integer", "minimum": 1},
                }
            ),
            _R,
            "read",
            _route_coverage,
        ),
        Operation(
            "analyse_routes",
            "Static publication routes: published versus declared-only outputs, "
            "with conditions, statuses and publish-rule locations. Compact rows, "
            "paged (offset, limit); process filters by name; detail=true returns "
            "full records.",
            _obj(
                {
                    "process": {"type": "string"},
                    "offset": {"type": "integer", "minimum": 0},
                    "limit": {"type": "integer", "minimum": 1},
                    "detail": {"type": "boolean"},
                }
            ),
            _R,
            "read",
            _analyse_routes,
        ),
        Operation(
            "list_example_outputs",
            "List an authorised example results tree (one run's evidence).",
            _obj(
                {
                    "example": {"type": "integer", "minimum": 0},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 5000},
                }
            ),
            _R,
            "read",
            _list_examples,
        ),
        Operation(
            "reconcile_example_outputs",
            "Classify an example's paths against the current catalogue: "
            "classified, unclassified, ambiguous and not observed.",
            _obj({"example": {"type": "integer", "minimum": 0}}),
            _R,
            "read",
            _reconcile,
        ),
        Operation(
            "preview_build",
            "Blockers and file diffs a build would produce (no write).",
            _obj({"layer": {"type": ["string", "null"], "enum": [*LAYER_NAMES, None]}}),
            _R,
            "read",
            _preview_build,
        ),
        Operation(
            "validate_layer",
            "Deterministic validation of one draft.",
            _obj({"layer": _LAYER}, ["layer"]),
            _R,
            "read",
            _validate_layer,
        ),
        Operation(
            "validate_bundle",
            "Deterministic validation of the published bundle.",
            _obj(),
            _R,
            "read",
            _validate_bundle,
        ),
        Operation(
            "assess",
            "Contract validity, observed-output compatibility and route coverage, "
            "as three separate results.",
            _obj(),
            _R,
            "read",
            _assess,
        ),
        Operation(
            "explain_term",
            "Precise SPLICE meaning of a vocabulary term.",
            _obj({"term": {"type": "string"}}, ["term"]),
            _R,
            "read",
            _explain,
        ),
        Operation(
            "classify_container",
            "Classify a container reference offline.",
            _obj({"reference": {"type": "string"}}, ["reference"]),
            _R,
            "read",
            _classify,
        ),
        Operation(
            "analyse_ro_crate",
            "Assess the repository's own RO-Crate and the authored draft graph: "
            "findings, whether to keep, adopt, correct or regenerate (with "
            "reasons), and whether nf-core's generator and rocrate-validator are "
            "installed and applicable.",
            _obj(),
            _R,
            "read",
            _crate,
        ),
        Operation(
            "validate_ro_crate",
            "Check the draft graph as it would be published: nf-splice's "
            "structural checks, and Workflow RO-Crate standards validation with "
            "rocrate-validator when installed and permitted (external_tools; "
            "network, or it runs offline). The two results are separate: "
            "passed, failed, not_run or not_applicable.",
            _obj(),
            _R,
            "read",
            _check_crate,
        ),
        Operation(
            "read_skill",
            "Read one nf-splice skill (procedure) by name.",
            _obj({"name": {"type": "string"}}, ["name"]),
            _R,
            "read",
            _read_skill,
        ),
        Operation(
            "run_optional_checks",
            "Run optional external checks (nf-core lint) that the policy permits; "
            "unavailable or unpermitted checks are reported as not run.",
            _obj(),
            _R,
            "read",
            _run_checks,
        ),
        Operation(
            "initialise_drafts",
            "Create absent drafts from repository evidence (never overwrites).",
            _obj(
                {
                    "identity": {"type": "object"},
                    "accept_detected": {"type": "boolean"},
                    "contract_version": {"type": "string"},
                }
            ),
            _D,
            "draft",
            _initialise,
        ),
        Operation(
            "list_vocabulary_assays",
            "Every assay in the pinned SPLICE vocabulary, with its reference, "
            "type, modality subtypes and modalities: what may be declared.",
            _obj(),
            _R,
            "read",
            _vocabulary_assays,
        ),
        Operation(
            "search_assay_catalogue",
            "Search the SPLICE assay and modality vocabulary by label, alias, "
            "registered code or entity id. Shows exact entity types and every path.",
            _obj({"text": {"type": "string", "minLength": 1}}, ["text"]),
            _R,
            "read",
            _search_assays,
        ),
        Operation(
            "show_assay",
            "Resolve one assay (registered code such as polya_rnaseq, or "
            "entity:<id>) to its type, assay types, modality subtypes, modalities "
            "and every path.",
            _obj({"reference": {"type": "string", "minLength": 1}}, ["reference"]),
            _R,
            "read",
            _show_assay,
        ),
        Operation(
            "add_assay_capability",
            "Declare an assay the pipeline can process, by registered code or "
            "entity:<id>, citing documented or detected evidence (path:line), or "
            "'confirmed' with the person's answer as the source (AI-assisted only, "
            "applied after their approval). Only a person may assert a capability "
            "without evidence.",
            _obj(
                {
                    "reference": {"type": "string", "minLength": 1},
                    "evidence": {"enum": ["documented", "detected", "confirmed"]},
                    "rationale": {"type": "string", "minLength": 1},
                    "sources": {**_STRINGS, "minItems": 1},
                },
                ["reference", "evidence", "rationale", "sources"],
            ),
            _D,
            "draft",
            _add_assay,
        ),
        Operation(
            "remove_assay_capability",
            "Remove a declared assay capability by registered code or entity:<id>.",
            _obj({"reference": {"type": "string", "minLength": 1}}, ["reference"]),
            _D,
            "draft",
            _remove_assay,
        ),
        Operation(
            "set_identity",
            "Set identity fields in bundle.draft.yaml (e.g. title, licence, "
            "description, authors). Publication consent is a person's decision.",
            _obj({"changes": {"type": "object"}}, ["changes"]),
            _D,
            "draft",
            _set_identity,
        ),
        Operation(
            "confirm_values",
            "Confirm detected draft values at JSON pointers after checking them.",
            _obj({"layer": _LAYER, "pointers": _STRINGS}, ["layer", "pointers"]),
            _D,
            "draft",
            _confirm,
            layer_argument=True,
        ),
        Operation(
            "sync_identity",
            "Copy the reviewed identity into the inputs draft.",
            _obj(),
            _D,
            "draft",
            _sync_identity,
        ),
        Operation(
            "reimport_inputs",
            "Import or re-import nextflow_schema.json into the inputs draft.",
            _obj(),
            _D,
            "draft",
            _reimport,
        ),
        Operation(
            "set_parameter_access",
            "Set who may edit parameters (user, platform, agent; empty for "
            "nobody) and optionally visibility (standard, advanced, hidden).",
            _obj(
                {
                    "parameters": _STRINGS,
                    "editable_by": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["user", "platform", "agent"],
                        },
                    },
                    "visibility": {
                        "type": "string",
                        "enum": ["standard", "advanced", "hidden"],
                    },
                },
                ["parameters", "editable_by"],
            ),
            _D,
            "draft",
            _set_access,
        ),
        Operation(
            "set_output_contract_version",
            "Set the analysis-output schema version (X.Y.Z). It versions the "
            "shape of this workflow's analysis_output.json, never the pipeline "
            "release. basis: published_catalogue (the version an existing "
            "splice/outputs.yaml declares; it must match), stated_by_person (a "
            "person gave it; cite where in rationale) or proposed_initial (no "
            "source states one: you propose a first version, recorded as a "
            "decision for a person to confirm).",
            _obj(
                {
                    "version": {"type": "string"},
                    "basis": {
                        "type": "string",
                        "enum": [
                            "published_catalogue",
                            "stated_by_person",
                            "proposed_initial",
                        ],
                    },
                    "rationale": {"type": "string"},
                },
                ["version", "basis", "rationale"],
            ),
            _D,
            "draft",
            _contract_version,
        ),
        Operation(
            "add_output",
            "Add one complete output to the catalogue.",
            _obj({"output": _OUTPUT_OBJECT}, ["output"]),
            _D,
            "draft",
            _add_output,
        ),
        Operation(
            "remove_output",
            "Remove one output from the catalogue by key.",
            _obj({"key": {"type": "string"}}, ["key"]),
            _D,
            "draft",
            _remove_output,
        ),
        Operation(
            "update_output",
            "Change fields of a reviewed output by key.",
            _obj(
                {"key": {"type": "string"}, "changes": {"type": "object"}},
                ["key", "changes"],
            ),
            _D,
            "draft",
            _update_output,
        ),
        Operation(
            "discover_components",
            "Rediscover module components and container sources.",
            _obj(),
            _D,
            "draft",
            _discover_components,
        ),
        Operation(
            "accept_component",
            "Accept a component candidate, optionally with version and sources.",
            _obj(
                {
                    "candidate_id": {"type": "string"},
                    "version": {"type": "string"},
                    "sources": {"type": "object"},
                },
                ["candidate_id"],
            ),
            _D,
            "draft",
            _accept_component,
        ),
        Operation(
            "accept_unambiguous_components",
            "Accept every component whose evidence is unambiguous.",
            _obj(),
            _D,
            "draft",
            _accept_unambiguous,
        ),
        Operation(
            "reject_component",
            "Reject a component candidate with a reason.",
            _obj(
                {"candidate_id": {"type": "string"}, "reason": {"type": "string"}},
                ["candidate_id", "reason"],
            ),
            _D,
            "draft",
            _reject_component,
        ),
        Operation(
            "set_image_policy",
            "Whether every image must have a verified downloadable distribution.",
            _obj(
                {"require_downloadable": {"type": "boolean"}}, ["require_downloadable"]
            ),
            _D,
            "draft",
            _image_policy,
        ),
        Operation(
            "discover_profiles",
            "Rediscover execution profiles from nextflow.config.",
            _obj(),
            _D,
            "draft",
            _discover_profiles,
        ),
        Operation(
            "review_profile",
            "Review one profile candidate: type, description, executor and an "
            "adopted config source or a generated config. container_engine is "
            "optional execution metadata: omit it when the profile declares no "
            "runtime; never invent one. To complete a profile already in the "
            "draft (the seeded default), use update_profile instead.",
            _obj(
                {
                    "candidate_id": {"type": "string"},
                    "profile_type": {"type": "string"},
                    "description": {"type": "string"},
                    "executor": {"type": "string"},
                    "container_engine": {
                        "type": ["string", "null"],
                        "description": "optional; omit or null when no runtime "
                        "is declared",
                    },
                    "config_source": {"type": "string"},
                    "generate": {"type": "boolean"},
                },
                ["candidate_id", "profile_type", "description", "executor"],
            ),
            _D,
            "draft",
            _review_profile,
        ),
        Operation(
            "update_profile",
            "Complete or correct a profile already in the draft (including "
            "the seeded default): name, description, type, executor, "
            "container_engine or the config pointer. container_engine is "
            "optional metadata: leave it unchanged when nothing declares "
            "one; never invent one.",
            _obj(
                {"identifier": {"type": "string"}, "changes": {"type": "object"}},
                ["identifier", "changes"],
            ),
            _D,
            "draft",
            _update_profile,
        ),
        Operation(
            "reject_profile",
            "Reject a profile candidate with a reason.",
            _obj(
                {"candidate_id": {"type": "string"}, "reason": {"type": "string"}},
                ["candidate_id", "reason"],
            ),
            _D,
            "draft",
            _reject_profile,
        ),
        Operation(
            "set_default_profile",
            "Choose the single default execution profile by ID.",
            _obj({"profile_id": {"type": "string"}}, ["profile_id"]),
            _D,
            "draft",
            _default_profile,
        ),
        Operation(
            "add_slurm_default_profile",
            "Add the generated SPLICE Slurm profile candidate.",
            _obj(),
            _D,
            "draft",
            _slurm,
        ),
        Operation(
            "provenance_strategy",
            "Start the authored graph afresh: adopt the repository's own crate, "
            "correct a copy of it from the reviewed identity, or regenerate one "
            "from the identity. Replaces the draft's crate.",
            _obj(
                {
                    "strategy": {
                        "type": "string",
                        "enum": ["adopt", "correct", "regenerate"],
                    },
                    "main_workflow": {"type": "string"},
                },
                ["strategy"],
            ),
            _D,
            "draft",
            _provenance,
        ),
        Operation(
            "generate_ro_crate",
            "Generate a candidate graph with nf-core's `pipelines rocrate`, on an "
            "isolated copy of the pipeline (never the original), when nf-core is "
            "installed; needs external_tools and network. Reviewed identity "
            "values are applied and nf-co.re hosting claims removed for "
            "pipelines that are not nf-core's; the result replaces the draft's "
            "crate. nf-splice never installs nf-core.",
            _obj(),
            Permission.EXTERNAL_TOOLS,
            "draft",
            _generate_crate,
        ),
        Operation(
            "patch_draft",
            "Field-level changes to the current stage's draft, merged three-way "
            "and validated. Each operation is {op: add|replace|remove, path: JSON "
            "pointer such as /outputs/2/description, value: the new value (not "
            "for remove), expected: the value you read there (optional: with it, "
            "the patch is refused if the file changed there since; without it, "
            "replace and remove accept the current value; add still needs a free "
            "location)}. For a whole section use replace_draft.",
            _obj(
                {
                    "layer": _LAYER,
                    "operations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "op": {
                                    "type": "string",
                                    "enum": ["add", "replace", "remove"],
                                },
                                "path": {"type": "string"},
                                "value": {},
                                "expected": {},
                            },
                            "required": ["op", "path"],
                        },
                    },
                },
                ["layer", "operations"],
            ),
            _D,
            "draft",
            _patch,
            layer_argument=True,
        ),
        Operation(
            "git_commit",
            "Commit the validated splice/ and .gitignore to the local branch.",
            _obj({"message": {"type": "string"}}),
            Permission.GIT_COMMIT,
            "build",
            _git_commit,
        ),
        Operation(
            "build_bundle",
            "Publish the validated drafts into splice/ (transactional, recoverable).",
            _obj(
                {
                    "replace_existing": {"type": "boolean"},
                    "overwrite_edited": _STRINGS,
                }
            ),
            _B,
            "build",
            _build,
        ),
    )
}

#: Session-control tools: recorded by the engine, never touching files.
CONTROL_SCHEMAS: dict[str, dict[str, Any]] = {
    "review_scope": {
        "name": "review_scope",
        "description": "The evidence this stage's review must and should inspect "
        "in this pipeline (its workflow files, publishing configs, unresolved "
        "modules, profile configs, crate, ...), what you have inspected so far, "
        "the gaps, and calls that would close them. Call it before finishing.",
        "input_schema": _obj(),
    },
    "submit_stage_proposal": {
        "name": "submit_stage_proposal",
        "description": "Finish planning: summarise the staged changes, the evidence "
        "that supports them (files as path or path:line, or the analyses you "
        "ran), the uncertainties and the validation that will decide the stage. "
        "Refused while required review evidence is uninspected (see review_scope).",
        "input_schema": _obj(
            {
                "summary": {"type": "string"},
                "evidence": {**_STRINGS, "minItems": 1},
                "uncertainties": _STRINGS,
                "validation_gate": {"type": "string"},
            },
            ["summary", "evidence"],
        ),
    },
    "assess_objection": {
        "name": "assess_objection",
        "description": "Record whether the user's concern is supported by the "
        "evidence you checked, and why.",
        "input_schema": _obj(
            {
                "assessment": {
                    "type": "string",
                    "enum": [
                        "supported",
                        "partly_supported",
                        "not_supported",
                        "unclear",
                    ],
                },
                "explanation": {"type": "string"},
                "evidence": _STRINGS,
            },
            ["assessment", "explanation"],
        ),
    },
    "complete_review": {
        "name": "complete_review",
        "description": "Finish reviewing the current stage's draft against the "
        "pipeline, whether or not you changed it. Give your assessment of the "
        "draft (omissions, incorrect assumptions, unsupported declarations, and "
        "what you confirmed against the evidence), the evidence for your "
        "conclusions (files as path or path:line that you read, or the analyses "
        "you ran) and what stays uncertain. Refused while required evidence for "
        "this stage is uninspected (see review_scope), when evidence cites a file "
        "you never read, or when an unchanged draft has no confirmations.",
        "input_schema": _obj(
            {
                "summary": {"type": "string"},
                "checked": _STRINGS,
                "findings": _STRINGS,
                "uncertainties": _STRINGS,
                "evidence": {**_STRINGS, "minItems": 1},
                "draft_assessment": _obj(
                    {
                        "omissions": _STRINGS,
                        "incorrect_assumptions": _STRINGS,
                        "unsupported_declarations": _STRINGS,
                        "confirmed": _STRINGS,
                    },
                    [
                        "omissions",
                        "incorrect_assumptions",
                        "unsupported_declarations",
                        "confirmed",
                    ],
                ),
            },
            ["summary", "checked", "evidence", "draft_assessment"],
        ),
    },
    "record_blocker": {
        "name": "record_blocker",
        "description": "Record a decision you cannot make with sufficient "
        "evidence. A person reads it: write plain sentences, not tool payloads. "
        "decision: what the person must decide or supply; reason: why you "
        "cannot decide it; attempted_checks: the sources you read and analyses "
        "you ran (file:line or tool name); uncertainties: what remains "
        "unknown; suggested_resolution: what the person should do next; "
        "pointer: the JSON pointer of the field in the stage's draft; "
        "artefact: the file concerned (defaults to the stage's draft).",
        "input_schema": _obj(
            {
                "decision": {"type": "string"},
                "reason": {"type": "string"},
                "uncertainties": _STRINGS,
                "artefact": {"type": "string"},
                "pointer": {
                    "type": "string",
                    "description": "JSON pointer of the field or entry in the "
                    "stage's draft that needs the decision, e.g. /outputs/2/scopes",
                },
                "attempted_checks": _STRINGS,
                "suggested_resolution": {"type": "string"},
            },
            ["decision"],
        ),
    },
    "record_evidence": {
        "name": "record_evidence",
        "description": "Record a claim with its support: observed, "
        "statically_inferred or unresolved, and its sources (file:line).",
        "input_schema": _obj(
            {
                "claim": {"type": "string"},
                "status": {
                    "type": "string",
                    "enum": ["observed", "statically_inferred", "unresolved"],
                },
                "sources": _STRINGS,
            },
            ["claim", "status"],
        ),
    },
}

READ_OPERATIONS = frozenset(
    name for name, item in OPERATIONS.items() if item.kind == "read"
)


def describe(name: str, arguments: Mapping[str, Any]) -> str:
    """Short human-readable summary of a planned operation."""
    text = json.dumps(dict(arguments), sort_keys=True, default=str)
    return f"{name} {redact(text)[:300]}"
