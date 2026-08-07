"""Reviewed projection models for Nextflow pipeline parameters."""

from __future__ import annotations

from enum import Enum

from pydantic import Field, JsonValue, model_validator

from nf_splice.domain.authoring import DomainModel, NonEmptyString


class InputClassification(str, Enum):
    """Ownership of a pipeline parameter in the SPLICE integration."""

    USER_CONFIGURABLE = "user-configurable"
    PLATFORM_MANAGED = "platform-managed"
    EXECUTION_ENVIRONMENT_MANAGED = "execution-environment-managed"
    HIDDEN_OR_UNSUPPORTED = "hidden-or-unsupported"


class InputCandidate(DomainModel):
    """Upstream parameter evidence awaiting an ownership decision."""

    id: NonEmptyString
    name: NonEmptyString
    group: NonEmptyString
    group_title: NonEmptyString
    group_description: str = ""
    schema_fragment: dict[str, JsonValue]
    unresolved_fields: tuple[NonEmptyString, ...] = ()


class ReviewedInput(DomainModel):
    """Explicit classification and validated projected parameter shape."""

    name: NonEmptyString
    group: NonEmptyString
    group_title: NonEmptyString
    group_description: str = ""
    classification: InputClassification
    schema_fragment: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_projection(self) -> ReviewedInput:
        """Require usable semantics only for developer-configurable inputs."""
        if self.classification is not InputClassification.USER_CONFIGURABLE:
            return self
        parameter_type = self.schema_fragment.get("type")
        description = self.schema_fragment.get("description")
        if not isinstance(parameter_type, str) or not parameter_type:
            raise ValueError("a user-configurable input requires an explicit type")
        if not isinstance(description, str) or not description.strip():
            raise ValueError(
                "a user-configurable input requires an explicit description"
            )
        return self
