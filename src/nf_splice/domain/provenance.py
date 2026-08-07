"""Reviewed workflow provenance domain models."""

from __future__ import annotations

from pydantic import model_validator

from nf_splice.domain.authoring import DomainModel, NonEmptyString


class ProvenanceCandidate(DomainModel):
    """The repository-root RO-Crate offered for explicit inclusion."""

    id: NonEmptyString
    source_path: NonEmptyString
    evidence_locations: tuple[NonEmptyString, ...] = ()


class ReviewedProvenance(DomainModel):
    """Explicit approval to include the repository-root RO-Crate unchanged."""

    source_path: NonEmptyString
    evidence_locations: tuple[NonEmptyString, ...]

    @model_validator(mode="after")
    def validate_review(self) -> ReviewedProvenance:
        """Require one repository-root source and its evidence."""
        if self.source_path != "ro-crate-metadata.json":
            raise ValueError(
                "RO-Crate source must be repository-root ro-crate-metadata.json"
            )
        if not self.evidence_locations:
            raise ValueError("reviewed provenance requires source evidence")
        return self
