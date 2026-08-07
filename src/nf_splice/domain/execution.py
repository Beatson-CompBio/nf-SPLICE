"""Reviewed execution-profile and configuration domain models."""

from __future__ import annotations

from enum import Enum

from pydantic import Field, model_validator

from nf_splice.domain.authoring import DomainModel, NonEmptyString


class EnvironmentUse(str, Enum):
    """Declared support purpose for an execution environment."""

    TEST = "test"
    DEVELOPMENT = "development"
    PRODUCTION = "production"


class ExecutionProfileCandidate(DomainModel):
    """Detected profile evidence that has not yet been selected for SPLICE."""

    id: NonEmptyString
    name: NonEmptyString
    source_profile: NonEmptyString
    config_sources: tuple[NonEmptyString, ...] = ()
    executors: tuple[NonEmptyString, ...] = ()
    container_engines: tuple[NonEmptyString, ...] = ()
    unresolved_fields: tuple[NonEmptyString, ...] = ()


class ReviewedExecutionProfile(DomainModel):
    """One explicitly supported and fully resolved execution environment."""

    id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    name: NonEmptyString
    description: NonEmptyString
    use: EnvironmentUse
    executor: NonEmptyString
    container_engine: NonEmptyString
    source_profile: NonEmptyString
    config_sources: tuple[NonEmptyString, ...]
    config_path: str = Field(pattern=r"^configs/[a-z][a-z0-9_-]*\.config$")
    evidence_locations: tuple[NonEmptyString, ...]

    @model_validator(mode="after")
    def validate_relationships(self) -> ReviewedExecutionProfile:
        """Keep the selected profile, sources, and generated config unambiguous."""
        if not self.config_sources:
            raise ValueError("a reviewed execution profile requires a config source")
        if len(self.config_sources) != len(set(self.config_sources)):
            raise ValueError("execution config sources must be unique")
        if not self.evidence_locations:
            raise ValueError("a reviewed execution profile requires source evidence")
        if len(self.evidence_locations) != len(set(self.evidence_locations)):
            raise ValueError("execution evidence locations must be unique")
        if self.config_path != f"configs/{self.id}.config":
            raise ValueError("execution config path must match the profile id")
        return self
