"""The SPLICE assay and modality catalogue (offline, versioned, typed).

A packaged snapshot of the SPLICE platform's modality vocabulary, its
registered assays, and one resolver that every interface and the bundle
compiler use. This is separate from :mod:`nf_splice.vocabulary`, which audits
nf-splice's own reserved terminology.
"""

from __future__ import annotations

from functools import lru_cache

from nf_splice.catalogue.model import (
    ASSAY_TYPES,
    CatalogueError,
    Entity,
    EntityType,
    Provenance,
    Registration,
    Relationship,
    Snapshot,
)
from nf_splice.catalogue.resolver import Catalogue, ResolvedCapability, SearchHit
from nf_splice.catalogue.sources import (
    ApiVocabularySource,
    PackagedSnapshot,
    Reconciliation,
    VocabularySource,
    compare,
    digest,
    load_live,
    packaged_snapshot,
)


@lru_cache(maxsize=1)
def default_catalogue() -> Catalogue:
    """The resolver over the packaged snapshot, used by every interface."""
    return Catalogue(packaged_snapshot())


__all__ = [
    "ASSAY_TYPES",
    "ApiVocabularySource",
    "Catalogue",
    "CatalogueError",
    "Entity",
    "EntityType",
    "PackagedSnapshot",
    "Provenance",
    "Reconciliation",
    "Registration",
    "Relationship",
    "ResolvedCapability",
    "SearchHit",
    "Snapshot",
    "VocabularySource",
    "compare",
    "default_catalogue",
    "digest",
    "load_live",
    "packaged_snapshot",
]
