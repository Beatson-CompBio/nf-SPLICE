"""Components layer: ``components.draft.yaml`` and container provenance.

Each reviewed component links to one logical container whose native source
references are kept per runtime (Docker/OCI versus Singularity/Apptainer).
A downloadable image distribution is recorded only after nf-splice has
downloaded it and verified its format and SHA-256; a hand-entered or stale
checksum is never accepted as verified.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from nf_splice.contracts import (
    COMPONENTS_FAMILY,
    data_document_header,
    validate_contract_document,
)
from nf_splice.domain.components import (
    ContainerRuntime,
    ContainerSource,
    ReferenceKind,
    ReviewedContainer,
)
from nf_splice.drafts import PatchOp, canonical_json
from nf_splice.inspectors.containers import (
    classify_reference,
    config_overrides,
    container_sources,
    nextflow_cache_filename,
)
from nf_splice.inspectors.modules import (
    ModuleDiscoveryError,
    conda_packages,
    detected_versions,
    module_items,
    module_metadata,
    tool_name,
)
from nf_splice.layers.base import (
    ChangeContext,
    DraftIssue,
    EditResult,
    LayerError,
    LayerValidation,
    ReviewState,
    Severity,
    edit_draft,
    issue,
    load_review_state,
    ops_for,
    read_layer,
    record_decision,
    seed_draft,
    strip_marker,
    update_review_state,
)
from nf_splice.layers.bundle import validate_bundle_draft
from nf_splice.services.containers import Fetcher, Resolver, verify_image_url

LAYER = "components"
PENDING = "pending"
_BLOCKING_KINDS = {
    ReferenceKind.UNRESOLVED_EXPRESSION,
    ReferenceKind.UNSUPPORTED,
    ReferenceKind.INSECURE_HTTP,
}
_SINGULARITY_KINDS = {
    ReferenceKind.HTTPS_IMAGE,
    ReferenceKind.ORAS,
    ReferenceKind.LOCAL_IMAGE,
}


def container_id(primary: str) -> str:
    """Stable container ID derived from the primary reference."""
    return f"container-{hashlib.sha256(primary.encode('utf-8')).hexdigest()[:12]}"


def _process_names(main_nf: Path) -> list[str]:
    if not main_nf.is_file():
        return []
    return re.findall(
        r"\bprocess\s+([A-Za-z0-9_]+)\s*\{",
        main_nf.read_text(encoding="utf-8", errors="replace"),
    )


def _discover(root: Path) -> list[dict[str, Any]]:
    try:
        items = module_items(root)
    except ModuleDiscoveryError as error:
        raise LayerError(str(error)) from error
    overrides = config_overrides(root)
    discovered = []
    for item in sorted(items, key=lambda value: str(value.get("path"))):
        relative = item.get("path")
        if not isinstance(relative, str) or not relative:
            continue
        module = root / relative
        metadata = module_metadata(module)
        sources = list(container_sources(module / "main.nf", f"{relative}/main.nf"))
        for process in _process_names(module / "main.nf"):
            sources.extend(overrides.get(process, []))
        uris = tuple(source.raw for source in sources)
        name = metadata.get("name") if isinstance(metadata.get("name"), str) else None
        namespace = item.get("namespace")
        discovered.append(
            {
                "id": "component:" + relative.replace("/", "__"),
                "name": name or str(item.get("name") or Path(relative).name),
                "path": relative,
                "namespace": namespace
                if isinstance(namespace, str) and namespace
                else (
                    Path(relative).parts[1]
                    if len(Path(relative).parts) > 1
                    else "local"
                ),
                "tool_name": tool_name(metadata, item, relative),
                "versions": list(detected_versions(item, relative, uris)),
                "conda_packages": list(conda_packages(module)),
                "sources": [source.model_dump(mode="json") for source in sources],
                "evidence": sorted(
                    {"modules.json", *(source.location for source in sources)}
                    | (
                        {f"{relative}/meta.yml"}
                        if (module / "meta.yml").is_file()
                        else set()
                    )
                ),
            }
        )
    return discovered


def _proposed_sources(
    sources: Sequence[ContainerSource],
) -> tuple[dict[str, str], list[str]]:
    """Group detected references by runtime; report what needs a decision."""
    by_runtime: dict[ContainerRuntime, set[str]] = {}
    problems: list[str] = []
    for source in sources:
        if source.kind in _BLOCKING_KINDS:
            problems.append(f"{source.kind.value} reference at {source.location}")
            continue
        runtime = source.runtime
        if runtime is ContainerRuntime.ANY:
            runtime = (
                ContainerRuntime.SINGULARITY
                if source.kind in _SINGULARITY_KINDS
                else ContainerRuntime.DOCKER
            )
        by_runtime.setdefault(runtime, set()).add(source.raw)
    selected = {}
    for runtime, values in sorted(by_runtime.items(), key=lambda item: item[0].value):
        if len(values) > 1:
            problems.append(
                f"ambiguous {runtime.value} alternatives: {', '.join(sorted(values))}"
            )
        else:
            selected[runtime.value] = next(iter(values))
    return selected, problems


@dataclass(frozen=True, slots=True)
class ComponentCandidateView:
    """A pending component and what still needs a decision."""

    id: str
    name: str
    versions: tuple[str, ...]
    proposed_sources: Mapping[str, str]
    problems: tuple[str, ...]


def discover_components(
    repository_root: str | Path,
) -> tuple[ComponentCandidateView, ...]:
    """Seed the draft if absent and merge module candidates into the sidecar."""
    root = Path(repository_root).resolve()
    seed_draft(
        root,
        LAYER,
        {"require_downloadable_images": None, "containers": [], "components": []},
    )
    discovered = _discover(root)

    def merge(state: ReviewState) -> None:
        for candidate in discovered:
            existing = state.candidates.get(candidate["id"])
            if existing is None or existing.get("status") == PENDING:
                state.candidates[candidate["id"]] = {
                    "status": PENDING,
                    "candidate": candidate,
                }

    update_review_state(root, LAYER, merge)
    return pending_components(root)


def _view(entry: Mapping[str, Any]) -> ComponentCandidateView:
    candidate = entry["candidate"]
    sources = [ContainerSource.model_validate(item) for item in candidate["sources"]]
    proposed, problems = _proposed_sources(sources)
    versions = tuple(candidate["versions"])
    if len(versions) > 1:
        problems.append(f"conflicting versions: {', '.join(versions)}")
    return ComponentCandidateView(
        candidate["id"], candidate["name"], versions, proposed, tuple(problems)
    )


def pending_components(
    repository_root: str | Path,
) -> tuple[ComponentCandidateView, ...]:
    """Return component candidates still awaiting review."""
    state = load_review_state(Path(repository_root).resolve(), LAYER)
    return tuple(
        _view(entry)
        for _, entry in sorted(state.candidates.items())
        if entry.get("status") == PENDING
    )


def _draft(root: Path) -> dict[str, Any]:
    state = read_layer(root, LAYER)
    if state.draft is None or not isinstance(state.draft.data, dict):
        raise LayerError("components.draft.yaml is missing or malformed")
    data: dict[str, Any] = state.draft.data
    return data


def accept_component(
    repository_root: str | Path,
    candidate_id: str,
    context: ChangeContext,
    *,
    version: str | None = None,
    sources: Mapping[str, str] | None = None,
) -> EditResult:
    """Accept one component with explicitly resolved version and sources.

    Selected sources must be among the detected references; ambiguous,
    unresolved or unsupported references must be resolved explicitly.
    """
    root = Path(repository_root).resolve()
    state = load_review_state(root, LAYER)
    entry = state.candidates.get(candidate_id)
    if not isinstance(entry, dict):
        raise LayerError(f"unknown component candidate {candidate_id!r}")
    view = _view(entry)
    candidate = entry["candidate"]
    detected = {item["raw"] for item in candidate["sources"]}
    if sources is None:
        if any(
            "alternatives" in item or "reference at" in item for item in view.problems
        ):
            raise LayerError(
                f"{candidate_id}: {'; '.join(view.problems)}; select sources explicitly"
            )
        selected = dict(view.proposed_sources)
    else:
        selected = {}
        for runtime, raw in sources.items():
            try:
                runtime_value = ContainerRuntime(runtime)
            except ValueError as error:
                raise LayerError(str(error)) from error
            if runtime_value is ContainerRuntime.ANY:
                raise LayerError("select a concrete runtime for each source")
            if raw not in detected:
                raise LayerError(f"source {raw!r} is not present in detected evidence")
            selected[runtime_value.value] = raw
    versions = tuple(candidate["versions"])
    if version is None and len(versions) > 1:
        raise LayerError(f"{candidate_id} has conflicting versions; select one")
    if version is not None and version not in versions:
        raise LayerError(f"version {version!r} is not present in detected evidence")
    data = _draft(root)
    containers = list(data.get("containers") or [])
    operations: list[PatchOp] = []
    identifier = None
    if selected:
        existing = next(
            (
                item
                for item in containers
                if isinstance(item, dict) and item.get("source_images") == selected
            ),
            None,
        )
        if existing is not None:
            identifier = existing["id"]
        else:
            primary = selected.get("docker") or next(iter(selected.values()))
            identifier = container_id(primary)
            if any(item.get("id") == identifier for item in containers):
                raise LayerError(
                    f"container {identifier} already exists with different sources"
                )
            operations.append(
                PatchOp(
                    "add",
                    f"/containers/{len(containers)}",
                    {"id": identifier, "source_images": selected, "distribution": None},
                )
            )
    components = list(data.get("components") or [])
    component: dict[str, Any] = {
        "id": candidate["id"].removeprefix("component:"),
        "type": "workflow_module",
        "name": candidate["name"],
        "path": candidate["path"],
        "namespace": candidate["namespace"],
        "tool": {"name": candidate["tool_name"]}
        | ({"version": version or versions[0]} if (version or versions) else {}),
        "evidence": candidate["evidence"],
    }
    if identifier is not None:
        component["container_id"] = identifier
    if candidate["conda_packages"]:
        component["conda_packages"] = candidate["conda_packages"]
    operations.append(PatchOp("add", f"/components/{len(components)}", component))

    def mark(review: ReviewState) -> None:
        review.candidates[candidate_id]["status"] = "accepted"

    return edit_draft(
        root, LAYER, operations, context, action="accept_component", review=mark
    )


def reject_component(
    repository_root: str | Path, candidate_id: str, reason: str, context: ChangeContext
) -> None:
    """Exclude one detected module from the published inventory."""
    root = Path(repository_root).resolve()
    if candidate_id not in load_review_state(root, LAYER).candidates:
        raise LayerError(f"unknown component candidate {candidate_id!r}")

    def mark(state: ReviewState) -> None:
        state.candidates[candidate_id].update({"status": "rejected", "reason": reason})

    record_decision(root, LAYER, "reject_component", context, (), mark)


def accept_unambiguous_components(
    repository_root: str | Path, context: ChangeContext
) -> tuple[str, ...]:
    """Explicitly accept every pending component that needs no decision."""
    accepted = []
    for view in pending_components(repository_root):
        if not view.problems:
            accept_component(repository_root, view.id, context)
            accepted.append(view.id)
    return tuple(accepted)


def set_image_policy(
    repository_root: str | Path, require_downloadable: bool, context: ChangeContext
) -> EditResult:
    """Record whether ingestion requires a downloadable image per container."""
    root = Path(repository_root).resolve()
    return edit_draft(
        root,
        LAYER,
        ops_for(_draft(root), {"/require_downloadable_images": require_downloadable}),
        context,
        action="set_image_policy",
    )


def _container_index(data: Mapping[str, Any], identifier: str) -> int:
    for index, item in enumerate(data.get("containers") or []):
        if isinstance(item, dict) and item.get("id") == identifier:
            return index
    raise LayerError(f"unknown container {identifier!r}")


def cache_filename_for(
    container: Mapping[str, Any], registry: str | None = None
) -> str:
    """Nextflow cache name for the container's Singularity/Apptainer source."""
    sources = container.get("source_images") or {}
    for runtime in ("singularity", "apptainer", "docker"):
        if sources.get(runtime):
            return nextflow_cache_filename(str(sources[runtime]), registry=registry)
    raise LayerError("container has no source image")


def verify_distribution(
    repository_root: str | Path,
    identifier: str,
    url: str,
    context: ChangeContext,
    *,
    fetcher: Fetcher | None = None,
    resolver: Resolver | None = None,
    registry: str | None = None,
    scratch: Path | None = None,
) -> EditResult:
    """Download, verify and record a static image distribution (opt-in network)."""
    root = Path(repository_root).resolve()
    data = _draft(root)
    index = _container_index(data, identifier)
    container = data["containers"][index]
    options: dict[str, Any] = {"scratch": scratch}
    if fetcher is not None:
        options["fetcher"] = fetcher
    if resolver is not None:
        options["resolver"] = resolver
    verified = verify_image_url(url, **options)
    sources = container.get("source_images") or {}
    runtime = (
        "apptainer"
        if "apptainer" in sources and "singularity" not in sources
        else "singularity"
    )
    distribution = {
        "download_uri": url,
        "sha256": verified.sha256,
        "size_bytes": verified.size_bytes,
        "filename": verified.filename,
        "format": verified.format.value,
        "cache_filename": cache_filename_for(container, registry),
        "source_runtime": runtime,
    }

    def record(state: ReviewState) -> None:
        state.section("verified")[identifier] = {
            "sha256": verified.sha256,
            "download_uri": url,
            "final_url": verified.final_url,
        }

    return edit_draft(
        root,
        LAYER,
        ops_for(data, {f"/containers/{index}/distribution": distribution}),
        context,
        action="verify_distribution",
        review=record,
    )


def _pipeline(root: Path) -> tuple[dict[str, str] | None, list[DraftIssue]]:
    identity = validate_bundle_draft(root)
    if not identity.ready or identity.metadata is None:
        return None, [issue(LAYER, "", "identity_not_ready", "identity is not ready")]
    return identity.metadata.reference(), []


def validate_components_draft(repository_root: str | Path) -> LayerValidation:
    """Validate the component inventory and compile ``components.json``."""
    root = Path(repository_root).resolve()
    state = read_layer(root, LAYER)
    if state.draft is None or not isinstance(state.draft.data, dict):
        code = "missing_draft" if not state.file.exists else "syntax"
        return LayerValidation(
            LAYER, (issue(LAYER, "", code, str(state.error or code)),)
        )
    data = strip_marker(state.draft.data)
    review = load_review_state(root, LAYER)
    issues: list[DraftIssue] = []
    for candidate_id, entry in sorted(review.candidates.items()):
        if entry.get("status") == PENDING:
            issues.append(
                issue(LAYER, "", "pending_candidate", f"{candidate_id} requires review")
            )
    required = data.get("require_downloadable_images")
    if not isinstance(required, bool):
        issues.append(
            issue(
                LAYER,
                "/require_downloadable_images",
                "missing_required",
                "review whether ingestion requires downloadable images (true/false)",
            )
        )
    containers: list[ReviewedContainer] = []
    raw_containers = data.get("containers") or []
    for index, item in enumerate(raw_containers):
        try:
            container = ReviewedContainer.model_validate(item)
        except ValidationError as error:
            for detail in error.errors():
                pointer = f"/containers/{index}" + "".join(
                    f"/{p}" for p in detail["loc"]
                )
                issues.append(issue(LAYER, pointer, "invalid_value", detail["msg"]))
            continue
        containers.append(container)
        for runtime, raw in container.source_images.items():
            kind = classify_reference(raw)
            if kind in _BLOCKING_KINDS:
                issues.append(
                    issue(
                        LAYER,
                        f"/containers/{index}/source_images/{runtime.value}",
                        "unresolved_source",
                        f"{kind.value} reference {raw!r} cannot be published",
                    )
                )
            if runtime is ContainerRuntime.DOCKER and kind in _SINGULARITY_KINDS:
                issues.append(
                    issue(
                        LAYER,
                        f"/containers/{index}/source_images/docker",
                        "runtime_mismatch",
                        f"{raw!r} is not a Docker/OCI registry reference",
                    )
                )
        distribution = container.distribution
        verified = review.section("verified").get(container.id)
        if distribution is not None:
            if (
                not isinstance(verified, dict)
                or verified.get("sha256") != distribution.sha256
            ):
                issues.append(
                    issue(
                        LAYER,
                        f"/containers/{index}/distribution",
                        "unverified_distribution",
                        "distribution was not verified by nf-splice; run "
                        "`nf-splice containers verify`",
                    )
                )
            expected = cache_filename_for(item)
            if distribution.cache_filename != expected:
                issues.append(
                    issue(
                        LAYER,
                        f"/containers/{index}/distribution/cache_filename",
                        "cache_filename",
                        f"Nextflow cache name for this source is {expected!r}",
                        Severity.WARNING,
                    )
                )
            if distribution.filename != distribution.cache_filename:
                issues.append(
                    issue(
                        LAYER,
                        f"/containers/{index}/distribution/filename",
                        "cache_reuse",
                        "published file name differs from the Nextflow cache name; "
                        "a pre-cached copy will not be reused",
                        Severity.WARNING,
                    )
                )
        elif required is True:
            issues.append(
                issue(
                    LAYER,
                    f"/containers/{index}/distribution",
                    "needs_materialisation",
                    f"{container.id} has no verified downloadable image",
                )
            )
    identifiers = [item.id for item in containers]
    if len(identifiers) != len(set(identifiers)):
        issues.append(
            issue(LAYER, "/containers", "duplicate_id", "container ids must be unique")
        )
    known = set(identifiers)
    for index, component in enumerate(data.get("components") or []):
        reference = (
            component.get("container_id") if isinstance(component, dict) else None
        )
        if reference is not None and reference not in known:
            issues.append(
                issue(
                    LAYER,
                    f"/components/{index}/container_id",
                    "dangling_reference",
                    f"component references unknown container {reference!r}",
                )
            )
    pipeline, identity_issues = _pipeline(root)
    issues.extend(identity_issues)
    if pipeline is None or any(item.severity is Severity.ERROR for item in issues):
        return LayerValidation(LAYER, tuple(issues))
    rendered_containers = []
    for container in sorted(containers, key=lambda item: item.id):
        sources = {
            key.value: value
            for key, value in sorted(
                container.source_images.items(), key=lambda kv: kv[0].value
            )
        }
        record: dict[str, Any] = {"id": container.id}
        if container.distribution is not None:
            record["type"] = container.distribution.source_runtime.value
            record["uri"] = container.distribution.download_uri
            status = "verified"
        elif "docker" in sources:
            record["type"] = "docker"
            record["uri"] = sources["docker"]
            status = "resolved"
        else:
            runtime_name, uri = next(iter(sources.items()))
            record["type"] = "oras" if uri.startswith("oras://") else runtime_name
            record["uri"] = uri
            status = "resolved"
        record["source_images"] = sources
        if container.distribution is not None:
            record["distribution"] = container.distribution.model_dump(
                mode="json", exclude_none=True
            )
        record["resolution"] = {"status": status}
        rendered_containers.append(record)
    document = {
        **data_document_header(COMPONENTS_FAMILY),
        "pipeline": pipeline,
        "require_downloadable_images": required,
        "containers": rendered_containers,
        "components": sorted(
            (dict(item) for item in data.get("components") or []),
            key=lambda item: item["id"],
        ),
    }
    report = validate_contract_document(document, COMPONENTS_FAMILY)
    issues.extend(
        issue(
            LAYER,
            item.json_pointer,
            "contract",
            item.message,
            path="splice/components.json",
        )
        for item in report.issues
    )
    if not report.valid:
        return LayerValidation(LAYER, tuple(issues))
    return LayerValidation(
        LAYER, tuple(issues), {"components.json": canonical_json(document)}
    )
