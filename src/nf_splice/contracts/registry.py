"""Packaged, offline registry of the five workflow-bundle contract families."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from importlib import resources
from typing import Any

from nf_splice._version import __version__

NAMESPACE = "https://schemas.splice-data.io/workflow-bundle/"
BUNDLE_FAMILY = f"{NAMESPACE}bundle"
INPUTS_FAMILY = f"{NAMESPACE}inputs"
OUTPUTS_FAMILY = f"{NAMESPACE}outputs"
COMPONENTS_FAMILY = f"{NAMESPACE}components"
EXECUTION_PROFILES_FAMILY = f"{NAMESPACE}execution-profiles"
FAMILY_IDS = (
    BUNDLE_FAMILY,
    INPUTS_FAMILY,
    OUTPUTS_FAMILY,
    COMPONENTS_FAMILY,
    EXECUTION_PROFILES_FAMILY,
)
TOOL_NAME = "nf-splice"


class ContractRegistryError(ValueError):
    """Raised for an unknown family, revision or tool release."""


@dataclass(frozen=True, slots=True)
class ContractFamily:
    """One public workflow-bundle contract family and its known revisions."""

    id: str
    key: str
    title: str
    path: str
    kind: str
    revisions: tuple[str, ...]

    @property
    def is_json_schema_document(self) -> bool:
        """Whether the final artefact is itself a JSON Schema document."""
        return self.kind == "json-schema-document"


@dataclass(frozen=True, slots=True)
class ToolRelease:
    """Explicit mapping of one nf-splice release to contract revisions."""

    tool_version: str
    contracts: tuple[tuple[str, str], ...]
    companion_formats: tuple[tuple[str, str], ...]


def _data_text(*parts: str) -> str:
    return (
        resources.files("nf_splice.contracts")
        .joinpath("data", *parts)
        .read_text(encoding="utf-8")
    )


@cache
def _registry_document() -> dict[str, Any]:
    loaded: object = json.loads(_data_text("registry.json"))
    if not isinstance(loaded, dict):
        raise ContractRegistryError("packaged contract registry is not an object")
    return loaded


@cache
def families() -> tuple[ContractFamily, ...]:
    """Return the five families in their documented stable order."""
    raw = _registry_document()["families"]
    result = []
    for family_id in FAMILY_IDS:
        item = raw[family_id]
        result.append(
            ContractFamily(
                id=family_id,
                key=str(item["key"]),
                title=str(item["title"]),
                path=str(item["path"]),
                kind=str(item["kind"]),
                revisions=tuple(sorted(item["revisions"])),
            )
        )
    if len(raw) != len(FAMILY_IDS):
        raise ContractRegistryError("packaged registry must list exactly five families")
    return tuple(result)


def family(identifier: str) -> ContractFamily:
    """Resolve a family by URI, short key or final artefact path."""
    for item in families():
        if identifier in {item.id, item.key, item.path}:
            return item
    raise ContractRegistryError(
        f"unknown workflow-bundle contract family {identifier!r}"
    )


@cache
def releases() -> tuple[ToolRelease, ...]:
    """Return every registered nf-splice release mapping, oldest first."""
    return tuple(
        ToolRelease(
            tool_version=str(item["tool_version"]),
            contracts=tuple(sorted(item.get("contracts", {}).items())),
            companion_formats=tuple(sorted(item.get("companion_formats", {}).items())),
        )
        for item in _registry_document()["releases"]
    )


def release(tool_version: str = __version__) -> ToolRelease:
    """Return the explicit contract mapping for one tool release."""
    for item in releases():
        if item.tool_version == tool_version:
            return item
    raise ContractRegistryError(
        f"nf-splice {tool_version} has no registered contract mapping"
    )


def current_revision(family_id: str) -> str:
    """Return the revision emitted by the running tool for one family."""
    mapping = dict(release().contracts)
    resolved = family(family_id).id
    if resolved not in mapping:
        raise ContractRegistryError(
            f"nf-splice {__version__} does not emit family {resolved}"
        )
    return mapping[resolved]


@cache
def meta_schema(family_id: str, revision: str | None = None) -> dict[str, Any]:
    """Load the packaged formal definition of one family revision offline."""
    item = family(family_id)
    selected = revision or current_revision(item.id)
    if selected not in item.revisions:
        raise ContractRegistryError(
            f"{item.id} has no packaged revision {selected!r}; "
            f"known revisions: {', '.join(item.revisions)}"
        )
    relative = _registry_document()["families"][item.id]["revisions"][selected]
    loaded: object = json.loads(_data_text(*str(relative).split("/")))
    if not isinstance(loaded, dict):
        raise ContractRegistryError(f"packaged schema {relative} is not an object")
    return loaded


def generated_by() -> dict[str, str]:
    """Return the generator identity embedded in every emitted contract."""
    return {"name": TOOL_NAME, "version": __version__}


def contract_extension(family_id: str) -> dict[str, object]:
    """Return the ``x-splice-contract`` fragment for JSON Schema documents."""
    item = family(family_id)
    return {
        "id": item.id,
        "version": current_revision(item.id),
        "generated_by": generated_by(),
    }


def data_document_header(family_id: str) -> dict[str, object]:
    """Return ``schema_id``/``schema_version``/``generated_by`` for data documents."""
    item = family(family_id)
    return {
        "schema_id": item.id,
        "schema_version": current_revision(item.id),
        "generated_by": generated_by(),
    }
