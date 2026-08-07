"""Reviewed software-component and container inventory models."""

from __future__ import annotations

from pydantic import model_validator

from nf_splice.domain.authoring import DomainModel, NonEmptyString


class ComponentCandidate(DomainModel):
    """Detected workflow component with all competing software evidence."""

    id: NonEmptyString
    name: NonEmptyString
    path: NonEmptyString
    namespace: NonEmptyString
    tool_name: NonEmptyString
    versions: tuple[NonEmptyString, ...] = ()
    container_uris: tuple[NonEmptyString, ...] = ()
    conda_packages: tuple[NonEmptyString, ...] = ()
    unresolved_fields: tuple[NonEmptyString, ...] = ()


class ReviewedComponent(DomainModel):
    """Explicitly selected software identity for one workflow component."""

    id: NonEmptyString
    name: NonEmptyString
    path: NonEmptyString
    namespace: NonEmptyString
    tool_name: NonEmptyString
    version: NonEmptyString | None = None
    container_uri: NonEmptyString | None = None
    conda_packages: tuple[NonEmptyString, ...] = ()
    evidence_locations: tuple[NonEmptyString, ...]

    @model_validator(mode="after")
    def validate_evidence(self) -> ReviewedComponent:
        """Every materialised component must retain source evidence."""
        if not self.evidence_locations:
            raise ValueError("a reviewed component requires source evidence")
        if len(self.evidence_locations) != len(set(self.evidence_locations)):
            raise ValueError("component evidence locations must be unique")
        return self
