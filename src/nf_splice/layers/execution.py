"""Execution-profile layer: profile metadata in YAML, configuration in native files.

``execution-profiles.draft.yaml`` owns each profile's identity, description,
executor, container engine, the single default and a *reference* to its
configuration. The configuration itself lives in native Nextflow files and
is never duplicated in YAML (ADR-0057):

- ``config: {draft: <name>.draft.config}`` names an editable file below
  ``.splice-local/drafts/configs/``, authored by a person or an agent in any
  editor and published byte-for-byte (``config_strategy: authored``);
- ``config: {adopt: conf/x.config}`` publishes a developer-owned repository
  config unchanged (``config_strategy: adopted``).

Initialisation seeds a usable default profile and its config scaffold with
the two conventional parameter sections, or, when an earlier bundle exists,
its profiles and configs. Detected repository profiles stay advisory
evidence; nothing waits for them to be reviewed. Site-specific values
(accounts, queues, paths) are deployment configuration, never invented.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from nf_splice.contracts import (
    EXECUTION_PROFILES_FAMILY,
    data_document_header,
    validate_contract_document,
)
from nf_splice.domain.execution import (
    ContainerEngine,
    ExecutionEngine,
    ExecutionExecutor,
    ExecutionProfileCandidate,
    ExecutionProfileType,
)
from nf_splice.drafts import (
    DRAFTS_DIR,
    DraftConflictError,
    PatchOp,
    canonical_json,
    create_file,
    read_file,
    replace_file,
    sha256,
    text_diff,
)
from nf_splice.inspectors.profiles import (
    _ACCOUNT_LITERAL,
    _DEMO_TEST,
    _PARAM_ASSIGNMENT,
    _PERSONAL_PATH,
    _SECRET_ASSIGNMENT,
    ProfileDiscoveryError,
    discover_profiles,
    safe_relative,
    strip_comments,
)
from nf_splice.layers.base import (
    ChangeContext,
    DraftIssue,
    EditResult,
    LayerError,
    LayerValidation,
    ReviewState,
    Severity,
    _record,
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
from nf_splice.layers.inputs import iter_parameters, validate_inputs_draft

LAYER = "execution-profiles"
PENDING = "pending"
SEEDED = "seeded"
CONFIGS_DIR = f"{DRAFTS_DIR}/configs"
DRAFT_CONFIG_SUFFIX = ".draft.config"
USER_SECTION = "// ***** User Pipeline Input Params *****"
PLATFORM_SECTION = "// ***** SPLICE Pipeline Input Params *****"
CONFIG_DRAFT_MARKER = (
    "// nf-SPLICE draft config: not for ingestion; promote with nf-splice draft promote"
)
#: Published ``config_strategy`` values.
AUTHORED = "authored"
ADOPTED = "adopted"
_CONFIG_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_PROFILE_ID = re.compile(r"^[a-z][a-z0-9_-]*$")
_ENGINE_BLOCKS = {
    ContainerEngine.SINGULARITY: (
        "singularity {\n    enabled    = true\n    autoMounts = true\n}"
    ),
    ContainerEngine.APPTAINER: (
        "apptainer {\n    enabled    = true\n    autoMounts = true\n}"
    ),
    ContainerEngine.DOCKER: "docker {\n    enabled = true\n}",
    ContainerEngine.PODMAN: "podman {\n    enabled = true\n}",
    ContainerEngine.CHARLIECLOUD: "charliecloud {\n    enabled = true\n}",
    ContainerEngine.SHIFTER: "shifter {\n    enabled = true\n}",
    ContainerEngine.CONDA: "conda {\n    enabled = true\n}",
}
_SECRET_NAME = re.compile(r"(?i)(password|passwd|secret|token|credential|api_?key)")
_FIELDS = (
    "id",
    "name",
    "description",
    "type",
    "engine",
    "executor",
    "container_engine",
    "config",
    "site_parameters",
    "source_profile",
    "evidence",
)


def profile_id(source_profile: str) -> str:
    """A readable profile ID derived from a profile or display name."""
    slug = re.sub(r"[^a-z0-9_-]+", "-", source_profile.lower()).strip("-_")
    if not slug or not slug[0].isalpha():
        slug = f"profile-{slug}".rstrip("-")
    return slug


def config_file_path(name: str) -> str:
    """Repository-relative path of an authored config named ``name``."""
    base = name.removesuffix(DRAFT_CONFIG_SUFFIX).removesuffix(".config")
    if not _CONFIG_NAME.fullmatch(base):
        raise LayerError(
            f"config name {name!r}: use lower-case letters, digits, - and _ only"
        )
    return f"{CONFIGS_DIR}/{base}{DRAFT_CONFIG_SUFFIX}"


def config_draft_path(identifier: str) -> str:
    """The authored config path conventionally used for a profile ID."""
    return config_file_path(identifier)


def groovy_literal(value: Any) -> str:
    """Render a JSON value as an escaped Nextflow/Groovy literal."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return json.dumps(value)
    if isinstance(value, str):
        escaped = (
            value.replace("\\", "\\\\")
            .replace("'", "\\'")
            .replace("\n", "\\n")
            .replace("$", "\\$")
        )
        return f"'{escaped}'"
    if isinstance(value, list):
        return "[" + ", ".join(groovy_literal(item) for item in value) + "]"
    if isinstance(value, Mapping):
        return (
            "["
            + ", ".join(
                f"{key}: {groovy_literal(item)}" for key, item in sorted(value.items())
            )
            + "]"
        )
    raise LayerError(f"cannot render {type(value).__name__} as a Nextflow literal")


def _params_block(values: Mapping[str, Any]) -> str:
    if not values:
        return "params {\n}"
    lines = [f"    {name} = {groovy_literal(values[name])}" for name in sorted(values)]
    return "params {\n" + "\n".join(lines) + "\n}"


def config_scaffold(
    identifier: str,
    *,
    executor: str | None,
    container_engine: str | None,
    process: Mapping[str, Any] | None = None,
    user_params: Mapping[str, Any] | None = None,
    platform_params: Mapping[str, Any] | None = None,
    site_parameters: Sequence[Mapping[str, str]] = (),
) -> str:
    """A starting native config for a profile; written once, then authored."""
    lines = [
        CONFIG_DRAFT_MARKER,
        f"// Execution profile {identifier!r}: authoritative, editable Nextflow "
        "configuration.",
        "// Add any valid Nextflow configuration. nf-splice publishes this file "
        "as written",
        "// (without these first lines) and never regenerates it.",
        "",
        "process {",
    ]
    if executor:
        lines.append(f"    executor = {groovy_literal(executor)}")
    for name in sorted(process or {}):
        lines.append(f"    {name} = {groovy_literal((process or {})[name])}")
    for site in site_parameters:
        lines.append(
            f"    // deployment-managed: {site['name']} - {site['description']}"
        )
    lines.append("}")
    if container_engine:
        lines.extend(["", _ENGINE_BLOCKS[ContainerEngine(container_engine)]])
    lines.extend(
        [
            "",
            USER_SECTION,
            _params_block(user_params or {}),
            "",
            PLATFORM_SECTION,
            _params_block(platform_params or {}),
            "",
        ]
    )
    return "\n".join(lines)


def render_generated_config(profile: Mapping[str, Any]) -> str:
    """Backward-compatible name for :func:`config_scaffold`."""
    generated = profile.get("generated") or {}
    return config_scaffold(
        str(profile["id"]),
        executor=str(profile["executor"]),
        container_engine=str(profile["container_engine"]),
        process=generated.get("process"),
        user_params=generated.get("user_params"),
        platform_params=generated.get("platform_params"),
        site_parameters=profile.get("site_parameters") or (),
    )


# ------------------------------------------------------------------ seeding


def _published_profiles(root: Path) -> tuple[list[dict[str, Any]], str | None]:
    """Profiles of an earlier bundle (0.3.0 or older) with their config bytes."""
    path = root / "splice" / "execution-profiles.json"
    if path.is_symlink() or not path.is_file():
        return [], None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return [], None
    if not isinstance(loaded, dict) or not isinstance(loaded.get("profiles"), list):
        return [], None
    found = []
    default = loaded.get("default_profile")
    for item in loaded["profiles"]:
        if not isinstance(item, dict) or not isinstance(item.get("config"), str):
            continue
        config = safe_relative(root, f"splice/{item['config']}")
        if config is None:
            continue
        identifier = profile_id(str(item.get("id") or item.get("name") or "profile"))
        found.append(
            {
                "source": item,
                "id": identifier,
                "config_path": config,
            }
        )
        if item.get("default") is True and default is None:
            default = identifier
    if default is None and any(item["id"] == "default" for item in found):
        default = "default"
    return found, str(default) if default else None


def _choice(values: Sequence[str], vocabulary: type) -> str | None:
    for value in values:
        try:
            return str(vocabulary(value).value)
        except ValueError:
            continue
    return None


def seed_profiles(
    root: Path, candidates: Sequence[ExecutionProfileCandidate]
) -> tuple[dict[str, Any], dict[str, bytes], list[str]]:
    """Build the first profile draft and the config files it references.

    An earlier bundle's profiles and configs are the best evidence and are
    carried over. Otherwise one ``default`` profile is created whose config
    is a scaffold for the container engine the pipeline already uses.
    Values the evidence cannot give (a profile's type) stay null.
    """
    published, default = _published_profiles(root)
    profiles: list[dict[str, Any]] = []
    configs: dict[str, bytes] = {}
    notes: list[str] = []
    if published:
        for item in published:
            source = item["source"]
            name = config_file_path(item["id"])
            payload = (root / item["config_path"]).read_bytes()
            configs[name] = (CONFIG_DRAFT_MARKER + "\n").encode("utf-8") + payload
            profile_type = source.get("type")
            profiles.append(
                {
                    "id": item["id"],
                    "name": str(source.get("name") or item["id"]),
                    "description": source.get("description"),
                    "type": profile_type
                    if profile_type in {value.value for value in ExecutionProfileType}
                    else None,
                    "engine": ExecutionEngine.NEXTFLOW.value,
                    "executor": source.get("executor"),
                    "container_engine": source.get("container_engine"),
                    "config": {"draft": PurePosixPath(name).name},
                    "site_parameters": list(source.get("site_parameters") or []),
                    "evidence": [item["config_path"], "splice/execution-profiles.json"],
                }
            )
        notes.append(
            f"seeded {len(profiles)} profile(s) and their configs from the "
            "published splice/execution-profiles.json"
        )
    else:
        engines = [engine for item in candidates for engine in item.container_engines]
        preferred = [
            engine
            for engine in ("singularity", "apptainer", "docker", "podman")
            if engine in engines
        ]
        engine = _choice(preferred or engines, ContainerEngine)
        name = config_file_path("default")
        configs[name] = config_scaffold(
            "default", executor="local", container_engine=engine
        ).encode("utf-8")
        profiles.append(
            {
                "id": "default",
                "name": "Default",
                "description": None,
                "type": None,
                "engine": ExecutionEngine.NEXTFLOW.value,
                "executor": "local",
                "container_engine": engine,
                "config": {"draft": PurePosixPath(name).name},
                "site_parameters": [],
                "evidence": ["nf-splice default scaffold"],
            }
        )
        default = "default"
        notes.append(
            "seeded a default profile with a native config scaffold "
            f"({CONFIGS_DIR}/default{DRAFT_CONFIG_SUFFIX}); describe it and "
            "edit the config for your deployment"
        )
    return {"default_profile": default, "profiles": profiles}, configs, notes


def discover_execution(
    repository_root: str | Path,
) -> tuple[ExecutionProfileCandidate, ...]:
    """Seed a usable draft and config files if absent; refresh evidence.

    Config files are created only when absent and are never overwritten.
    Profiles detected in ``nextflow.config`` are recorded as advisory
    evidence; they never block validation.
    """
    root = Path(repository_root).resolve()
    try:
        discovered = (
            discover_profiles(root) if (root / "nextflow.config").is_file() else ()
        )
    except ProfileDiscoveryError as error:
        raise LayerError(str(error)) from error
    seed, configs, _notes = seed_profiles(root, [item for item, _ in discovered])
    if not read_layer(root, LAYER).file.exists:
        for relative, payload in configs.items():
            create_file(root, relative, payload)
    seed_draft(
        root,
        LAYER,
        seed,
        header=(
            "nf-SPLICE execution profiles draft (authoritative, editable).",
            "Profile metadata and references only: each profile's Nextflow "
            "configuration",
            f"is the native file it names under {CONFIGS_DIR}/.",
        ),
    )

    def merge(state: ReviewState) -> None:
        for candidate, evidence in discovered:
            existing = state.candidates.get(candidate.id)
            if existing is None or existing.get("status") == PENDING:
                state.candidates[candidate.id] = {
                    "status": PENDING,
                    "candidate": candidate.model_dump(mode="json"),
                    "evidence": sorted({item.provenance.location for item in evidence}),
                }

    update_review_state(root, LAYER, merge)
    return pending_profiles(root)


def pending_profiles(
    repository_root: str | Path,
) -> tuple[ExecutionProfileCandidate, ...]:
    """Detected repository profiles nobody has acted on (advisory only)."""
    state = load_review_state(Path(repository_root).resolve(), LAYER)
    return tuple(
        ExecutionProfileCandidate.model_validate(entry["candidate"])
        for _, entry in sorted(state.candidates.items())
        if entry.get("status") == PENDING
    )


def _draft(root: Path) -> dict[str, Any]:
    state = read_layer(root, LAYER)
    if state.draft is None or not isinstance(state.draft.data, dict):
        raise LayerError("execution-profiles.draft.yaml is missing or malformed")
    data: dict[str, Any] = state.draft.data
    return data


def _vocabulary(
    profile_type: str, executor: str, container_engine: str
) -> tuple[str, str, str]:
    try:
        return (
            ExecutionProfileType(profile_type).value,
            ExecutionExecutor(executor).value,
            ContainerEngine(container_engine).value,
        )
    except ValueError as error:
        raise LayerError(str(error)) from error


# ------------------------------------------------------------ native configs


def read_config_draft(repository_root: str | Path, name: str) -> dict[str, Any]:
    """Read one authored config: its text, hash and path (read-only)."""
    root = Path(repository_root).resolve()
    relative = config_file_path(name)
    state = read_file(root, relative)
    return {
        "path": relative,
        "exists": state.exists,
        "sha256": state.sha256,
        "text": state.text,
    }


def list_config_drafts(repository_root: str | Path) -> tuple[str, ...]:
    """Authored config files present below ``.splice-local/drafts/configs/``."""
    directory = Path(repository_root).resolve() / CONFIGS_DIR
    if not directory.is_dir() or directory.is_symlink():
        return ()
    return tuple(
        f"{CONFIGS_DIR}/{item.name}"
        for item in sorted(directory.iterdir())
        if item.name.endswith(DRAFT_CONFIG_SUFFIX)
        and item.is_file()
        and not item.is_symlink()
    )


def write_config_draft(
    repository_root: str | Path,
    name: str,
    text: str,
    context: ChangeContext,
    *,
    expected_sha256: str | None,
    write: bool = True,
) -> EditResult:
    """Create or replace one authored native config, safely.

    ``expected_sha256`` is the hash the caller read (``None``: the file must
    not exist yet), so a concurrent edit in an editor is never overwritten.
    Only safe content is refused (an embedded secret); configuration that
    still fails validation is saved, so it can be repaired in later edits.
    """
    root = Path(repository_root).resolve()
    relative = config_file_path(name)
    if write and not context.approved:
        raise LayerError(f"{relative}: explicit approval is required")
    body = text if text.endswith("\n") else text + "\n"
    if "\x00" in body:
        raise LayerError(f"{relative}: a config is text")
    for number, line in enumerate(body.splitlines(), start=1):
        if _SECRET_ASSIGNMENT.search(strip_comments(line)):
            raise LayerError(
                f"{relative} line {number}: never write a secret into a config; "
                "read it from the environment or the deployment's secret store"
            )
    if not body.startswith(CONFIG_DRAFT_MARKER):
        body = f"{CONFIG_DRAFT_MARKER}\n{body}"
    current = read_file(root, relative)
    if current.sha256 != expected_sha256:
        raise DraftConflictError(
            relative,
            "the config changed on disk since it was read; read it again first",
        )
    rendered = text_diff(relative, current.text or "", body)
    if not write:
        return EditResult(LAYER, relative, rendered, False, None, {"path": relative})
    wrote = False
    if body != (current.text or ""):
        replace_file(
            root, relative, body.encode("utf-8"), expected_sha256=expected_sha256
        )
        wrote = True
    event = _record(
        root,
        LAYER,
        "write_config",
        context,
        (relative,),
        current.sha256,
        sha256(body.encode("utf-8")),
    )

    def mutate(review: ReviewState) -> None:
        review.events.append(event.model_dump(mode="json"))

    update_review_state(root, LAYER, mutate)
    return EditResult(LAYER, relative, rendered, wrote, event, {"path": relative})


# ------------------------------------------------------------ conveniences


def _add_profile(
    root: Path,
    profile: dict[str, Any],
    context: ChangeContext,
    *,
    action: str,
    config_text: str | None = None,
    review: Any = None,
) -> EditResult:
    data = _draft(root)
    profiles = list(data.get("profiles") or [])
    if any(
        item.get("id") == profile["id"] for item in profiles if isinstance(item, dict)
    ):
        raise LayerError(f"execution profile {profile['id']} already exists")
    if config_text is not None:
        create_file(
            root,
            config_file_path(profile["config"]["draft"]),
            config_text.encode("utf-8"),
        )
    return edit_draft(
        root,
        LAYER,
        [PatchOp("add", f"/profiles/{len(profiles)}", profile)],
        context,
        action=action,
        review=review,
    )


def review_profile(
    repository_root: str | Path,
    candidate_id: str,
    context: ChangeContext,
    *,
    profile_type: str,
    description: str,
    executor: str,
    container_engine: str,
    config_source: str | None = None,
    generate: Mapping[str, Any] | None = None,
    site_parameters: Sequence[Mapping[str, str]] = (),
) -> EditResult:
    """Optional convenience: add a detected profile to the draft.

    ``config_source`` adopts a repository config unchanged; otherwise a
    native config scaffold is created (``generate`` may prefill process
    settings and parameter sections once). Editing the YAML and config files
    directly does the same.
    """
    root = Path(repository_root).resolve()
    state = load_review_state(root, LAYER)
    entry = state.candidates.get(candidate_id)
    if not isinstance(entry, dict):
        raise LayerError(f"unknown execution profile candidate {candidate_id!r}")
    candidate = ExecutionProfileCandidate.model_validate(entry["candidate"])
    selected_type, selected_executor, selected_engine = _vocabulary(
        profile_type, executor, container_engine
    )
    if candidate.executors and selected_executor not in candidate.executors:
        raise LayerError(f"executor {selected_executor!r} is not in detected evidence")
    if (
        candidate.container_engines
        and selected_engine not in candidate.container_engines
    ):
        raise LayerError(
            f"container engine {selected_engine!r} is not in detected evidence"
        )
    if config_source is not None and generate is not None:
        raise LayerError("choose one config route: adopt a source or author a config")
    identifier = profile_id(candidate.source_profile)
    config: dict[str, Any]
    text = None
    if config_source is not None:
        safe = safe_relative(root, config_source.strip())
        if safe is None or not safe.endswith(".config") or safe.startswith("splice/"):
            raise LayerError(
                "adopted config must be a repository-local .config outside splice/"
            )
        config = {"adopt": safe}
    else:
        config = {"draft": PurePosixPath(config_file_path(identifier)).name}
        text = config_scaffold(
            identifier,
            executor=selected_executor,
            container_engine=selected_engine,
            process=(generate or {}).get("process"),
            user_params=(generate or {}).get("user_params"),
            platform_params=(generate or {}).get("platform_params"),
            site_parameters=site_parameters,
        )
    profile: dict[str, Any] = {
        "id": identifier,
        "name": candidate.name,
        "description": description.strip(),
        "type": selected_type,
        "engine": ExecutionEngine.NEXTFLOW.value,
        "executor": selected_executor,
        "container_engine": selected_engine,
        "source_profile": candidate.source_profile,
        "config": config,
        "site_parameters": [dict(item) for item in site_parameters],
        "evidence": entry.get("evidence", []),
    }

    def mark(review: ReviewState) -> None:
        review.candidates[candidate_id]["status"] = "accepted"

    return _add_profile(
        root, profile, context, action="review_profile", config_text=text, review=mark
    )


def add_generated_profile(
    repository_root: str | Path,
    context: ChangeContext,
    *,
    name: str,
    description: str,
    profile_type: str,
    executor: str,
    container_engine: str,
    generate: Mapping[str, Any] | None = None,
    site_parameters: Sequence[Mapping[str, str]] = (),
) -> EditResult:
    """Optional convenience: add a profile with a new native config scaffold."""
    root = Path(repository_root).resolve()
    selected_type, selected_executor, selected_engine = _vocabulary(
        profile_type, executor, container_engine
    )
    identifier = profile_id(name)
    text = config_scaffold(
        identifier,
        executor=selected_executor,
        container_engine=selected_engine,
        process=(generate or {}).get("process"),
        user_params=(generate or {}).get("user_params"),
        platform_params=(generate or {}).get("platform_params"),
        site_parameters=site_parameters,
    )
    profile = {
        "id": identifier,
        "name": name,
        "description": description.strip(),
        "type": selected_type,
        "engine": ExecutionEngine.NEXTFLOW.value,
        "executor": selected_executor,
        "container_engine": selected_engine,
        "config": {"draft": PurePosixPath(config_file_path(identifier)).name},
        "site_parameters": [dict(item) for item in site_parameters],
        "evidence": ["nf-splice scaffold"],
    }
    return _add_profile(
        root, profile, context, action="add_generated_profile", config_text=text
    )


#: Reviewable starting point for a Slurm/HPC deployment (no site literals).
SLURM_SITE_PARAMETERS = (
    {"name": "queue", "description": "Slurm partition chosen by the deployment"},
    {
        "name": "clusterOptions",
        "description": "Site account/QoS options supplied by the deployment",
    },
)


def add_slurm_default_candidate(
    repository_root: str | Path, context: ChangeContext
) -> EditResult:
    """Optional convenience: add a Slurm production profile scaffold."""
    return add_generated_profile(
        repository_root,
        context,
        name="SPLICE Slurm",
        description="SPLICE production execution on a Slurm cluster.",
        profile_type="production",
        executor="slurm",
        container_engine="singularity",
        generate={"process": {"queueSize": 50}},
        site_parameters=SLURM_SITE_PARAMETERS,
    )


def reject_profile(
    repository_root: str | Path, candidate_id: str, reason: str, context: ChangeContext
) -> None:
    """Optional: record that a detected profile is deliberately unsupported."""
    if not reason.strip():
        raise LayerError("rejecting an execution profile requires a reason")
    root = Path(repository_root).resolve()
    if candidate_id not in load_review_state(root, LAYER).candidates:
        raise LayerError(f"unknown execution profile candidate {candidate_id!r}")

    def mark(state: ReviewState) -> None:
        state.candidates[candidate_id].update({"status": "rejected", "reason": reason})

    record_decision(root, LAYER, "reject_profile", context, (), mark)


def set_default_profile(
    repository_root: str | Path, identifier: str, context: ChangeContext
) -> EditResult:
    """Select the single default profile."""
    root = Path(repository_root).resolve()
    data = _draft(root)
    if identifier not in {item.get("id") for item in data.get("profiles") or []}:
        raise LayerError(f"unknown execution profile {identifier!r}")
    return edit_draft(
        root,
        LAYER,
        ops_for(data, {"/default_profile": identifier}),
        context,
        action="set_default_profile",
    )


def profile_ids(repository_root: str | Path) -> tuple[str, ...]:
    """IDs of the profiles in the draft."""
    data = _draft(Path(repository_root).resolve())
    return tuple(
        str(item["id"])
        for item in data.get("profiles") or []
        if isinstance(item, dict) and item.get("id")
    )


_EDITABLE_PROFILE_FIELDS = {
    "name",
    "description",
    "type",
    "executor",
    "container_engine",
    "config_draft",
    "config_adopt",
}


def update_profile(
    repository_root: str | Path,
    identifier: str,
    changes: Mapping[str, Any],
    context: ChangeContext,
) -> EditResult:
    """Change metadata of one profile in the draft (targeted edit).

    ``config_draft`` / ``config_adopt`` point the profile at a native file;
    the configuration itself is edited in that file, never here.
    """
    root = Path(repository_root).resolve()
    unknown = sorted(set(changes) - _EDITABLE_PROFILE_FIELDS)
    if unknown:
        raise LayerError(
            f"unknown profile field(s) {', '.join(unknown)}; edit "
            f"{', '.join(sorted(_EDITABLE_PROFILE_FIELDS))}"
        )
    data = _draft(root)
    index = next(
        (
            position
            for position, item in enumerate(data.get("profiles") or [])
            if isinstance(item, dict) and item.get("id") == identifier
        ),
        None,
    )
    if index is None:
        raise LayerError(f"unknown execution profile {identifier!r}")
    pointers: dict[str, Any] = {}
    for key, value in changes.items():
        if key == "config_draft":
            config_file_path(str(value))
            pointers[f"/profiles/{index}/config"] = {
                "draft": PurePosixPath(config_file_path(str(value))).name
            }
        elif key == "config_adopt":
            pointers[f"/profiles/{index}/config"] = {"adopt": str(value)}
        else:
            pointers[f"/profiles/{index}/{key}"] = value
    return edit_draft(
        root, LAYER, ops_for(data, pointers), context, action="update_profile"
    )


# ------------------------------------------------------------ validation


def _safety_issues(
    text: str, *, path: str, profile_type: str, user_params: set[str], authored: bool
) -> list[DraftIssue]:
    found = []
    section = None
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped == USER_SECTION:
            section = "user"
        elif stripped == PLATFORM_SECTION:
            section = "platform"
        code = strip_comments(line)
        pointer = f"line {line_number}"
        if _SECRET_ASSIGNMENT.search(code):
            found.append(
                issue(LAYER, pointer, "unsafe_config", "embedded secret", path=path)
            )
        if _PERSONAL_PATH.search(code):
            found.append(
                issue(
                    LAYER, pointer, "unsafe_config", "personal absolute path", path=path
                )
            )
        if _ACCOUNT_LITERAL.search(code):
            found.append(
                issue(LAYER, pointer, "unsafe_config", "literal HPC account", path=path)
            )
        if profile_type == "production" and _DEMO_TEST.search(code):
            found.append(
                issue(LAYER, pointer, "unsafe_config", "test/demo setting", path=path)
            )
        if not authored or section is None:
            for parameter in _PARAM_ASSIGNMENT.findall(code):
                if parameter in user_params:
                    found.append(
                        issue(
                            LAYER,
                            pointer,
                            "unsafe_config",
                            f"user-editable parameter override {parameter!r}",
                            path=path,
                        )
                    )
    return found


def section_parameters(text: str) -> dict[str, list[tuple[str, int]]]:
    """Parameters assigned in each conventional section.

    ``{"user": [(name, line)], "platform": [...]}``. A section runs from its
    heading to the next ``// *****`` heading; within it, top-level
    assignments of ``params { }`` blocks and ``params.x = ...`` lines count.
    """
    found: dict[str, list[tuple[str, int]]] = {"user": [], "platform": []}
    section: str | None = None
    depth = 0
    for number, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if stripped == USER_SECTION:
            section, depth = "user", 0
            continue
        if stripped == PLATFORM_SECTION:
            section, depth = "platform", 0
            continue
        if stripped.startswith("// *****"):
            section, depth = None, 0
            continue
        if section is None:
            continue
        code = strip_comments(raw)
        if depth == 0:
            opening = re.match(r"^\s*params\s*\{", code)
            if opening:
                depth = 1 + code[opening.end() :].count("{") - code.count("}")
                depth = max(depth, 0)
                continue
            assigned = re.match(r"^\s*params\.([A-Za-z_]\w*)\s*=(?!=)", code)
            if assigned:
                found[section].append((assigned.group(1), number))
            continue
        assigned = re.match(r"^\s*([A-Za-z_]\w*)\s*=(?!=)", code)
        if depth == 1 and assigned:
            found[section].append((assigned.group(1), number))
        depth = max(depth + code.count("{") - code.count("}"), 0)
    return found


def _section_policy_issues(
    text: str, path: str, policies: Mapping[str, set[str]]
) -> list[DraftIssue]:
    """Check the parameter sections of an authored config against the contract.

    A value in the user section must be one users may change; one in the
    SPLICE section must not be (it would replace the user's choice): it is
    either platform-set or fixed for the deployment. Secret-like names are
    never written into a config.
    """
    found = []
    for section, assignments in section_parameters(text).items():
        for name, line in assignments:
            pointer = f"line {line}"
            if _SECRET_NAME.search(name):
                found.append(
                    issue(
                        LAYER,
                        pointer,
                        "secret_literal",
                        f"never write secret-like parameter {name!r} into a config",
                        path=path,
                    )
                )
                continue
            if not policies:
                continue
            allowed = policies.get(name)
            if allowed is None:
                found.append(
                    issue(
                        LAYER,
                        pointer,
                        "section_policy",
                        f"{name!r} is not a parameter of the input contract",
                        Severity.WARNING,
                        path=path,
                    )
                )
            elif section == "user" and "user" not in allowed:
                found.append(
                    issue(
                        LAYER,
                        pointer,
                        "section_policy",
                        f"{name!r} is in the user section but users may not change "
                        "it (x-splice-access)",
                        path=path,
                    )
                )
            elif section == "platform" and "user" in allowed:
                # A deployment value here would silently replace what a user
                # chose; fixed values ([]) and platform-set ones belong here.
                found.append(
                    issue(
                        LAYER,
                        pointer,
                        "section_policy",
                        f"{name!r} is in the SPLICE section but users may change "
                        "it (x-splice-access); move it to the user section or "
                        "stop users editing it",
                        path=path,
                    )
                )
    return found


def _input_policies(root: Path) -> tuple[dict[str, set[str]], list[DraftIssue]]:
    validation = validate_inputs_draft(root)
    payload = validation.files.get("inputs.schema.json")
    if payload is None:
        return {}, [
            issue(
                LAYER,
                "",
                "inputs_not_ready",
                "parameter overrides need a ready inputs draft",
                Severity.WARNING,
            )
        ]
    schema = json.loads(payload)
    return {
        item.name: set(item.editable_by or ()) for item in iter_parameters(schema)
    }, []


def profile_config(
    root: Path, profile: Mapping[str, Any]
) -> tuple[str | None, str | None, str | None]:
    """(strategy, repository-relative path, problem) of a profile's config.

    Reads the current shape (``draft``/``adopt``) and the earlier one
    (``strategy: generated|adopted``) of the same unreleased contract.
    """
    config = profile.get("config")
    if not isinstance(config, Mapping):
        return None, None, "config must name a draft config or an adopted file"
    if "draft" in config or config.get("strategy") == "generated":
        name = config.get("draft") or profile.get("id")
        try:
            return AUTHORED, config_file_path(str(name)), None
        except LayerError as error:
            return AUTHORED, None, str(error)
    source = config.get("adopt") or (
        config.get("source") if config.get("strategy") == "adopted" else None
    )
    if isinstance(source, str):
        safe = safe_relative(root, source)
        if safe is None or not safe.endswith(".config") or safe.startswith("splice/"):
            return (
                ADOPTED,
                None,
                f"adopted config {source!r} must be a repository .config outside "
                "splice/",
            )
        return ADOPTED, safe, None
    return None, None, "config must be {draft: <name>.draft.config} or {adopt: <path>}"


def _publishable(text: str) -> bytes:
    return (
        "\n".join(line for line in text.splitlines() if line != CONFIG_DRAFT_MARKER)
        .lstrip("\n")
        .encode("utf-8")
        + b"\n"
    )


def validate_execution_draft(repository_root: str | Path) -> LayerValidation:
    """Validate profiles, defaults and configs; compile the profile catalogue.

    Reads every referenced config from disk now, so an edit made in an
    editor since the last validation is what is checked and published.
    """
    root = Path(repository_root).resolve()
    state = read_layer(root, LAYER)
    if state.draft is None or not isinstance(state.draft.data, dict):
        code = "missing_draft" if not state.file.exists else "syntax"
        return LayerValidation(
            LAYER, (issue(LAYER, "", code, str(state.error or code)),)
        )
    data = strip_marker(state.draft.data)
    issues: list[DraftIssue] = []
    unknown = sorted(set(data) - {"default_profile", "profiles"})
    issues.extend(
        issue(LAYER, f"/{name}", "unknown_field", f"unknown field {name!r}")
        for name in unknown
    )
    profiles = [item for item in data.get("profiles") or [] if isinstance(item, dict)]
    if not profiles:
        issues.append(
            issue(LAYER, "/profiles", "missing_required", "define at least one profile")
        )
    identifiers = [item.get("id") for item in profiles]
    if len(identifiers) != len(set(identifiers)):
        issues.append(
            issue(LAYER, "/profiles", "duplicate_id", "profile ids must be unique")
        )
    default = data.get("default_profile")
    if profiles and default is None:
        issues.append(
            issue(
                LAYER,
                "/default_profile",
                "missing_default",
                "name the single default profile in default_profile",
            )
        )
    elif default is not None and default not in identifiers:
        issues.append(
            issue(
                LAYER,
                "/default_profile",
                "dangling_default",
                f"unknown profile {default!r}",
            )
        )
    policies, policy_issues = _input_policies(root)
    issues.extend(policy_issues)
    user_params = {name for name, allowed in policies.items() if "user" in allowed}
    configs: dict[str, bytes] = {}
    referenced: set[str] = set()
    rendered = []
    for index, profile in enumerate(profiles):
        pointer = f"/profiles/{index}"
        identifier = str(profile.get("id"))
        if not _PROFILE_ID.fullmatch(identifier):
            issues.append(
                issue(
                    LAYER,
                    f"{pointer}/id",
                    "invalid_value",
                    f"profile id {identifier!r}: start with a letter; use "
                    "lower-case letters, digits, - and _",
                )
            )
        for key in sorted(set(profile) - set(_FIELDS) - {"generated"}):
            issues.append(
                issue(LAYER, f"{pointer}/{key}", "unknown_field", f"unknown {key!r}")
            )
        if "generated" in profile:
            issues.append(
                issue(
                    LAYER,
                    f"{pointer}/generated",
                    "ignored_settings",
                    "settings under 'generated' are not used: the profile's "
                    "configuration is its config file; move them there and "
                    "remove this block",
                    Severity.WARNING,
                )
            )
        strategy, path, problem = profile_config(root, profile)
        if path is not None:
            referenced.add(path)
        missing = [
            key
            for key in ("name", "description", "type", "executor", "container_engine")
            if not profile.get(key)
        ]
        for key in missing:
            issues.append(
                issue(
                    LAYER,
                    f"{pointer}/{key}",
                    "missing_required",
                    f"profile {identifier!r}: {key} is required",
                )
            )
        if missing:
            continue
        try:
            _vocabulary(
                str(profile.get("type")),
                str(profile.get("executor")),
                str(profile.get("container_engine")),
            )
        except LayerError as error:
            issues.append(issue(LAYER, pointer, "vocabulary", str(error)))
            continue
        if problem is not None or path is None:
            issues.append(
                issue(
                    LAYER,
                    f"{pointer}/config",
                    "missing_config",
                    problem or "config missing",
                )
            )
            continue
        current = read_file(root, path) if strategy == AUTHORED else None
        if strategy == AUTHORED:
            assert current is not None
            if current.payload is None:
                issues.append(
                    issue(
                        LAYER,
                        f"{pointer}/config",
                        "missing_config_draft",
                        f"{path} does not exist; create it (any valid Nextflow "
                        "config) or point the profile at another file",
                    )
                )
                continue
            text = current.payload.decode("utf-8", errors="replace")
            if USER_SECTION not in text or PLATFORM_SECTION not in text:
                issues.append(
                    issue(
                        LAYER,
                        "",
                        "missing_sections",
                        "the conventional '// ***** User Pipeline Input Params "
                        "*****' and '// ***** SPLICE Pipeline Input Params *****' "
                        "sections are missing; parameter policy checks cannot "
                        "tell which values are which",
                        Severity.WARNING,
                        path=path,
                    )
                )
            payload = _publishable(text)
            issues.extend(_section_policy_issues(text, path, policies))
        else:
            payload = (root / path).read_bytes()
        issues.extend(
            _safety_issues(
                payload.decode("utf-8", errors="replace"),
                path=path,
                profile_type=str(profile["type"]),
                user_params=user_params,
                authored=strategy == AUTHORED,
            )
        )
        relative = f"configs/{identifier}.config"
        configs[relative] = payload
        rendered.append(
            {
                "id": identifier,
                "name": profile["name"],
                "description": profile["description"],
                "type": profile["type"],
                "engine": profile.get("engine", "nextflow"),
                "executor": profile["executor"],
                "container_engine": profile["container_engine"],
                "config": relative,
                "default": identifier == default,
                "config_strategy": strategy,
            }
            | (
                {"site_parameters": profile["site_parameters"]}
                if profile.get("site_parameters")
                else {}
            )
        )
    for path in list_config_drafts(root):
        if path not in referenced:
            issues.append(
                issue(
                    LAYER,
                    "/profiles",
                    "unreferenced_config",
                    f"{path} is not used by any profile; register it in a profile "
                    "or delete it",
                    Severity.WARNING,
                    path=path,
                )
            )
    identity = validate_bundle_draft(root)
    if identity.metadata is None or not identity.ready:
        issues.append(issue(LAYER, "", "identity_not_ready", "identity is not ready"))
    if (
        any(item.severity is Severity.ERROR for item in issues)
        or identity.metadata is None
    ):
        return LayerValidation(LAYER, tuple(issues))
    document = {
        **data_document_header(EXECUTION_PROFILES_FAMILY),
        "pipeline": identity.metadata.reference(),
        "default_profile": default,
        "profiles": sorted(rendered, key=lambda item: item["id"]),
    }
    report = validate_contract_document(document, EXECUTION_PROFILES_FAMILY)
    issues.extend(
        issue(LAYER, item.json_pointer, "contract", item.message)
        for item in report.issues
    )
    if not report.valid:
        return LayerValidation(LAYER, tuple(issues))
    return LayerValidation(
        LAYER,
        tuple(issues),
        {"execution-profiles.json": canonical_json(document), **configs},
    )


__all__ = [
    "ADOPTED",
    "AUTHORED",
    "CONFIGS_DIR",
    "PLATFORM_SECTION",
    "USER_SECTION",
    "add_generated_profile",
    "add_slurm_default_candidate",
    "config_draft_path",
    "config_file_path",
    "config_scaffold",
    "discover_execution",
    "list_config_drafts",
    "pending_profiles",
    "profile_config",
    "profile_id",
    "profile_ids",
    "read_config_draft",
    "reject_profile",
    "render_generated_config",
    "review_profile",
    "seed_profiles",
    "set_default_profile",
    "update_profile",
    "validate_execution_draft",
    "write_config_draft",
]
