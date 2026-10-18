"""Conservative discovery and classification of container references.

Known nf-core conditional patterns are parsed so Docker and
Singularity/Apptainer sources stay distinct; any other Groovy expression is
recorded as unresolved rather than evaluated. Raw values are preserved.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

from nf_splice.domain.components import ContainerRuntime, ContainerSource, ReferenceKind

#: The ``container`` directive, at the start of a line (not the word in a
#: script or comment).
_CONTAINER = re.compile(r"^[ \t]*container\b[ \t]*(?:=[ \t]*)?", re.M)
_QUOTED = re.compile(r"(?P<quote>['\"])(?P<value>(?:(?!(?P=quote)).)*)(?P=quote)", re.S)
#: The runtime condition of nf-core's container ternary, in its common forms:
#: ``containerEngine == 'singularity'`` and
#: ``containerEngine in ['apptainer','singularity']`` (either order), optionally
#: with ``&& !task.ext.singularity_pull_docker_container``.
_CONDITION = re.compile(
    r"containerEngine\s*(?:==\s*['\"](?P<engine>singularity|apptainer)['\"]"
    r"|in\s*\[(?P<engines>[^\]]*)\])"
    r"(?P<pull>\s*&&\s*!\s*task\.ext\.singularity_pull_docker_container)?"
)
_IMAGE_ENGINES = ("singularity", "apptainer")
_OCI = re.compile(
    r"^(?:[a-z0-9.-]+(?::[0-9]+)?/)?[a-z0-9]+(?:[._-][a-z0-9]+)*"
    r"(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)*(?::[\w][\w.-]{0,127})?(?:@sha256:[0-9a-f]{64})?$"
)
_WITH_NAME = re.compile(
    r"withName\s*:\s*['\"]?(?P<name>[A-Za-z0-9_:*|.-]+)['\"]?\s*\{(?P<body>[^{}]*)\}",
    re.S,
)
_CONFIG_CONTAINER = re.compile(
    r"\bcontainer\s*=\s*(?P<quote>['\"])(?P<value>[^'\"]+)(?P=quote)"
)


def classify_reference(raw: str) -> ReferenceKind:
    """Classify a reference without treating any URL suffix as proof."""
    value = raw.strip()
    if "${" in value or "{" in value or "?" in value:
        return ReferenceKind.UNRESOLVED_EXPRESSION
    lowered = value.lower()
    if lowered.startswith("docker://"):
        return ReferenceKind.DOCKER_URI
    if lowered.startswith("oras://"):
        return ReferenceKind.ORAS
    if lowered.startswith("https://"):
        return ReferenceKind.HTTPS_IMAGE
    if lowered.startswith("http://"):
        return ReferenceKind.INSECURE_HTTP
    if lowered.endswith((".sif", ".img")) and (
        value.startswith(("/", "./")) or "/" not in value
    ):
        return ReferenceKind.LOCAL_IMAGE
    if _OCI.fullmatch(value) and ("/" in value or ":" in value):
        return ReferenceKind.OCI_REGISTRY
    return ReferenceKind.UNSUPPORTED


_DIRECTIVE_START = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*(?:\s|['\"(]|$)")
_CONTINUES = ("?", ":", "(", ",", "+", "{", "\\", "&&", "||")


def _expression(text: str, start: int) -> str:
    """The container expression: up to a section, a blank line or a directive.

    A following line that starts a new directive (``publishDir ...``,
    ``label ...``) ends the expression unless the expression visibly
    continues, as in nf-core's multi-line ternary form.
    """
    tail = text[start : start + 1500]
    boundary = re.search(r"\n\s*(?:input|output|when|script|stub|exec|shell)\s*:", tail)
    tail = tail[: boundary.start()] if boundary else tail.split("\n\n", 1)[0]
    lines = tail.split("\n")
    kept = [lines[0]]
    for line in lines[1:]:
        stripped = line.strip()
        previous = kept[-1].rstrip()
        if (
            _DIRECTIVE_START.match(stripped)
            and not stripped.startswith(("?", ":"))
            and not previous.endswith(_CONTINUES)
        ):
            break
        kept.append(line)
    return "\n".join(kept)


def _condition_engines(condition: re.Match[str] | None) -> tuple[str, ...]:
    """Singularity-family engines a ternary condition selects, in order."""
    if condition is None:
        return ()
    if condition.group("engine"):
        return (condition.group("engine"),)
    listed = re.findall(r"""['"]([a-z]+)['"]""", condition.group("engines") or "")
    return tuple(item for item in _IMAGE_ENGINES if item in listed)


def _line(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def container_sources(main_nf: Path, relative: str) -> tuple[ContainerSource, ...]:
    """Extract every container reference of one module with its condition."""
    if main_nf.is_symlink() or not main_nf.is_file():
        return ()
    text = main_nf.read_text(encoding="utf-8", errors="replace")
    return sources_in_text(text, relative)


def sources_in_text(
    text: str, relative: str, start: int = 0, end: int | None = None
) -> tuple[ContainerSource, ...]:
    """Container references in ``text[start:end]``, located in the whole file.

    Used for a module's ``main.nf`` and for one process defined inline in a
    workflow file.
    """
    found: list[ContainerSource] = []
    for match in _CONTAINER.finditer(text, start, len(text) if end is None else end):
        expression = _expression(text, match.end())
        location = f"{relative}:{_line(text, match.start())}"
        values = [item.group("value") for item in _QUOTED.finditer(expression)]
        values = [item for item in values if item and not item.isspace()]
        condition = _CONDITION.search(expression)
        engines = _condition_engines(condition)
        if condition and engines and "?" in expression and ":" in expression:
            ternary = expression[condition.end() :]
            branches = [
                item
                for item in re.findall(r"""['"]([^'"\s]+)['"]""", ternary)
                if item not in _IMAGE_ENGINES
            ]
            if len(branches) == 2:
                # The first branch is what Singularity/Apptainer use; the
                # second is what every other engine (Docker, Podman) pulls.
                pairs = [
                    (ContainerRuntime(engine), branches[0]) for engine in engines
                ] + [(ContainerRuntime.DOCKER, branches[1])]
                for runtime, raw in pairs:
                    found.append(
                        ContainerSource(
                            raw=raw,
                            runtime=runtime,
                            kind=classify_reference(raw),
                            location=location,
                            confidence=0.95,
                        )
                    )
                continue
        quoted_values = [
            item.strip()
            for item in values
            if not any(character.isspace() for character in item.strip())
        ]
        if "?" in expression or ("${" in expression and not quoted_values):
            found.append(
                ContainerSource(
                    raw=" ".join(expression.split())[:300] or "container",
                    runtime=ContainerRuntime.ANY,
                    kind=ReferenceKind.UNRESOLVED_EXPRESSION,
                    location=location,
                    confidence=0.3,
                )
            )
            continue
        for raw in quoted_values:
            kind = classify_reference(raw)
            if (
                kind in {ReferenceKind.UNSUPPORTED}
                and "/" not in raw
                and ":" not in raw
            ):
                continue
            runtime = (
                ContainerRuntime.SINGULARITY
                if kind
                in {
                    ReferenceKind.HTTPS_IMAGE,
                    ReferenceKind.ORAS,
                    ReferenceKind.LOCAL_IMAGE,
                }
                else ContainerRuntime.ANY
            )
            found.append(
                ContainerSource(
                    raw=raw,
                    runtime=runtime,
                    kind=kind,
                    location=location,
                    confidence=0.9,
                )
            )
    return tuple(found)


_INCLUDE = re.compile(r"""^\s*includeConfig\s+(['"])(?P<path>[^'"$]+)\1\s*$""", re.M)
_PROFILES = re.compile(r"\bprofiles\s*\{")


def _without_profiles(text: str) -> str:
    """The text outside ``profiles { ... }``: what applies to every run."""
    match = _PROFILES.search(text)
    if match is None:
        return text
    depth = 0
    for index in range(match.end() - 1, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[: match.start()] + _without_profiles(text[index + 1 :])
    return text[: match.start()]


def default_config_files(root: Path) -> list[Path]:
    """Configs that apply to a run without a profile.

    ``nextflow.config`` and every file it includes with a literal
    ``includeConfig`` outside ``profiles { }``, recursively. Files only a
    profile includes, conditional includes and files nothing includes do not
    apply to the default run.
    """
    found: list[Path] = []
    pending = [root / "nextflow.config"]
    while pending:
        path = pending.pop(0)
        if path in found or path.is_symlink() or not path.is_file():
            continue
        try:
            resolved = path.resolve()
            resolved.relative_to(root.resolve())
        except (OSError, ValueError):
            continue
        found.append(path)
        text = _without_profiles(path.read_text(encoding="utf-8", errors="replace"))
        for match in _INCLUDE.finditer(text):
            pending.append(path.parent / match.group("path"))
    return found


def config_overrides(root: Path) -> dict[str, list[ContainerSource]]:
    """``withName`` container overrides that apply to a run without a profile."""
    overrides: dict[str, list[ContainerSource]] = {}
    for path in default_config_files(root):
        if path.is_symlink() or not path.is_file():
            continue
        text = _without_profiles(path.read_text(encoding="utf-8", errors="replace"))
        relative = PurePosixPath(path.relative_to(root).as_posix())
        for block in _WITH_NAME.finditer(text):
            for item in _CONFIG_CONTAINER.finditer(block.group("body")):
                raw = item.group("value")
                overrides.setdefault(block.group("name"), []).append(
                    ContainerSource(
                        raw=raw,
                        runtime=ContainerRuntime.ANY,
                        kind=classify_reference(raw),
                        location=f"{relative}:{_line(text, block.start())}",
                        confidence=0.8,
                    )
                )
    return overrides


def nextflow_cache_filename(image: str, *, registry: str | None = None) -> str:
    """Return the file name Nextflow's Singularity/Apptainer cache uses.

    Mirrors the published Nextflow ``SingularityCache.simpleName`` rule:
    strip any URI scheme, map ``:`` and ``/`` to ``-`` and append ``.img``
    (or keep ``.sif``). A registry-less Docker reference is first prefixed
    with the configured registry, as Nextflow does when
    ``singularity.registry``/``apptainer.registry`` is set. The rule is
    checked against a real Nextflow only by the opt-in ``nextflow``
    integration test (``tests/test_containers.py``).
    """
    value = image.strip()
    if "://" not in value and registry and not re.match(r"^[^/]+[.:][^/]*/", value):
        value = f"{registry.rstrip('/')}/{value}"
    position = value.find("://")
    name = value[position + 3 :] if position != -1 else value
    extension = ".img"
    if ".sif:" in name:
        extension = ".sif"
        name = name.replace(".sif:", "-")
    elif name.endswith(".sif"):
        extension = ".sif"
        name = name[:-4]
    return name.replace(":", "-").replace("/", "-") + extension
