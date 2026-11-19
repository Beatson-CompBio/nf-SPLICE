"""Where a vocabulary comes from: the packaged snapshot today, the API later.

All sources produce a :class:`~nf_splice.catalogue.model.Snapshot`; the
resolver never knows which one it got. Rules:

- The packaged snapshot is pinned: its content digest must match the digest
  recorded when it was compiled, or it is refused.
- An API response is untrusted: every field is type-checked, and anything
  unexpected is refused rather than repaired.
- A live vocabulary that disagrees with the pinned snapshot (a different
  label, type, edge target or registration link for the same identifier) is
  a conflict and is refused unless the caller explicitly reconciles it.
  Additions are reported as a stale snapshot, not as conflicts.
- Falling back to the packaged snapshot after an API failure happens only
  when the caller asks for it, and the provenance says so.
- Accession identifiers are kept only when the API supplies them; nothing
  derives one.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from functools import lru_cache
from importlib import resources
from typing import Any, Protocol

from nf_splice.catalogue.model import (
    CatalogueError,
    Entity,
    EntityType,
    Provenance,
    Registration,
    Relationship,
    Snapshot,
    content_document,
)

PACKAGED = "assay-vocabulary.json"
FORMAT = "nf-splice-assay-vocabulary/1"
_ACCESSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


class VocabularySource(Protocol):
    """Anything that can supply a complete vocabulary snapshot."""

    def load(self) -> Snapshot: ...


def digest(snapshot: Snapshot) -> str:
    payload = json.dumps(content_document(snapshot), sort_keys=True, ensure_ascii=False)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _require(value: Any, kind: type | tuple[type, ...], where: str) -> Any:
    if not isinstance(value, kind) or (isinstance(value, bool) and kind is int):
        raise CatalogueError(
            "untrusted_response", f"{where}: unexpected value {value!r}"
        )
    return value


def _optional_text(value: Any, where: str) -> str | None:
    if value is None or value == "":
        return None
    return str(_require(value, str, where))


def _entity(row: Mapping[str, Any], where: str) -> Entity:
    kind = str(_require(row.get("entity_type"), str, f"{where}.entity_type"))
    try:
        entity_type = EntityType(kind)
    except ValueError:
        raise CatalogueError(
            "untrusted_response", f"{where}: unknown entity_type {kind!r}"
        ) from None
    aliases = row.get("aliases") or []
    if isinstance(aliases, str):
        aliases = [item for item in aliases.split("|")]
    aliases = [str(_require(item, str, f"{where}.aliases")).strip() for item in aliases]
    return Entity(
        entity_id=_require(row.get("entity_id"), int, f"{where}.entity_id"),
        label=str(_require(row.get("label"), str, f"{where}.label")).strip(),
        entity_type=entity_type,
        description=_optional_text(row.get("description"), f"{where}.description"),
        aliases=tuple(item for item in aliases if item),
        concept_status=str(_require(row.get("concept_status"), str, where)),
        implementation_status=str(
            _require(row.get("implementation_status"), str, where)
        ),
    )


def _relationship(row: Mapping[str, Any], where: str) -> Relationship:
    return Relationship(
        id=_require(row.get("id"), int, f"{where}.id"),
        child_entity_id=_require(row.get("child_entity_id"), int, f"{where}.child"),
        ancestor_entity_id=_require(
            row.get("ancestor_entity_id"), int, f"{where}.ancestor"
        ),
        navigation=str(_require(row.get("navigation"), str, f"{where}.navigation")),
    )


def _registration(
    row: Mapping[str, Any], where: str, *, trusted_accession: bool
) -> Registration:
    entity_id = row.get("entity_id")
    current = row.get("current")
    if isinstance(current, str):
        current = {"true": True, "false": False}.get(current.lower(), current)
    accession = row.get("accession_id") if trusted_accession else None
    if accession is not None and not (
        isinstance(accession, str) and _ACCESSION.match(accession)
    ):
        raise CatalogueError("untrusted_response", f"{where}: invalid accession_id")
    version = row.get("schema_version_splice")
    return Registration(
        modality_id=_require(row.get("modality_id"), int, f"{where}.modality_id"),
        code=str(_require(row.get("modality_name"), str, f"{where}.modality_name")),
        entity_id=None if entity_id is None else _require(entity_id, int, where),
        current=bool(_require(current, bool, f"{where}.current")),
        schema_version_splice=None if version is None else str(version),
        schema_version_ext=_optional_text(row.get("schema_version_ext"), where),
        accession_id=accession,
    )


def snapshot_from_document(
    document: Mapping[str, Any],
    provenance: Provenance,
    *,
    trusted_accession: bool = False,
) -> Snapshot:
    """Build a snapshot from parsed rows, checking every field."""
    for key in ("entities", "relationships", "registrations"):
        if not isinstance(document.get(key), list):
            raise CatalogueError("untrusted_response", f"{key} must be a list")
    return Snapshot(
        provenance=provenance,
        entities=tuple(
            _entity(_require(row, dict, f"entities[{index}]"), f"entities[{index}]")
            for index, row in enumerate(document["entities"])
        ),
        relationships=tuple(
            _relationship(
                _require(row, dict, f"relationships[{index}]"),
                f"relationships[{index}]",
            )
            for index, row in enumerate(document["relationships"])
        ),
        registrations=tuple(
            _registration(
                _require(row, dict, f"registrations[{index}]"),
                f"registrations[{index}]",
                trusted_accession=trusted_accession,
            )
            for index, row in enumerate(document["registrations"])
        ),
    )


class PackagedSnapshot:
    """The vocabulary snapshot packaged with nf-splice (offline)."""

    def load(self) -> Snapshot:
        text = (
            resources.files("nf_splice.catalogue")
            .joinpath("data")
            .joinpath(PACKAGED)
            .read_text(encoding="utf-8")
        )
        document = json.loads(text)
        if document.get("format") != FORMAT:
            raise CatalogueError(
                "invalid_snapshot", "unknown packaged vocabulary format"
            )
        meta = document["snapshot"]
        provenance = Provenance(
            snapshot_id=meta["id"],
            name=meta["name"],
            origin=meta["origin"],
            digest=meta["digest"],
            source="packaged_snapshot",
            source_files=dict(meta.get("source_files") or {}),
        )
        snapshot = snapshot_from_document(document, provenance)
        if digest(snapshot) != provenance.digest:
            raise CatalogueError(
                "invalid_snapshot", "the packaged vocabulary does not match its digest"
            )
        return snapshot


Fetch = Callable[[str], Any]


@dataclass(slots=True)
class ApiVocabularySource:
    """A SPLICE platform API (``/modality-entities``, ``/modality-relationships``,
    ``/modalities``). The endpoints exist in the platform; their final,
    authenticated contract does not yet, so responses are checked strictly.
    """

    base_url: str
    fetch: Fetch
    snapshot_id: str = "live"

    def _rows(self, path: str) -> list[Any]:
        try:
            body = self.fetch(f"{self.base_url.rstrip('/')}/{path}")
        except CatalogueError:
            raise
        except Exception as error:  # network, TLS, timeout: all "unavailable"
            raise CatalogueError(
                "unavailable", f"the vocabulary API could not be reached: {error}"
            ) from None
        if isinstance(body, dict):
            body = body.get("items", body.get("data"))
        if not isinstance(body, list):
            raise CatalogueError("untrusted_response", f"{path}: expected a list")
        return body

    def load(self) -> Snapshot:
        document = {
            "entities": self._rows("modality-entities"),
            "relationships": self._rows("modality-relationships"),
            "registrations": self._rows("modalities"),
        }
        provisional = Provenance(
            snapshot_id=self.snapshot_id,
            name="SPLICE modality vocabulary",
            origin=self.base_url,
            digest="",
            source="api",
        )
        snapshot = snapshot_from_document(document, provisional, trusted_accession=True)
        return replace(
            snapshot, provenance=replace(provisional, digest=digest(snapshot))
        )


@dataclass(frozen=True, slots=True)
class Reconciliation:
    """How a live vocabulary compares with the pinned snapshot."""

    conflicts: tuple[str, ...]
    additions: tuple[str, ...]

    @property
    def stale(self) -> bool:
        return bool(self.additions)


def compare(pinned: Snapshot, live: Snapshot) -> Reconciliation:
    conflicts: list[str] = []
    additions: list[str] = []
    old = {item.entity_id: item for item in pinned.entities}
    for item in live.entities:
        before = old.get(item.entity_id)
        if before is None:
            additions.append(f"entity {item.entity_id} {item.label!r}")
        elif (before.label, before.entity_type) != (item.label, item.entity_type):
            conflicts.append(
                f"entity {item.entity_id}: pinned {before.entity_type.value} "
                f"{before.label!r}, live {item.entity_type.value} {item.label!r}"
            )
    missing = sorted(set(old) - {item.entity_id for item in live.entities})
    conflicts.extend(
        f"entity {key} is missing from the live vocabulary" for key in missing
    )
    edges = {
        (e.child_entity_id, e.ancestor_entity_id, e.navigation)
        for e in pinned.relationships
    }
    live_edges = {
        (e.child_entity_id, e.ancestor_entity_id, e.navigation)
        for e in live.relationships
    }
    conflicts.extend(
        f"edge {child} -> {parent} is missing from the live vocabulary"
        for child, parent, _nav in sorted(edges - live_edges)
    )
    additions.extend(
        f"edge {child} -> {parent}"
        for child, parent, _nav in sorted(live_edges - edges)
    )
    codes = {item.code: item for item in pinned.registrations}
    for registration in live.registrations:
        pinned_registration = codes.get(registration.code)
        if pinned_registration is None:
            additions.append(f"registration {registration.code!r}")
        elif pinned_registration.entity_id != registration.entity_id:
            conflicts.append(
                f"registration {registration.code!r}: pinned entity "
                f"{pinned_registration.entity_id}, live entity {registration.entity_id}"
            )
    return Reconciliation(tuple(conflicts), tuple(additions))


def load_live(
    source: VocabularySource,
    pinned: Snapshot,
    *,
    reconcile: bool = False,
    fallback: bool = False,
) -> tuple[Snapshot, Reconciliation | None]:
    """Load a live vocabulary, refusing conflicts unless reconciled.

    With ``fallback``, an unreachable source yields the pinned snapshot with a
    provenance note saying so; nothing is silently guessed.
    """
    try:
        live = source.load()
    except CatalogueError as error:
        if fallback and error.code == "unavailable":
            note = f"live vocabulary unavailable ({error}); using the pinned snapshot"
            return replace(
                pinned, provenance=replace(pinned.provenance, note=note)
            ), None
        raise
    result = compare(pinned, live)
    if result.conflicts and not reconcile:
        raise CatalogueError(
            "conflict",
            "the live vocabulary conflicts with the pinned snapshot: "
            + "; ".join(result.conflicts[:10]),
        )
    return live, result


@lru_cache(maxsize=1)
def packaged_snapshot() -> Snapshot:
    return PackagedSnapshot().load()
