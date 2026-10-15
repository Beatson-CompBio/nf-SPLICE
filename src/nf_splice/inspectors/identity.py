"""Read-only discovery of pipeline identity values and conflicts."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml  # type: ignore[import-untyped]

from nf_splice.domain import Evidence, EvidenceProvenance

# Upstream Nextflow configuration syntax: Nextflow itself names its pipeline
# metadata scope with the literal token in these patterns. The token is parsed
# only as external input evidence and is never a SPLICE concept or output name
# (see ADR-0025 and docs/GLOSSARY.md).
_NEXTFLOW_METADATA_BLOCK = re.compile(r"\bmanifest\s*\{(?P<body>.*?)\}", re.DOTALL)
_NEXTFLOW_KEYS = (
    r"name|version|homePage|repository_url|release_url|description|author|"
    r"nextflowVersion|doi|license|docsUrl"
)
_ASSIGNMENT = re.compile(
    rf"(?m)^\s*(?P<key>{_NEXTFLOW_KEYS})\s*=\s*"
    r"(?P<quote>['\"])(?P<value>.+?)(?P=quote)"
)
_NEXTFLOW_METADATA_DOTTED = re.compile(
    rf"(?m)^\s*manifest\.(?P<key>{_NEXTFLOW_KEYS})"
    r"\s*=\s*(?P<quote>['\"])(?P<value>.+?)(?P=quote)"
)
_CONTRIBUTOR = re.compile(r"\[\s*(?P<body>name\s*:[^\[\]]*(?:\[[^\]]*\][^\[\]]*)*)\]")
_CONTRIBUTOR_FIELD = re.compile(
    r"(?P<key>name|affiliation|orcid)\s*:\s*(?P<quote>['\"])(?P<value>.*?)(?P=quote)"
)
_FIELD_NAMES = {
    "homePage": "repository_url",
    "repository_url": "repository_url",
    "release_url": "release_url",
    "name": "name",
    "version": "version",
    "description": "description",
    "author": "authors",
    "nextflowVersion": "engine_version_min",
    "doi": "citation",
    "license": "licence",
    "docsUrl": "documentation_url",
}


@dataclass(frozen=True, slots=True)
class IdentityValue:
    """One detected identity value and its supporting evidence.

    ``value`` is a string for scalar fields and JSON-compatible structured
    data for ``authors`` (list of mappings) and ``citation`` (mapping).
    """

    field: str
    value: Any
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
    *, root: Path, source: str, location: str, field: str, value: Any
) -> Evidence:
    revision = _git_value(root, "rev-parse", "HEAD")
    rendered = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
    digest = hashlib.sha256(
        f"{source}\0{location}\0{field}\0{rendered}".encode()
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


def _nextflow_contributors(content: str) -> list[dict[str, str]]:
    match = re.search(r"\bcontributors\s*=\s*\[", content)
    if match is None:
        return []
    contributors = []
    for item in _CONTRIBUTOR.finditer(content, match.end()):
        fields = {
            found.group("key"): found.group("value").strip()
            for found in _CONTRIBUTOR_FIELD.finditer(item.group("body"))
            if found.group("value").strip()
        }
        if "name" in fields:
            contributors.append(
                {"name": fields["name"], "type": "person"}
                | {
                    key: fields[key]
                    for key in ("affiliation", "orcid")
                    if key in fields
                }
            )
    return contributors


def _read_text(path: Path) -> str | None:
    if path.is_symlink() or not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None


def _citation_values(root: Path) -> list[IdentityValue]:
    """Citation File Format metadata is evidence, never authoring truth."""
    text = _read_text(root / "CITATION.cff")
    if text is None:
        return []
    try:
        loaded: object = yaml.safe_load(text)
    except yaml.YAMLError:
        return []
    if not isinstance(loaded, dict):
        return []
    found: list[tuple[str, Any]] = []
    if isinstance(loaded.get("title"), str):
        found.append(("title", loaded["title"].strip()))
    if isinstance(loaded.get("abstract"), str):
        found.append(("description", " ".join(loaded["abstract"].split())))
    if isinstance(loaded.get("version"), str | int | float):
        found.append(("version", str(loaded["version"])))
    if isinstance(loaded.get("license"), str):
        found.append(("licence", loaded["license"]))
    if isinstance(loaded.get("repository-code"), str):
        found.append(("repository_url", loaded["repository-code"].removesuffix(".git")))
    if isinstance(loaded.get("doi"), str):
        found.append(("citation", {"doi": loaded["doi"], "cff_path": "CITATION.cff"}))
    authors = []
    for item in loaded.get("authors") or []:
        if not isinstance(item, dict):
            continue
        if isinstance(item.get("name"), str):
            author: dict[str, str] = {"name": item["name"], "type": "organization"}
        else:
            parts = [item.get("given-names"), item.get("family-names")]
            name = " ".join(str(part) for part in parts if part)
            if not name:
                continue
            author = {"name": name, "type": "person"}
        if isinstance(item.get("affiliation"), str):
            author["affiliation"] = item["affiliation"]
        if isinstance(item.get("orcid"), str):
            author["orcid"] = item["orcid"]
        authors.append(author)
    if authors:
        found.append(("authors", authors))
    return [
        IdentityValue(
            field,
            value,
            _evidence(
                root=root,
                source="CITATION.cff",
                location=f"CITATION.cff:{field}",
                field=field,
                value=value,
            ),
        )
        for field, value in found
    ]


def _ro_crate_values(root: Path) -> list[IdentityValue]:
    text = _read_text(root / "ro-crate-metadata.json")
    if text is None:
        return []
    try:
        loaded: object = json.loads(text)
    except json.JSONDecodeError:
        return []
    graph = loaded.get("@graph") if isinstance(loaded, dict) else None
    if not isinstance(graph, list):
        return []
    by_id = {item.get("@id"): item for item in graph if isinstance(item, dict)}
    dataset = by_id.get("./")
    if not isinstance(dataset, dict):
        return []
    found: list[tuple[str, Any]] = []
    for source, field in (
        ("name", "name"),
        ("description", "description"),
        ("version", "version"),
    ):
        if isinstance(dataset.get(source), str) and dataset[source].strip():
            found.append((field, dataset[source].strip()))
    licence = dataset.get("license")
    if isinstance(licence, dict):
        licence = licence.get("@id")
    if isinstance(licence, str) and licence:
        found.append(("licence", licence))
    creators = dataset.get("creator") or dataset.get("author")
    creators = (
        creators if isinstance(creators, list) else [creators] if creators else []
    )
    authors = []
    for creator in creators:
        entity = by_id.get(creator.get("@id")) if isinstance(creator, dict) else None
        entity = entity if isinstance(entity, dict) else creator
        if isinstance(entity, dict) and isinstance(entity.get("name"), str):
            kind = "organization" if entity.get("@type") == "Organization" else "person"
            author = {"name": entity["name"], "type": kind}
            identifier = str(entity.get("@id", ""))
            if identifier.startswith("https://orcid.org/"):
                author["orcid"] = identifier
            authors.append(author)
    if authors:
        found.append(("authors", authors))
    return [
        IdentityValue(
            field,
            value,
            _evidence(
                root=root,
                source="ro-crate-metadata.json",
                location=f"ro-crate-metadata.json#./{field}",
                field=field,
                value=value,
            ),
        )
        for field, value in found
    ]


def _readme_values(root: Path) -> list[IdentityValue]:
    text = _read_text(root / "README.md")
    if text is None:
        return []
    heading = re.search(r"(?m)^#\s+(?P<title>[^\n#!\[]+?)\s*$", text)
    if heading is None:
        return []
    title = heading.group("title").strip()
    line = text.count("\n", 0, heading.start()) + 1
    return [
        IdentityValue(
            "title",
            title,
            _evidence(
                root=root,
                source="README.md",
                location=f"README.md:{line}",
                field="title",
                value=title,
            ),
        )
    ]


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
        matches = list(_NEXTFLOW_METADATA_DOTTED.finditer(content))
        for block in _NEXTFLOW_METADATA_BLOCK.finditer(content):
            matches.extend(
                _ASSIGNMENT.finditer(content, block.start("body"), block.end("body"))
            )
        for match in sorted(matches, key=lambda item: item.start()):
            field = _FIELD_NAMES[match.group("key")]
            raw = match.group("value").strip()
            value: Any = raw
            if field == "authors":
                value = [
                    {"name": item.strip()}
                    for item in re.split(r",|\band\b", raw)
                    if item.strip()
                ]
            elif field == "citation":
                value = {"doi": raw.removeprefix("https://doi.org/")}
            elif field == "engine_version_min":
                value = re.sub(r"^[!>=\s]+", "", raw)
            line = content.count("\n", 0, match.start()) + 1
            values.append(
                IdentityValue(
                    field,
                    value,
                    _evidence(
                        root=root,
                        source="nextflow.config",
                        location=f"nextflow.config:{line}",
                        field=field,
                        value=value,
                    ),
                )
            )
        contributors = _nextflow_contributors(content)
        if contributors:
            values.append(
                IdentityValue(
                    "authors",
                    contributors,
                    _evidence(
                        root=root,
                        source="nextflow.config",
                        location="nextflow.config:contributors",
                        field="authors",
                        value=contributors,
                    ),
                )
            )
    values.extend(_citation_values(root))
    values.extend(_ro_crate_values(root))
    values.extend(_readme_values(root))

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
