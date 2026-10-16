"""The one deterministic resolver over a SPLICE modality vocabulary.

Every interface (CLI, wizard, agents) and the bundle compiler resolve assay
capabilities here, so a capability means the same thing everywhere.

Rules:

- The hierarchy is the ``modality_tree`` DAG. An assay keeps every path to
  every modality it reaches; none is chosen over another.
- A capability names an assay: an entity of type ``ASSAY_METHOD`` or
  ``ASSAY_TYPE``. Missing levels are never filled in (ATAC-seq is an
  ``ASSAY_TYPE`` with no method).
- A registered capability is identified by its registration code
  (``modality_name``, such as ``polya_rnaseq``); a vocabulary-only capability
  by ``entity_id``. The two are never confused.
- Labels, types and identifiers come from the vocabulary. Anything a caller
  supplies alongside a reference must match exactly, or it is rejected.
- Platform accession identifiers are never accepted from callers.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from nf_splice.catalogue.model import (
    ASSAY_TYPES,
    MODALITY_TREE,
    CatalogueError,
    Entity,
    EntityType,
    Provenance,
    Registration,
    Snapshot,
)

#: Keys a capability reference may carry.
REFERENCE_KEYS = frozenset(
    {"registered_code", "entity_id", "label", "entity_type", "evidence", "rationale",
     "sources"}
)  # fmt: skip
_ACCESSION_KEYS = frozenset({"accession", "accession_id", "splice_accession"})


@dataclass(frozen=True, slots=True)
class ResolvedCapability:
    """One pipeline capability with its full, deterministic classification."""

    registration: Registration | None
    assay: Entity
    paths: tuple[tuple[Entity, ...], ...]

    @property
    def key(self) -> str:
        if self.registration is not None:
            return self.registration.code
        return f"entity:{self.assay.entity_id}"

    def ancestors(self, kind: EntityType) -> tuple[Entity, ...]:
        found = {
            item.entity_id: item
            for path in self.paths
            for item in path[1:]
            if item.entity_type is kind
        }
        return tuple(found[key] for key in sorted(found))

    def to_json(self) -> dict[str, Any]:
        """The published form in ``bundle.json`` → ``pipeline.assay_capabilities``."""
        document: dict[str, Any] = {
            "kind": "registered_assay" if self.registration else "vocabulary_assay",
        }
        if self.registration is not None:
            document["registered_code"] = self.registration.code
        document["assay"] = self.assay.reference(with_type=True)
        document["assay_types"] = [
            item.reference() for item in self.ancestors(EntityType.ASSAY_TYPE)
        ]
        document["modality_subtypes"] = [
            item.reference() for item in self.ancestors(EntityType.MODALITY_SUBTYPE)
        ]
        document["modalities"] = [
            item.reference() for item in self.ancestors(EntityType.MODALITY)
        ]
        document["paths"] = [[item.entity_id for item in path] for path in self.paths]
        return document


@dataclass(frozen=True, slots=True)
class SearchHit:
    entity: Entity
    matched: tuple[str, ...]
    registrations: tuple[Registration, ...]
    paths: tuple[tuple[Entity, ...], ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "entity": self.entity.reference(with_type=True),
            "matched": list(self.matched),
            "registered_codes": [item.code for item in self.registrations],
            "paths": [
                [
                    {
                        "entity_id": item.entity_id,
                        "entity_type": item.entity_type.value,
                        "label": item.label,
                    }
                    for item in path
                ]
                for path in self.paths
            ],
        }


def _fold(text: str) -> str:
    return " ".join(text.casefold().split())


class Catalogue:
    """A validated vocabulary with lookup, traversal and selection checks."""

    def __init__(self, snapshot: Snapshot) -> None:
        self.snapshot = snapshot
        self.provenance: Provenance = snapshot.provenance
        self._entities = self._index_entities(snapshot.entities)
        self._parents = self._index_edges()
        self._registrations = self._index_registrations()
        self._check_acyclic()
        self._paths: dict[int, tuple[tuple[Entity, ...], ...]] = {}
        for entity in self._entities.values():
            if entity.entity_type in ASSAY_TYPES and not self.paths(entity.entity_id):
                raise CatalogueError(
                    "unreachable",
                    f"assay {entity.entity_id} ({entity.label}) reaches no MODALITY",
                )

    # ------------------------------------------------------------ validation

    @staticmethod
    def _index_entities(entities: Iterable[Entity]) -> dict[int, Entity]:
        found: dict[int, Entity] = {}
        for entity in entities:
            if entity.entity_id in found:
                raise CatalogueError(
                    "invalid_snapshot", f"entity {entity.entity_id} is listed twice"
                )
            found[entity.entity_id] = entity
        return found

    def _index_edges(self) -> dict[int, tuple[int, ...]]:
        parents: dict[int, set[int]] = defaultdict(set)
        for edge in self.snapshot.relationships:
            if edge.navigation != MODALITY_TREE:
                continue
            for end in (edge.child_entity_id, edge.ancestor_entity_id):
                if end not in self._entities:
                    raise CatalogueError(
                        "broken_edge",
                        f"relationship {edge.id} refers to unknown entity {end}",
                    )
            if edge.child_entity_id == edge.ancestor_entity_id:
                raise CatalogueError(
                    "cycle", f"relationship {edge.id} links entity to itself"
                )
            parents[edge.child_entity_id].add(edge.ancestor_entity_id)
        return {key: tuple(sorted(value)) for key, value in parents.items()}

    def _index_registrations(self) -> dict[str, Registration]:
        found: dict[str, Registration] = {}
        ids: set[int] = set()
        for item in self.snapshot.registrations:
            if item.code in found or item.modality_id in ids:
                raise CatalogueError(
                    "invalid_snapshot", f"registration {item.code!r} is not unique"
                )
            if item.entity_id is not None and item.entity_id not in self._entities:
                raise CatalogueError(
                    "broken_edge",
                    f"registration {item.code!r} links unknown entity {item.entity_id}",
                )
            found[item.code] = item
            ids.add(item.modality_id)
        return found

    def _check_acyclic(self) -> None:
        state: dict[int, int] = {}

        def visit(node: int, trail: tuple[int, ...]) -> None:
            if state.get(node) == 2:
                return
            if state.get(node) == 1:
                cycle = " -> ".join(str(item) for item in (*trail, node))
                raise CatalogueError("cycle", f"the hierarchy has a cycle: {cycle}")
            state[node] = 1
            for parent in self._parents.get(node, ()):
                visit(parent, (*trail, node))
            state[node] = 2

        for node in sorted(self._entities):
            visit(node, ())

    # --------------------------------------------------------------- lookups

    def entity(self, entity_id: int) -> Entity:
        try:
            return self._entities[entity_id]
        except KeyError:
            raise CatalogueError(
                "unknown_entity", f"no vocabulary entity {entity_id}"
            ) from None

    def entities(self, kind: EntityType | None = None) -> tuple[Entity, ...]:
        return tuple(
            self._entities[key]
            for key in sorted(self._entities)
            if kind is None or self._entities[key].entity_type is kind
        )

    def registrations(self) -> tuple[Registration, ...]:
        return tuple(sorted(self._registrations.values(), key=lambda item: item.code))

    def registration(self, code: str) -> Registration:
        try:
            return self._registrations[code]
        except KeyError:
            raise CatalogueError(
                "unknown_code", f"{code!r} is not a registered assay code"
            ) from None

    def registrations_for(self, entity_id: int) -> tuple[Registration, ...]:
        return tuple(
            item for item in self.registrations() if item.entity_id == entity_id
        )

    def parents(self, entity_id: int) -> tuple[Entity, ...]:
        return tuple(self._entities[key] for key in self._parents.get(entity_id, ()))

    def children(self, entity_id: int) -> tuple[Entity, ...]:
        return tuple(
            self._entities[key]
            for key in sorted(self._parents)
            if entity_id in self._parents[key]
        )

    def paths(self, entity_id: int) -> tuple[tuple[Entity, ...], ...]:
        """Every path from the entity up to a MODALITY, in entity-id order.

        A path stops at the first MODALITY; the root is never part of it.
        """
        if entity_id in self._paths:
            return self._paths[entity_id]
        start = self.entity(entity_id)
        found: list[tuple[Entity, ...]] = []

        def walk(node: Entity, trail: tuple[Entity, ...]) -> None:
            trail = (*trail, node)
            if node.entity_type is EntityType.MODALITY:
                found.append(trail)
                return
            for parent in self.parents(node.entity_id):
                if parent.entity_type is not EntityType.ROOT:
                    walk(parent, trail)

        walk(start, ())
        result = tuple(
            sorted(found, key=lambda path: tuple(item.entity_id for item in path))
        )
        self._paths[entity_id] = result
        return result

    def modalities_of(self, entity_id: int) -> tuple[Entity, ...]:
        found = {path[-1].entity_id: path[-1] for path in self.paths(entity_id)}
        return tuple(found[key] for key in sorted(found))

    def assays(
        self, modality: str | int | None = None, *, registered_only: bool = True
    ) -> tuple[ResolvedCapability, ...]:
        """Assays, optionally under one modality (by label or entity id)."""
        target = None if modality is None else self._modality(modality)
        found = []
        if registered_only:
            for item in self.registrations():
                if item.entity_id is None:
                    continue
                found.append(self._resolve_registration(item))
        else:
            for entity in self.entities():
                if entity.entity_type in ASSAY_TYPES:
                    found.append(
                        ResolvedCapability(None, entity, self.paths(entity.entity_id))
                    )
        if target is not None:
            found = [
                item
                for item in found
                if target.entity_id in {path[-1].entity_id for path in item.paths}
            ]
        return tuple(found)

    def _modality(self, value: str | int) -> Entity:
        candidates = [
            item
            for item in self.entities(EntityType.MODALITY)
            if str(item.entity_id) == str(value)
            or _fold(item.label) == _fold(str(value))
        ]
        if not candidates:
            raise CatalogueError("unknown_entity", f"no MODALITY {value!r}")
        return candidates[0]

    # ---------------------------------------------------------------- search

    def search(self, text: str) -> tuple[SearchHit, ...]:
        """Entities whose label, alias, registration code or id contains ``text``."""
        query = _fold(text.removeprefix("entity:"))
        if not query:
            return ()
        hits = []
        for entity in self.entities():
            registrations = self.registrations_for(entity.entity_id)
            matched = []
            if query == str(entity.entity_id):
                matched.append("entity_id")
            if query in _fold(entity.label):
                matched.append("label")
            if any(query in _fold(alias) for alias in entity.aliases):
                matched.append("alias")
            if any(query in item.code.casefold() for item in registrations):
                matched.append("registered_code")
            if matched and entity.entity_type is not EntityType.ROOT:
                hits.append(
                    SearchHit(
                        entity,
                        tuple(matched),
                        registrations,
                        self.paths(entity.entity_id)
                        if entity.entity_type is not EntityType.MODALITY
                        else ((entity,),),
                    )
                )
        return tuple(hits)

    def by_name(self, text: str) -> Entity:
        """The one entity whose label or an alias equals ``text`` exactly."""
        query = _fold(text)
        found = {
            entity.entity_id: entity
            for entity in self.entities()
            if _fold(entity.label) == query
            or any(_fold(alias) == query for alias in entity.aliases)
        }
        if not found:
            raise CatalogueError(
                "unknown_entity", f"no vocabulary entity named {text!r}"
            )
        if len(found) > 1:
            options = ", ".join(
                f"{item.entity_id} ({item.entity_type.value} {item.label})"
                for item in found.values()
            )
            raise CatalogueError(
                "ambiguous", f"{text!r} names several entities: {options}"
            )
        return next(iter(found.values()))

    # ------------------------------------------------------------ resolution

    def _resolve_registration(self, registration: Registration) -> ResolvedCapability:
        if registration.entity_id is None:
            raise CatalogueError(
                "unknown_entity",
                f"registration {registration.code!r} links no vocabulary entity",
            )
        entity = self.entity(registration.entity_id)
        if entity.entity_type not in ASSAY_TYPES:
            raise CatalogueError(
                "not_an_assay",
                f"registration {registration.code!r} links "
                f"{entity.entity_type.value} {entity.label!r}, not an assay",
            )
        return ResolvedCapability(registration, entity, self.paths(entity.entity_id))

    def resolve_code(self, code: str) -> ResolvedCapability:
        return self._resolve_registration(self.registration(code))

    def resolve_reference(
        self, reference: str | Mapping[str, Any]
    ) -> ResolvedCapability:
        """Resolve one reference: a code, ``entity:<id>``, or a mapping.

        A mapping has ``registered_code`` or ``entity_id``; any ``label`` or
        ``entity_type`` it carries must match the vocabulary exactly.
        """
        if isinstance(reference, str):
            text = reference.strip()
            if text.startswith("entity:"):
                return self._resolve_entity(
                    _entity_number(text.removeprefix("entity:"))
                )
            return self.resolve_code(text)
        fields = dict(reference)
        accession = sorted(_ACCESSION_KEYS & set(fields))
        if accession:
            raise CatalogueError(
                "accession_not_accepted",
                "platform accession identifiers come only from the SPLICE platform; "
                f"remove {', '.join(accession)}",
            )
        unknown = sorted(set(fields) - REFERENCE_KEYS)
        if unknown:
            raise CatalogueError(
                "mismatch", f"unknown capability field(s): {', '.join(unknown)}"
            )
        code, number = fields.get("registered_code"), fields.get("entity_id")
        if (code is None) == (number is None):
            raise CatalogueError(
                "mismatch", "give exactly one of registered_code or entity_id"
            )
        resolved = (
            self.resolve_code(str(code))
            if code is not None
            else self._resolve_entity(_entity_number(number))
        )
        if fields.get("label") not in (None, resolved.assay.label):
            raise CatalogueError(
                "mismatch",
                f"{resolved.key} is labelled {resolved.assay.label!r}, "
                f"not {fields['label']!r}",
            )
        if fields.get("entity_type") not in (None, resolved.assay.entity_type.value):
            raise CatalogueError(
                "mismatch",
                f"{resolved.key} is an {resolved.assay.entity_type.value}, "
                f"not {fields['entity_type']!r}",
            )
        return resolved

    def _resolve_entity(self, entity_id: int) -> ResolvedCapability:
        entity = self.entity(entity_id)
        if entity.entity_type not in ASSAY_TYPES:
            raise CatalogueError(
                "not_an_assay",
                f"{entity.label!r} is a {entity.entity_type.value}; a capability "
                "names an ASSAY_METHOD or ASSAY_TYPE",
            )
        return ResolvedCapability(None, entity, self.paths(entity_id))

    def resolve_selection(
        self, references: Sequence[str | Mapping[str, Any]]
    ) -> tuple[ResolvedCapability, ...]:
        """Resolve zero or more capabilities; duplicates are rejected.

        Two references to the same registration, or to the same vocabulary
        entity without a registration, are duplicates. The order is kept.
        """
        resolved: list[ResolvedCapability] = []
        seen: dict[str, int] = {}
        for index, reference in enumerate(references):
            item = self.resolve_reference(reference)
            if item.key in seen:
                raise CatalogueError(
                    "duplicate",
                    f"{item.key} is selected twice (entries {seen[item.key] + 1} "
                    f"and {index + 1})",
                )
            seen[item.key] = index
            resolved.append(item)
        return tuple(resolved)


def _entity_number(value: Any) -> int:
    if isinstance(value, bool):
        raise CatalogueError("unknown_entity", f"invalid entity id {value!r}")
    try:
        return int(str(value).strip())
    except ValueError:
        raise CatalogueError("unknown_entity", f"invalid entity id {value!r}") from None
