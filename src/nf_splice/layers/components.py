"""Components layer: ``components.draft.yaml`` and container provenance.

Each reviewed component links to one logical container whose native source
references are kept per runtime (Docker/OCI versus Singularity/Apptainer).
A downloadable image distribution is recorded only after nf-splice has
downloaded it and verified its format and SHA-256; a hand-entered or stale
checksum is never accepted as verified.
"""

from __future__ import annotations

import hashlib
import json
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
    sources_in_text,
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
from nf_splice.services.containers import (
    ContainerServiceError,
    Fetcher,
    Resolver,
    verify_image_url,
)

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


#: Directories that never hold workflow code of the pipeline itself.
_NOT_WORKFLOW = {".git", ".splice-local", ".nf-splice-local", "work", ".nextflow"}


def _block_end(text: str, opening: int) -> int:
    """Index just past the brace that closes the one at ``opening``."""
    depth = 0
    for index in range(opening, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return index + 1
    return len(text)


def inline_processes(root: Path) -> list[dict[str, Any]]:
    """Processes defined in workflow files rather than in module directories.

    Custom pipelines often define processes in ``main.nf`` or a workflow
    file. Each is a component, with the container references of its own
    body (located by file and line), so an inventory never silently misses
    software a pipeline runs.
    """
    found = []
    for path in sorted(root.rglob("*.nf")):
        relative = path.relative_to(root)
        parts = relative.parts
        if (
            path.is_symlink()
            or not path.is_file()
            or parts[0] in {"modules", "splice", "tests"}
            or any(part in _NOT_WORKFLOW for part in parts)
            or "tests" in parts[:-1]
        ):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in re.finditer(r"^\s*process\s+([A-Za-z0-9_]+)\s*\{", text, re.M):
            start = text.index("{", match.start())
            end = _block_end(text, start)
            name = match.group(1)
            line = text.count("\n", 0, match.start()) + 1
            found.append(
                {
                    "file": relative.as_posix(),
                    "process": name,
                    "line": line,
                    "sources": sources_in_text(
                        text, relative.as_posix(), match.start(), end
                    ),
                }
            )
    return found


#: Component types: a module directory, or a process defined in a
#: workflow file (``path`` is that ``.nf`` file, ``process`` its name).
MODULE = "workflow_module"
PROCESS = "workflow_process"


def code_key(item: Mapping[str, Any]) -> str:
    """What identifies a component's code: its path, and process if inline."""
    path = str(item.get("path") or "")
    process = item.get("process")
    return f"{path}#{process}" if process else path


def _declared_sources(
    root: Path, path: str, process: str | None = None
) -> tuple[ContainerSource, ...]:
    """Container references a component's code declares (module or inline)."""
    if process:
        return next(
            (
                tuple(item["sources"])
                for item in inline_processes(root)
                if item["file"] == path and item["process"] == process
            ),
            (),
        )
    main = root / path / "main.nf"
    if main.is_symlink() or not main.is_file():
        return ()
    return container_sources(main, f"{path}/main.nf")


def _code_exists(root: Path, path: str, process: str | None = None) -> bool:
    if process:
        return any(
            item["file"] == path and item["process"] == process
            for item in inline_processes(root)
        )
    return (root / path / "main.nf").is_file()


def _scanned_items(root: Path) -> tuple[dict[str, Any], ...]:
    """Modules found on disk when ``modules.json`` is absent."""
    found = []
    modules = root / "modules"
    if modules.is_dir() and not modules.is_symlink():
        for main_nf in sorted(modules.rglob("main.nf")):
            relative = main_nf.parent.relative_to(root).as_posix()
            if "tests" in Path(relative).parts:
                continue
            parts = Path(relative).parts
            found.append(
                {
                    "kind": "module",
                    "path": relative,
                    "namespace": parts[1] if len(parts) > 2 else "local",
                    "name": main_nf.parent.name,
                }
            )
    return tuple(found)


def _discover(root: Path) -> list[dict[str, Any]]:
    if (root / "modules.json").is_file():
        try:
            items = module_items(root)
        except ModuleDiscoveryError as error:
            raise LayerError(str(error)) from error
    else:
        items = _scanned_items(root)
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
                "type": MODULE,
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
    for inline in inline_processes(root):
        # A process defined in a workflow file: path is the file itself.
        sources = list(inline["sources"])
        sources.extend(overrides.get(inline["process"], []))
        uris = tuple(source.raw for source in sources)
        # Stable and unique: the file and the process name, which Nextflow
        # requires to be unique within one file.
        identifier = re.sub(
            r"[^A-Za-z0-9_]+", "__", f"{inline['file']}::{inline['process']}"
        ).strip("_")
        discovered.append(
            {
                "id": "component:" + identifier,
                "type": PROCESS,
                "name": inline["process"],
                "path": inline["file"],
                "process": inline["process"],
                "namespace": "local",
                "tool_name": inline["process"].lower(),
                "versions": list(detected_versions({}, inline["file"], uris)),
                "conda_packages": [],
                "sources": [source.model_dump(mode="json") for source in sources],
                "evidence": sorted(
                    {
                        f"{inline['file']}:{inline['line']}",
                        *(source.location for source in sources),
                    }
                ),
            }
        )
    return discovered


def discovered_modules(repository_root: str | Path) -> list[dict[str, Any]]:
    """Every module found, with its container references (read-only)."""
    found = []
    for item in _discover(Path(repository_root).resolve()):
        sources = [ContainerSource.model_validate(value) for value in item["sources"]]
        selected, problems = _proposed_sources(sources)
        found.append(item | {"selected_sources": selected, "problems": problems})
    return found


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


#: Draft-only component field: what still stops the component publishing
#: (an unresolved container expression, conflicting versions). It is never
#: published; validation reports it until the author resolves and removes it.
UNRESOLVED = "unresolved"
SEEDED = "seeded"


def sources_digest(sources: Mapping[str, Any]) -> str:
    """A digest of a container's source images (runtime to reference)."""
    canonical = json.dumps(dict(sources), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _lock_evidence(root: Path, payload: bytes) -> dict[str, Any] | None:
    """The lock's verification records, if it vouches for components.json.

    The lock's hash of the published file must match: a hand-edited or
    foreign file is not evidence of an earlier verification.
    """
    try:
        lock = json.loads(
            (root / "splice" / "nf-splice.lock.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(lock, dict):
        return None
    record = (lock.get("managed_files") or {}).get("components.json") or {}
    if not (
        isinstance(record, dict)
        and record.get("sha256") == hashlib.sha256(payload).hexdigest()
    ):
        return None
    distributions = lock.get("distributions") or {}
    return distributions if isinstance(distributions, dict) else {}


def _published_inventory(
    root: Path,
) -> tuple[
    dict[str, dict[str, Any]],
    dict[str, tuple[str, str]],
    bool | None,
    dict[str, Any] | None,
]:
    """Published containers, component (id, container id) by path, image policy.

    Read as evidence from ``splice/components.json`` (0.3.0 or an earlier
    layout) so known container IDs stay stable across the migration. The last
    value is the lock's verification records when the lock vouches for the
    file, else ``None``.
    """
    path = root / "splice" / "components.json"
    if path.is_symlink() or not path.is_file():
        return {}, {}, None, None
    try:
        payload = path.read_bytes()
        loaded = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}, {}, None, None
    if not isinstance(loaded, dict):
        return {}, {}, None, None
    containers = {
        str(item["id"]): item
        for item in loaded.get("containers") or []
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    links = {
        code_key(item): (str(item["id"]), str(item.get("container_id") or ""))
        for item in loaded.get("components") or []
        if isinstance(item, dict) and item.get("id") and item.get("path")
    }
    policy = loaded.get("require_downloadable_images")
    return (
        containers,
        links,
        policy if isinstance(policy, bool) else None,
        _lock_evidence(root, payload),
    )


def _adopted_distribution(
    published: Mapping[str, Any],
    selected: Mapping[str, str],
    evidence: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """A previously verified distribution that may be reused, or ``None``.

    Reused without downloading only when everything agrees: the lock vouches
    for the published ``components.json``; the lock's own record of the
    verification names the same checksum, address and size; the published
    distribution is internally consistent (an HTTPS address, a ``sif`` or
    ``img`` file, the Nextflow cache name of these sources); and the
    container's source images are byte-for-byte the ones verified (their
    digest matches the lock's). This is historical evidence of a past
    verification: it never shows the file is reachable today.
    """
    distribution = published.get("distribution")
    resolution = published.get("resolution") or {}
    sources = published.get("source_images")
    container_id = published.get("id")
    record = (evidence or {}).get(str(container_id)) if evidence is not None else None
    if not (
        isinstance(record, dict)
        and isinstance(distribution, dict)
        and isinstance(resolution, dict)
        and resolution.get("status") == "verified"
        and isinstance(sources, dict)
        and dict(sources) == dict(selected)
    ):
        return None
    uri = str(distribution.get("download_uri", ""))
    try:
        cache_name = cache_filename_for({"source_images": dict(selected)})
    except LayerError:
        return None
    consistent = (
        uri.startswith("https://")
        and distribution.get("format") in {"sif", "img"}
        and bool(distribution.get("filename"))
        and distribution.get("cache_filename") == cache_name
        and record.get("sha256") == distribution.get("sha256")
        and record.get("download_uri") == uri
        and record.get("size_bytes") == distribution.get("size_bytes")
        and record.get("source_images_sha256") == sources_digest(selected)
    )
    return dict(distribution) if consistent else None


def _references(container: Mapping[str, Any]) -> set[str]:
    """Every image reference a published container record names."""
    found = {
        str(value)
        for key in ("uri", "source_image")
        if isinstance(value := container.get(key), str)
    }
    sources = container.get("source_images")
    if isinstance(sources, dict):
        found.update(str(value) for value in sources.values())
    normalised = set()
    for value in found:
        bare = value.removeprefix("docker://")
        normalised.update({bare, bare.removeprefix("quay.io/")})
    return normalised


def seed_inventory(
    root: Path, discovered: Sequence[Mapping[str, Any]]
) -> tuple[dict[str, Any], list[str], dict[str, dict[str, Any]]]:
    """Build the first ``components.draft.yaml`` from the module inventory.

    Every module becomes a component. Containers are deduplicated by their
    per-runtime sources; a previously published container whose reference
    matches keeps its ID. Anything that cannot be resolved statically stays
    visible in the component's draft-only ``unresolved`` list instead of
    being guessed. A verified distribution of a kept container is kept too,
    when its source is unchanged and the lock vouches for the published
    file; the last value returned holds those verification records.
    """
    published, links, policy, lock_evidence = _published_inventory(root)
    adopted: dict[str, dict[str, Any]] = {}
    containers: list[dict[str, Any]] = []
    by_sources: dict[str, str] = {}
    components: list[dict[str, Any]] = []
    reused = 0
    for candidate in discovered:
        sources = [
            ContainerSource.model_validate(item) for item in candidate["sources"]
        ]
        selected, problems = _proposed_sources(sources)
        versions = list(candidate["versions"])
        if not versions:
            # The module's conda environment pins the tool itself.
            tool = re.escape(str(candidate["tool_name"]).lower())
            versions = sorted(
                {
                    match.group(1)
                    for package in candidate["conda_packages"]
                    if (
                        match := re.fullmatch(
                            rf"(?:[\w-]+::)?{tool}=+([\w.]+?)(?:=.*)?",
                            str(package).lower(),
                        )
                    )
                }
            )
        previous_id, previous_container = links.get(code_key(candidate), ("", ""))
        component: dict[str, Any] = {
            "id": previous_id or candidate["id"].removeprefix("component:"),
            "type": candidate.get("type", MODULE),
            "name": candidate["name"],
            "path": candidate["path"],
            **({"process": candidate["process"]} if candidate.get("process") else {}),
            "namespace": candidate["namespace"],
            "tool": {"name": candidate["tool_name"]}
            | ({"version": versions[0]} if len(versions) == 1 else {}),
            "evidence": candidate["evidence"],
        }
        unresolved = list(problems)
        if len(versions) > 1:
            unresolved.append(
                f"conflicting tool versions {', '.join(versions)}: set tool.version"
            )
        if selected and not problems:
            # One logical image may be listed for Singularity only by one
            # module and for Singularity and Apptainer by another: merge
            # records whose shared runtimes name the same references.
            existing = next(
                (
                    item
                    for item in containers
                    if all(
                        item["source_images"].get(runtime) in (None, raw)
                        for runtime, raw in selected.items()
                    )
                    and set(item["source_images"].values()) & set(selected.values())
                    and selected.get("docker") == item["source_images"].get("docker")
                ),
                None,
            )
            if existing is not None:
                existing["source_images"] = dict(
                    sorted({**existing["source_images"], **selected}.items())
                )
                component["container_id"] = existing["id"]
                selected = {}
            signature = json.dumps(selected, sort_keys=True)
            identifier = by_sources.get(signature) if selected else None
            if identifier is None and selected:
                wanted = {
                    value.removeprefix("quay.io/") for value in selected.values()
                } | set(selected.values())
                candidates_ids = (
                    [previous_container] if previous_container else []
                ) + sorted(published)
                identifier = next(
                    (
                        item
                        for item in candidates_ids
                        if item in published
                        and _references(published[item]) & wanted
                        and item not in by_sources.values()
                    ),
                    None,
                )
                if identifier is not None:
                    reused += 1
                else:
                    primary = selected.get("docker") or next(iter(selected.values()))
                    identifier = container_id(primary)
                    if any(item["id"] == identifier for item in containers):
                        identifier = container_id(signature)
                by_sources[signature] = identifier
                distribution = (
                    _adopted_distribution(
                        published[identifier], selected, lock_evidence
                    )
                    if identifier in published
                    else None
                )
                if distribution is not None:
                    adopted[identifier] = {
                        "sha256": distribution["sha256"],
                        "download_uri": distribution["download_uri"],
                        "basis": "historical",
                        "adopted_from": "splice/components.json",
                    }
                containers.append(
                    {
                        "id": identifier,
                        "source_images": selected,
                        "distribution": distribution,
                    }
                )
            if selected:
                component["container_id"] = identifier
        if candidate["conda_packages"]:
            component["conda_packages"] = candidate["conda_packages"]
        if unresolved:
            component[UNRESOLVED] = unresolved
        components.append(component)
    origin = "modules.json" if (root / "modules.json").is_file() else "modules/"
    notes = [
        f"seeded {len(components)} component(s) and {len(containers)} distinct "
        f"container(s) from {origin}"
    ]
    if published:
        notes.append(
            f"kept {reused} container ID(s) from the published splice/components.json"
        )
    if adopted:
        notes.append(
            f"kept {len(adopted)} verified image distribution(s) whose sources are "
            "unchanged; they were not downloaded again"
        )
    open_items = sum(1 for item in components if item.get(UNRESOLVED))
    if open_items:
        notes.append(f"{open_items} component(s) have unresolved items to review")
    return (
        {
            "require_downloadable_images": policy,
            "containers": sorted(containers, key=lambda item: item["id"]),
            "components": components,
        },
        notes,
        adopted,
    )


def discover_components(
    repository_root: str | Path,
) -> tuple[ComponentCandidateView, ...]:
    """Seed a populated draft if absent; refresh the advisory module evidence.

    The first run writes the whole inventory into ``components.draft.yaml``.
    Later runs never change the draft: they only record evidence for modules
    added since, which validation reports as not yet listed.
    """
    root = Path(repository_root).resolve()
    discovered = _discover(root)
    seed, _notes, adopted = seed_inventory(root, discovered)
    created = seed_draft(
        root,
        LAYER,
        seed,
        header=(
            "nf-SPLICE components draft (authoritative, editable).",
            "Seeded with every module and its runtime-specific container sources;",
            "edit freely. 'unresolved' lists what still needs a decision.",
        ),
    )

    def merge(state: ReviewState) -> None:
        if created:
            # The verification records of distributions carried over above.
            state.section("verified").update(adopted)
        for candidate in discovered:
            existing = state.candidates.get(candidate["id"])
            if existing is None or existing.get("status") == PENDING:
                state.candidates[candidate["id"]] = {
                    "status": SEEDED if created else PENDING,
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
        "type": candidate.get("type", MODULE),
        "name": candidate["name"],
        "path": candidate["path"],
        **({"process": candidate["process"]} if candidate.get("process") else {}),
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
            "basis": "fresh",
        }

    return edit_draft(
        root,
        LAYER,
        ops_for(data, {f"/containers/{index}/distribution": distribution}),
        context,
        action="verify_distribution",
        review=record,
    )


@dataclass(frozen=True, slots=True)
class Reverification:
    """Outcome of downloading one recorded distribution again."""

    container_id: str
    download_uri: str
    status: str  # fresh, changed or failed
    detail: str

    def to_json(self) -> dict[str, str]:
        return {
            "container_id": self.container_id,
            "download_uri": self.download_uri,
            "status": self.status,
            "detail": self.detail,
        }


def reverify_distributions(
    repository_root: str | Path,
    containers: Sequence[str] = (),
    *,
    fetcher: Fetcher | None = None,
    resolver: Resolver | None = None,
    scratch: Path | None = None,
) -> tuple[Reverification, ...]:
    """Download recorded distributions again and check them (network, opt-in).

    The fresh availability check that historical verification never is: each
    distribution is downloaded in full from its recorded address and its
    checksum and size compared with the record. A match is recorded as a
    ``fresh`` verification; a different file (``changed``) or a failed
    download (``failed``) is reported and nothing is changed, so the person
    decides what to do. The draft itself is never edited.
    """
    root = Path(repository_root).resolve()
    data = _draft(root)
    wanted = set(containers)
    known = {
        str(item.get("id"))
        for item in data.get("containers") or []
        if isinstance(item, dict)
    }
    unknown = sorted(wanted - known)
    if unknown:
        raise LayerError(f"unknown container(s): {', '.join(unknown)}")
    options: dict[str, Any] = {"scratch": scratch}
    if fetcher is not None:
        options["fetcher"] = fetcher
    if resolver is not None:
        options["resolver"] = resolver
    results: list[Reverification] = []
    fresh: dict[str, dict[str, Any]] = {}
    for item in data.get("containers") or []:
        if not isinstance(item, dict) or not isinstance(item.get("distribution"), dict):
            continue
        identifier = str(item.get("id"))
        if wanted and identifier not in wanted:
            continue
        distribution = item["distribution"]
        uri = str(distribution.get("download_uri"))
        try:
            image = verify_image_url(uri, **options)
        except ContainerServiceError as error:
            results.append(Reverification(identifier, uri, "failed", str(error)))
            continue
        if image.sha256 != distribution.get(
            "sha256"
        ) or image.size_bytes != distribution.get("size_bytes"):
            results.append(
                Reverification(
                    identifier,
                    uri,
                    "changed",
                    f"the file now has SHA-256 {image.sha256} and "
                    f"{image.size_bytes} bytes, not the recorded "
                    f"{distribution.get('sha256')}; nothing was changed",
                )
            )
            continue
        fresh[identifier] = {
            "sha256": image.sha256,
            "download_uri": uri,
            "final_url": image.final_url,
            "basis": "fresh",
        }
        results.append(
            Reverification(
                identifier, uri, "fresh", "downloaded again; checksum and size match"
            )
        )
    if fresh:

        def record(state: ReviewState) -> None:
            state.section("verified").update(fresh)

        update_review_state(root, LAYER, record)
    return tuple(results)


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
    # Candidate review status never gates the inventory (ADR-0057). What
    # matters is the content: unresolved items and modules left out.
    listed = {
        code_key(item)
        for item in data.get("components") or []
        if isinstance(item, dict)
    }
    missing = sorted(
        str(entry["candidate"].get("path"))
        + (
            f" ({entry['candidate']['process']})"
            if entry["candidate"].get("process")
            else ""
        )
        for entry in review.candidates.values()
        if isinstance(entry, dict)
        and entry.get("status") != "rejected"
        and isinstance(entry.get("candidate"), dict)
        and code_key(entry["candidate"]) not in listed
        and _code_exists(
            root,
            str(entry["candidate"].get("path")),
            entry["candidate"].get("process"),
        )
    )
    if missing:
        issues.append(
            issue(
                LAYER,
                "/components",
                "module_not_listed",
                f"{len(missing)} module(s) in the repository are not in the "
                f"inventory: {', '.join(missing[:10])}"
                + (" ..." if len(missing) > 10 else "")
                + "; add them, or remove them on purpose",
                Severity.WARNING,
            )
        )
    for index, component in enumerate(data.get("components") or []):
        if not isinstance(component, dict):
            continue
        if (
            not component.get("container_id")
            and not component.get(UNRESOLVED)
            and isinstance(component.get("path"), str)
        ):
            declared = _declared_sources(
                root, str(component["path"]), component.get("process")
            )
            if declared:
                issues.append(
                    issue(
                        LAYER,
                        f"/components/{index}/container_id",
                        "container_not_mapped",
                        f"{component.get('id')}: {declared[0].location} declares a "
                        "container, but the inventory maps none; set container_id, "
                        f"or record what stops it under {UNRESOLVED}",
                    )
                )
        for item in component.get(UNRESOLVED) or []:
            issues.append(
                issue(
                    LAYER,
                    f"/components/{index}/{UNRESOLVED}",
                    "unresolved_component",
                    f"{component.get('id')}: {item}; resolve it in the draft and "
                    f"remove it from {UNRESOLVED}",
                )
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
        if (
            distribution is not None
            and isinstance(verified, dict)
            and verified.get("adopted_from")
            and verified.get("sha256") == distribution.sha256
        ):
            issues.append(
                issue(
                    LAYER,
                    f"/containers/{index}/distribution",
                    "adopted_distribution",
                    f"{container.id}: historical verification, reused because the "
                    "lock, its verification record, the distribution and the "
                    "source images all agree; it was not downloaded again, so "
                    "its current availability is unknown; check it now with "
                    "`nf-splice containers reverify`",
                    Severity.WARNING,
                )
            )
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
            (
                {key: value for key, value in item.items() if key != UNRESOLVED}
                for item in data.get("components") or []
                if isinstance(item, dict)
            ),
            key=lambda item: str(item.get("id")),
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
