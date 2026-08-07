"""Discover, review, and persist workflow software inventory decisions."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]
from pydantic import ValidationError

from nf_splice.domain import (
    AuthoringDocument,
    ComponentCandidate,
    Decision,
    DecisionStatus,
    Evidence,
    EvidenceProvenance,
    LayerState,
    ReviewedComponent,
    UnresolvedDecision,
)
from nf_splice.services.authoring import (
    load_repository_document,
    save_repository_document,
)


class ComponentReviewError(ValueError):
    """Raised when software evidence is invalid or needs explicit resolution."""


_QUOTED = re.compile(r"['\"]([^'\"\n]+)['\"]")
_SEMVER = re.compile(r"^v?(\d+(?:\.\d+)+(?:[-+][A-Za-z0-9_.-]+)?)")


def _replace_layer(
    layers: tuple[LayerState, ...], replacement: LayerState
) -> tuple[LayerState, ...]:
    retained = [item for item in layers if item.name != replacement.name]
    retained.append(replacement)
    return tuple(sorted(retained, key=lambda item: item.name))


def _module_items(root: Path) -> tuple[dict[str, Any], ...]:
    path = root / "modules.json"
    if not path.is_file():
        raise ComponentReviewError("modules.json is required for component discovery")
    try:
        loaded: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ComponentReviewError(f"invalid modules.json: {error}") from error
    if not isinstance(loaded, dict) or not isinstance(loaded.get("items"), list):
        raise ComponentReviewError("modules.json must contain an items array")
    return tuple(
        item
        for item in loaded["items"]
        if isinstance(item, dict) and item.get("kind") == "module"
    )


def _metadata(path: Path) -> dict[str, Any]:
    for name in ("meta.yml", "meta.yaml"):
        candidate = path / name
        if not candidate.is_file():
            continue
        try:
            loaded: object = yaml.safe_load(candidate.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError):
            return {}
        return loaded if isinstance(loaded, dict) else {}
    return {}


def _tool_name(metadata: dict[str, Any], item: dict[str, Any], path: str) -> str:
    tools = metadata.get("tools")
    if isinstance(tools, list):
        for tool in tools:
            if isinstance(tool, dict) and tool:
                return str(next(iter(tool)))
    detected = item.get("tool")
    if isinstance(detected, str) and detected:
        return detected
    return Path(path).name


def _container_uris(path: Path) -> tuple[str, ...]:
    main = path / "main.nf"
    if not main.is_file():
        return ()
    text = main.read_text(encoding="utf-8", errors="replace")
    uris: set[str] = set()
    for match in re.finditer(r"\bcontainer\b", text):
        tail = text[match.end() : match.end() + 1200]
        boundary = re.search(r"\n\s*(?:input|output|when|script|stub)\s*:", tail)
        expression = tail[: boundary.start()] if boundary else tail.split("\n\n", 1)[0]
        for value in _QUOTED.findall(expression):
            if any(character.isspace() for character in value):
                continue
            if "/" not in value:
                continue
            basename = value.rsplit("/", 1)[-1]
            if ":" in basename or "sha256/" in value or value.endswith("/data"):
                uris.add(value)
    return tuple(sorted(uris))


def _conda_packages(path: Path) -> tuple[str, ...]:
    environment = path / "environment.yml"
    if not environment.is_file():
        return ()
    try:
        loaded: object = yaml.safe_load(environment.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError):
        return ()
    if not isinstance(loaded, dict) or not isinstance(loaded.get("dependencies"), list):
        return ()
    return tuple(
        sorted(item for item in loaded["dependencies"] if isinstance(item, str))
    )


def _versions(
    item: dict[str, Any], path: str, uris: tuple[str, ...]
) -> tuple[str, ...]:
    values: set[str] = set()
    detected = item.get("tool_version")
    if isinstance(detected, str) and detected:
        values.add(detected)
    path_version = _SEMVER.match(Path(path).name)
    if path_version:
        values.add(path_version.group(1))
    for uri in uris:
        basename = uri.rsplit("/", 1)[-1]
        if ":" not in basename:
            continue
        match = _SEMVER.match(basename.split(":", 1)[1])
        if match:
            values.add(match.group(1))
    return tuple(sorted(values))


def _discover(
    root: Path,
) -> tuple[tuple[ComponentCandidate, tuple[Evidence, ...]], ...]:
    discovered = []
    for item in sorted(_module_items(root), key=lambda value: str(value.get("path"))):
        relative = item.get("path")
        if not isinstance(relative, str) or not relative:
            continue
        module_path = root / relative
        metadata = _metadata(module_path)
        uris = _container_uris(module_path)
        versions = _versions(item, relative, uris)
        namespace = item.get("namespace")
        if not isinstance(namespace, str) or not namespace:
            namespace = (
                Path(relative).parts[1] if len(Path(relative).parts) > 1 else "local"
            )
        name = metadata.get("name")
        if not isinstance(name, str) or not name:
            raw_name = item.get("name")
            name = (
                raw_name
                if isinstance(raw_name, str) and raw_name
                else Path(relative).name
            )
        tool_name = _tool_name(metadata, item, relative)
        unresolved = ["review"]
        if len(versions) > 1:
            unresolved.append("version")
        if len(uris) > 1:
            unresolved.append("container_uri")
        component_id = "component:" + relative.replace("/", "__")
        candidate = ComponentCandidate(
            id=component_id,
            name=name,
            path=relative,
            namespace=namespace,
            tool_name=tool_name,
            versions=versions,
            container_uris=uris,
            conda_packages=_conda_packages(module_path),
            unresolved_fields=tuple(unresolved),
        )
        locations = ["modules.json"]
        if metadata:
            locations.append(f"{relative}/meta.yml")
        if (module_path / "main.nf").is_file():
            locations.append(f"{relative}/main.nf")
        if (module_path / "environment.yml").is_file():
            locations.append(f"{relative}/environment.yml")
        evidence = tuple(
            Evidence(
                id=f"component:{relative}:{index}",
                provenance=EvidenceProvenance(
                    source="component_inventory", location=location
                ),
                observed_value=(
                    candidate.model_dump(mode="json") if index == 1 else location
                ),
                confidence=1.0,
            )
            for index, location in enumerate(locations, start=1)
        )
        discovered.append((candidate, evidence))
    return tuple(discovered)


def discover_components(repository_root: str | Path) -> AuthoringDocument:
    """Persist deterministic component candidates and explicit conflicts."""
    root = Path(repository_root).resolve()
    document = load_repository_document(root)
    evidence = {item.id: item for item in document.evidence}
    decisions = {item.id: item for item in document.decisions}
    component_ids: set[str] = set()
    for candidate, candidate_evidence in _discover(root):
        component_ids.add(candidate.id)
        for item in candidate_evidence:
            evidence[item.id] = item
        existing = decisions.get(candidate.id)
        if existing is not None and existing.status in {
            DecisionStatus.REVIEWED,
            DecisionStatus.REJECTED,
        }:
            continue
        conflict_fields = tuple(
            field
            for field in candidate.unresolved_fields
            if field in {"version", "container_uri"}
        )
        decisions[candidate.id] = Decision(
            id=candidate.id,
            status=(
                DecisionStatus.CONFLICT if conflict_fields else DecisionStatus.CANDIDATE
            ),
            value=candidate.model_dump(mode="json"),
            evidence_ids=tuple(item.id for item in candidate_evidence),
            reason=(
                f"conflicting detected {', '.join(conflict_fields)}"
                if conflict_fields
                else None
            ),
        )
    unresolved = tuple(
        UnresolvedDecision(
            decision_id=decision_id,
            reason="Component software identity requires explicit review",
        )
        for decision_id in sorted(component_ids)
        if decisions[decision_id].status
        in {DecisionStatus.CANDIDATE, DecisionStatus.CONFLICT}
    )
    layer = LayerState(
        name="components",
        configured=True,
        decision_ids=tuple(sorted(component_ids)),
        unresolved=unresolved,
    )
    updated = AuthoringDocument(
        schema_version=document.schema_version,
        pipeline=document.pipeline,
        output_contract=document.output_contract,
        evidence=tuple(sorted(evidence.values(), key=lambda value: value.id)),
        decisions=tuple(sorted(decisions.values(), key=lambda value: value.id)),
        layers=_replace_layer(document.layers, layer),
    )
    save_repository_document(root, updated)
    return updated


def unresolved_component_candidates(
    document: AuthoringDocument,
) -> tuple[ComponentCandidate, ...]:
    """Return components still awaiting review or conflict resolution."""
    layer = next((item for item in document.layers if item.name == "components"), None)
    if layer is None:
        return ()
    decisions = {item.id: item for item in document.decisions}
    candidates = []
    for decision_id in layer.decision_ids:
        decision = decisions[decision_id]
        if decision.status not in {DecisionStatus.CANDIDATE, DecisionStatus.CONFLICT}:
            continue
        try:
            candidates.append(ComponentCandidate.model_validate(decision.value))
        except ValidationError:
            continue
    return tuple(sorted(candidates, key=lambda item: item.id))


def review_component(
    repository_root: str | Path,
    candidate_id: str,
    *,
    version: str | None = None,
    container_uri: str | None = None,
) -> AuthoringDocument:
    """Select one component version/container combination explicitly."""
    root = Path(repository_root).resolve()
    document = load_repository_document(root)
    decisions = {item.id: item for item in document.decisions}
    decision = decisions.get(candidate_id)
    if decision is None:
        raise ComponentReviewError(f"unknown component candidate {candidate_id!r}")
    try:
        candidate = ComponentCandidate.model_validate(decision.value)
    except ValidationError as error:
        raise ComponentReviewError(str(error)) from error
    if version is None and len(candidate.versions) > 1:
        raise ComponentReviewError(
            f"{candidate_id} has conflicting versions; select one explicitly"
        )
    if container_uri is None and len(candidate.container_uris) > 1:
        raise ComponentReviewError(
            f"{candidate_id} has conflicting containers; select one explicitly"
        )
    if version is not None and version not in candidate.versions:
        raise ComponentReviewError(
            f"selected version {version!r} is not present in detected evidence"
        )
    if container_uri is not None and container_uri not in candidate.container_uris:
        raise ComponentReviewError(
            f"selected container {container_uri!r} is not present in detected evidence"
        )
    selected_version = version or (
        candidate.versions[0] if candidate.versions else None
    )
    selected_container = container_uri or (
        candidate.container_uris[0] if candidate.container_uris else None
    )
    evidence_by_id = {item.id: item for item in document.evidence}
    locations = tuple(
        sorted(
            {
                evidence_by_id[item_id].provenance.location
                for item_id in decision.evidence_ids
                if item_id in evidence_by_id
            }
        )
    )
    reviewed = ReviewedComponent(
        id=candidate.id,
        name=candidate.name,
        path=candidate.path,
        namespace=candidate.namespace,
        tool_name=candidate.tool_name,
        version=selected_version,
        container_uri=selected_container,
        conda_packages=candidate.conda_packages,
        evidence_locations=locations,
    )
    decisions[candidate_id] = Decision(
        id=candidate_id,
        status=DecisionStatus.REVIEWED,
        value=reviewed.model_dump(mode="json"),
        evidence_ids=decision.evidence_ids,
    )
    layer = next((item for item in document.layers if item.name == "components"), None)
    if layer is None:
        raise ComponentReviewError("component layer has not been discovered")
    replacement = layer.model_copy(
        update={
            "unresolved": tuple(
                item for item in layer.unresolved if item.decision_id != candidate_id
            )
        }
    )
    updated = AuthoringDocument(
        schema_version=document.schema_version,
        pipeline=document.pipeline,
        output_contract=document.output_contract,
        evidence=document.evidence,
        decisions=tuple(sorted(decisions.values(), key=lambda value: value.id)),
        layers=_replace_layer(document.layers, replacement),
    )
    save_repository_document(root, updated)
    return updated


def accept_unambiguous_components(repository_root: str | Path) -> AuthoringDocument:
    """Explicitly accept every detected component without a conflict."""
    root = Path(repository_root).resolve()
    document = load_repository_document(root)
    for candidate in unresolved_component_candidates(document):
        if len(candidate.versions) <= 1 and len(candidate.container_uris) <= 1:
            document = review_component(root, candidate.id)
    return document
