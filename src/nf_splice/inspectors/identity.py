"""Read-only discovery of pipeline identity values and conflicts."""

from __future__ import annotations

import hashlib
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from nf_splice.domain import Evidence, EvidenceProvenance

_MANIFEST_BLOCK = re.compile(r"\bmanifest\s*\{(?P<body>.*?)\}", re.DOTALL)
_ASSIGNMENT = re.compile(
    r"(?m)^\s*(?P<key>name|version|homePage|repository_url|release_url)\s*=\s*"
    r"(?P<quote>['\"])(?P<value>.+?)(?P=quote)"
)
_DOTTED_ASSIGNMENT = re.compile(
    r"(?m)^\s*manifest\.(?P<key>name|version|homePage|repository_url|release_url)"
    r"\s*=\s*(?P<quote>['\"])(?P<value>.+?)(?P=quote)"
)


@dataclass(frozen=True, slots=True)
class IdentityValue:
    """One detected identity value and its supporting evidence."""

    field: str
    value: str
    evidence: Evidence


@dataclass(frozen=True, slots=True)
class IdentityInspection:
    """Detected values grouped for explicit review by the application service."""

    values: tuple[IdentityValue, ...]


def _git_value(root: Path, *arguments: str) -> str | None:
    try:
        result = subprocess.run(
            ("git", "-C", str(root), *arguments),
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = result.stdout.strip()
    return value if result.returncode == 0 and value else None


def _normalise_remote(remote: str) -> str:
    if remote.startswith("git@") and ":" in remote:
        host_path = remote.removeprefix("git@").replace(":", "/", 1)
        remote = f"https://{host_path}"
    return remote.removesuffix(".git")


def _repository_name(remote: str) -> str | None:
    path = urlparse(_normalise_remote(remote)).path.rstrip("/")
    return path.rsplit("/", 1)[-1] if path else None


def _evidence(
    *, root: Path, source: str, location: str, field: str, value: str
) -> Evidence:
    revision = _git_value(root, "rev-parse", "HEAD")
    digest = hashlib.sha256(
        f"{source}\0{location}\0{field}\0{value}".encode()
    ).hexdigest()[:16]
    return Evidence(
        id=f"identity-evidence:{digest}",
        provenance=EvidenceProvenance(
            source=source,
            location=location,
            repository_revision=revision,
        ),
        observed_value={"field": field, "value": value},
        confidence=1.0,
    )


def inspect_pipeline_identity(repository_root: str | Path) -> IdentityInspection:
    """Collect configuration and Git identity evidence without selecting it."""
    root = Path(repository_root).resolve()
    values: list[IdentityValue] = []
    config = root / "nextflow.config"
    if config.is_file() and not config.is_symlink():
        try:
            content = config.read_text(encoding="utf-8", errors="replace")
        except OSError:
            content = ""
        matches = list(_DOTTED_ASSIGNMENT.finditer(content))
        for block in _MANIFEST_BLOCK.finditer(content):
            matches.extend(_ASSIGNMENT.finditer(block.group("body")))
        field_names = {
            "homePage": "repository_url",
            "repository_url": "repository_url",
            "release_url": "release_url",
            "name": "name",
            "version": "version",
        }
        for match in sorted(matches, key=lambda item: item.start()):
            field = field_names[match.group("key")]
            value = match.group("value").strip()
            line = content.count("\n", 0, match.start()) + 1
            evidence = _evidence(
                root=root,
                source="nextflow.config",
                location=f"nextflow.config:{line}",
                field=field,
                value=value,
            )
            values.append(IdentityValue(field, value, evidence))

    remote = _git_value(root, "remote", "get-url", "origin")
    if remote:
        repository_url = _normalise_remote(remote)
        evidence = _evidence(
            root=root,
            source="git_remote",
            location=".git/config",
            field="repository_url",
            value=repository_url,
        )
        values.append(IdentityValue("repository_url", repository_url, evidence))
        name = _repository_name(repository_url)
        if name:
            evidence = _evidence(
                root=root,
                source="git_remote",
                location=".git/config",
                field="name",
                value=name,
            )
            values.append(IdentityValue("name", name, evidence))

    tag = _git_value(root, "describe", "--tags", "--exact-match")
    if tag:
        version = tag[1:] if re.fullmatch(r"v\d.*", tag) else tag
        evidence = _evidence(
            root=root,
            source="git_tag",
            location=".git/refs/tags",
            field="version",
            value=version,
        )
        values.append(IdentityValue("version", version, evidence))
    return IdentityInspection(tuple(values))
