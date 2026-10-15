"""Read-only discovery of Nextflow execution profiles and config evidence."""

from __future__ import annotations

import re
from pathlib import Path

from nf_splice.domain.authoring import Evidence, EvidenceProvenance
from nf_splice.domain.execution import ExecutionProfileCandidate


class ProfileDiscoveryError(ValueError):
    """Raised when execution-profile evidence cannot be read safely."""


_PROFILE_BLOCK = re.compile(r"\bprofiles\s*\{")
_INCLUDE = re.compile(r"\bincludeConfig\s*\(?\s*['\"]([^'\"]+)['\"]")
_EXECUTOR = re.compile(r"\bexecutor\s*=\s*['\"]([A-Za-z0-9_-]+)['\"]")
_ENGINE_DIRECT = re.compile(
    r"\b(docker|singularity|apptainer|podman|conda|mamba|shifter|charliecloud)"
    r"\.enabled\s*=\s*true\b"
)
_ENGINE_BLOCK = re.compile(
    r"\b(docker|singularity|apptainer|podman|conda|mamba|shifter|charliecloud)"
    r"\s*\{[^{}]*\benabled\s*=\s*true\b",
    re.DOTALL,
)
_PROFILE_ID = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(?:password|passwd|secret|token|credential|private[_-]?key|"
    r"access[_-]?key)\b\s*=\s*(?!null\b|System\.getenv\b)([^\n]+)"
)
_PERSONAL_PATH = re.compile(r"(?:~[/\\]|/(?:Users|home)/[^/'\"\s]+)")
_ACCOUNT_LITERAL = re.compile(
    r"(?i)(?:--account(?:=|\s+)|\b(?:account|project|budget)\s*=\s*)"
    r"['\"]?[A-Za-z0-9][A-Za-z0-9_.-]+"
)
_DEMO_TEST = re.compile(r"(?i)(?:test[_-]?data|testdata|demo(?:nstration)?)")
_PARAM_ASSIGNMENT = re.compile(r"\bparams\.([A-Za-z_][A-Za-z0-9_]*)\s*=")


def strip_comments(text: str) -> str:
    text = re.sub(
        r"/\*.*?\*/",
        lambda match: "\n" * match.group(0).count("\n"),
        text,
        flags=re.DOTALL,
    )
    return re.sub(r"//.*", "", text)


def _matching_brace(text: str, opening: int) -> int:
    depth = 0
    quote: str | None = None
    escaped = False
    for index in range(opening, len(text)):
        character = text[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in {"'", '"'}:
            quote = character
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return index
    raise ProfileDiscoveryError("nextflow.config contains an unclosed profiles block")


def _profile_bodies(text: str) -> tuple[tuple[str, str], ...]:
    cleaned = strip_comments(text)
    match = _PROFILE_BLOCK.search(cleaned)
    if match is None:
        return ()
    opening = cleaned.find("{", match.start())
    closing = _matching_brace(cleaned, opening)
    body = cleaned[opening + 1 : closing]
    profiles: list[tuple[str, str]] = []
    index = 0
    while index < len(body):
        candidate = re.search(r"\b([A-Za-z_][A-Za-z0-9_-]*)\s*\{", body[index:])
        if candidate is None:
            break
        name = candidate.group(1)
        profile_opening = index + candidate.end() - 1
        profile_closing = _matching_brace(body, profile_opening)
        profiles.append((name, body[profile_opening + 1 : profile_closing]))
        index = profile_closing + 1
    return tuple(profiles)


def _scan_environment(text: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    executors = tuple(sorted(set(_EXECUTOR.findall(text))))
    engines = set(_ENGINE_DIRECT.findall(text)) | set(_ENGINE_BLOCK.findall(text))
    engines.discard("mamba")
    if "mamba" in _ENGINE_DIRECT.findall(text):
        engines.add("conda")
    return executors, tuple(sorted(engines))


def safe_relative(root: Path, path: str) -> str | None:
    if "$" in path or "://" in path:
        return None
    requested = root / path
    if requested.is_symlink():
        return None
    candidate = requested.resolve()
    try:
        relative = candidate.relative_to(root).as_posix()
    except ValueError:
        return None
    return relative if candidate.is_file() else None


def discover_profiles(
    root: Path,
) -> tuple[tuple[ExecutionProfileCandidate, tuple[Evidence, ...]], ...]:
    config = root / "nextflow.config"
    if not config.is_file():
        raise ProfileDiscoveryError("nextflow.config is required for profile discovery")
    discovered: dict[str, tuple[ExecutionProfileCandidate, tuple[Evidence, ...]]] = {}
    for name, body in _profile_bodies(config.read_text(encoding="utf-8")):
        if not _PROFILE_ID.fullmatch(name):
            continue
        sources = tuple(
            sorted(
                {
                    relative
                    for included in _INCLUDE.findall(body)
                    if (relative := safe_relative(root, included)) is not None
                }
            )
        )
        combined = (
            body
            + "\n"
            + "\n".join(
                (root / source).read_text(encoding="utf-8", errors="replace")
                for source in sources
            )
        )
        executors, engines = _scan_environment(combined)
        unresolved = ["review", "config_source"]
        if len(executors) != 1:
            unresolved.append("executor")
        if len(engines) != 1:
            unresolved.append("container_engine")
        locations = ("nextflow.config", *sources)
        candidate = ExecutionProfileCandidate(
            id=f"profile:{name}",
            name=name.replace("_", " ").replace("-", " ").title(),
            source_profile=name,
            config_sources=sources,
            executors=executors,
            container_engines=engines,
            unresolved_fields=tuple(unresolved),
        )
        evidence = tuple(
            Evidence(
                id=f"{candidate.id}:{index}",
                provenance=EvidenceProvenance(
                    source="execution_profile", location=location
                ),
                observed_value=(
                    candidate.model_dump(mode="json") if index == 1 else location
                ),
                confidence=1.0,
            )
            for index, location in enumerate(locations, start=1)
        )
        discovered[candidate.id] = (candidate, evidence)
    return tuple(discovered[key] for key in sorted(discovered))
