"""Shared base types for nf-splice domain models."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, JsonValue

NonEmptyString = Annotated[str, Field(min_length=1)]


class DomainModel(BaseModel):
    """Strict, immutable base for canonical domain values."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class EvidenceProvenance(DomainModel):
    """Location and revision from which evidence was observed."""

    source: NonEmptyString
    location: NonEmptyString
    repository_revision: NonEmptyString | None = None


class Evidence(DomainModel):
    """A detected fact that may support one or more decisions."""

    id: NonEmptyString
    provenance: EvidenceProvenance
    observed_value: JsonValue
    confidence: float = Field(ge=0.0, le=1.0)
