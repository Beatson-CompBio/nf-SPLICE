"""Reviewed workflow provenance domain models."""

from __future__ import annotations

from enum import Enum

from pydantic import Field, model_validator

from nf_splice.domain.authoring import DomainModel, NonEmptyString


class ProvenanceStrategy(str, Enum):
    """Explicit source strategy for the generated workflow RO-Crate."""

    MINIMAL_INTERNAL = "minimal_internal"
    NORMALIZE_EXISTING = "normalize_existing"
    SUPPLIED_FILE = "supplied_file"


class ProvenanceCandidate(DomainModel):
    """One detected or built-in RO-Crate generation strategy."""

    id: NonEmptyString
    strategy: ProvenanceStrategy
    source_path: NonEmptyString | None = None
    evidence_locations: tuple[NonEmptyString, ...] = ()


class ReviewedAuthor(DomainModel):
    """Reviewed workflow author represented in RO-Crate metadata."""

    name: NonEmptyString
    identifier: NonEmptyString | None = None


class ReviewedProvenance(DomainModel):
    """Complete reviewed inputs to one deterministic RO-Crate strategy."""

    strategy: ProvenanceStrategy
    source_path: NonEmptyString | None = None
    authors: tuple[ReviewedAuthor, ...]
    licenses: tuple[NonEmptyString, ...]
    published_at: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    source_revision: NonEmptyString
    evidence_locations: tuple[NonEmptyString, ...]

    @model_validator(mode="after")
    def validate_review(self) -> ReviewedProvenance:
        """Require explicit people, licensing, revision, and source selection."""
        if not self.authors:
            raise ValueError("reviewed provenance requires at least one author")
        if not self.licenses:
            raise ValueError("reviewed provenance requires at least one licence")
        if len(self.licenses) != len(set(self.licenses)):
            raise ValueError("reviewed provenance licences must be unique")
        if not self.evidence_locations:
            raise ValueError("reviewed provenance requires source evidence")
        needs_source = self.strategy in {
            ProvenanceStrategy.NORMALIZE_EXISTING,
            ProvenanceStrategy.SUPPLIED_FILE,
        }
        if needs_source != (self.source_path is not None):
            raise ValueError(
                f"provenance strategy {self.strategy.value!r} "
                "has an inconsistent source path"
            )
        return self
