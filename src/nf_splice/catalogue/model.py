"""Typed records of the SPLICE modality vocabulary and its provenance.

Three sets are kept apart, as the platform does:

- the **scientific vocabulary**: entities of the types in :class:`EntityType`
  and the directed ``modality_tree`` edges between them (a DAG: an entity can
  have several parents);
- the **platform registrations**: named leaf entries (``modality_name``, for
  example ``polya_rnaseq``) linking a vocabulary entity to a source database
  record (``modality_id``), with the deployment flag ``current``;
- a **pipeline's capabilities**, chosen by people from the first two and
  stored in its bundle (see :mod:`nf_splice.catalogue.resolver`).

``current`` describes what one deployment ingests today. It never limits what
the vocabulary contains or what a pipeline may declare.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EntityType(str, Enum):
    """The exact ``entity_type`` values of the SPLICE vocabulary."""

    ROOT = "root"
    MODALITY = "MODALITY"
    MODALITY_SUBTYPE = "MODALITY_SUBTYPE"
    ASSAY_TYPE = "ASSAY_TYPE"
    ASSAY_METHOD = "ASSAY_METHOD"


#: Entity types a pipeline capability may name.
ASSAY_TYPES = frozenset({EntityType.ASSAY_TYPE, EntityType.ASSAY_METHOD})
#: The navigation whose edges define the modality hierarchy.
MODALITY_TREE = "modality_tree"


class CatalogueError(ValueError):
    """A vocabulary, selection or source problem, with a stable ``code``.

    Codes: ``invalid_snapshot``, ``broken_edge``, ``cycle``, ``unreachable``,
    ``unknown_code``, ``unknown_entity``, ``not_an_assay``, ``duplicate``,
    ``ambiguous``, ``mismatch``, ``accession_not_accepted``, ``unavailable``,
    ``untrusted_response``, ``conflict``.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code

    def to_json(self) -> dict[str, str]:
        return {"code": self.code, "message": str(self)}


@dataclass(frozen=True, slots=True)
class Entity:
    entity_id: int
    label: str
    entity_type: EntityType
    description: str | None
    aliases: tuple[str, ...]
    concept_status: str
    implementation_status: str

    def reference(self, *, with_type: bool = False) -> dict[str, Any]:
        found: dict[str, Any] = {"entity_id": self.entity_id}
        if with_type:
            found["entity_type"] = self.entity_type.value
        found["label"] = self.label
        return found


@dataclass(frozen=True, slots=True)
class Relationship:
    id: int
    child_entity_id: int
    ancestor_entity_id: int
    navigation: str


@dataclass(frozen=True, slots=True)
class Registration:
    """A platform registration (``Modalities`` row) of a vocabulary entity."""

    modality_id: int
    code: str
    entity_id: int | None
    current: bool
    schema_version_splice: str | None
    schema_version_ext: str | None
    #: Present only when an authoritative platform source supplied it.
    accession_id: str | None = None


@dataclass(frozen=True, slots=True)
class Provenance:
    """Where a vocabulary came from; independent of every other version."""

    snapshot_id: str
    name: str
    origin: str
    digest: str
    source: str = "packaged_snapshot"
    source_files: Mapping[str, str] = field(default_factory=dict)
    note: str | None = None

    def reference(self) -> dict[str, str]:
        """What a bundle records: enough to identify and verify the snapshot."""
        return {"name": self.name, "snapshot": self.snapshot_id, "digest": self.digest}

    def to_json(self) -> dict[str, Any]:
        found: dict[str, Any] = {
            "snapshot": self.snapshot_id,
            "name": self.name,
            "origin": self.origin,
            "digest": self.digest,
            "source": self.source,
            "source_files": dict(self.source_files),
        }
        if self.note:
            found["note"] = self.note
        return found


@dataclass(frozen=True, slots=True)
class Snapshot:
    """One complete vocabulary with its provenance."""

    provenance: Provenance
    entities: tuple[Entity, ...]
    relationships: tuple[Relationship, ...]
    registrations: tuple[Registration, ...]


def content_document(snapshot: Snapshot) -> dict[str, Any]:
    """The canonical content whose SHA-256 is the snapshot digest."""
    return {
        "entities": [
            {
                "entity_id": item.entity_id,
                "label": item.label,
                "entity_type": item.entity_type.value,
                "description": item.description,
                "aliases": list(item.aliases),
                "concept_status": item.concept_status,
                "implementation_status": item.implementation_status,
            }
            for item in sorted(snapshot.entities, key=lambda value: value.entity_id)
        ],
        "relationships": [
            {
                "id": item.id,
                "child_entity_id": item.child_entity_id,
                "ancestor_entity_id": item.ancestor_entity_id,
                "navigation": item.navigation,
            }
            for item in sorted(snapshot.relationships, key=lambda value: value.id)
        ],
        "registrations": [
            {
                "modality_id": item.modality_id,
                "modality_name": item.code,
                "entity_id": item.entity_id,
                "current": item.current,
                "schema_version_splice": item.schema_version_splice,
                "schema_version_ext": item.schema_version_ext,
            }
            for item in sorted(
                snapshot.registrations, key=lambda value: value.modality_id
            )
        ],
    }
