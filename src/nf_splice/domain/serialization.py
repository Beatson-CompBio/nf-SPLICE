"""Deterministic YAML serialization for canonical authoring state."""

from __future__ import annotations

import yaml  # type: ignore[import-untyped]
from pydantic import ValidationError
from yaml import YAMLError

from nf_splice.domain.authoring import (
    AUTHORING_SCHEMA_VERSION,
    AuthoringDocument,
)


class AuthoringDocumentError(ValueError):
    """Base error for authoring document loading failures."""


class InvalidAuthoringDocument(AuthoringDocumentError):
    """Raised when YAML does not contain valid canonical authoring state."""


class UnsupportedSchemaVersion(AuthoringDocumentError):
    """Raised at the boundary where a future migration may be selected."""

    def __init__(self, version: object) -> None:
        super().__init__(
            f"unsupported authoring schema version {version!r}; "
            f"expected {AUTHORING_SCHEMA_VERSION!r}"
        )
        self.version = version


def dump_authoring_document(document: AuthoringDocument) -> str:
    """Return a stable YAML representation of an authoring document."""
    content: object = yaml.safe_dump(
        document.model_dump(mode="json"),
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=88,
    )
    if not isinstance(content, str):
        raise TypeError("YAML serializer did not return text")
    return content


def load_authoring_document(content: str) -> AuthoringDocument:
    """Load current canonical state or fail explicitly at its version boundary."""
    try:
        loaded: object = yaml.safe_load(content)
    except YAMLError as error:
        raise InvalidAuthoringDocument(f"invalid YAML: {error}") from error

    if not isinstance(loaded, dict):
        raise InvalidAuthoringDocument("authoring state must be a YAML mapping")

    if "schema_version" not in loaded:
        raise InvalidAuthoringDocument("authoring state is missing schema_version")
    if loaded["schema_version"] != AUTHORING_SCHEMA_VERSION:
        raise UnsupportedSchemaVersion(loaded["schema_version"])

    try:
        return AuthoringDocument.model_validate(loaded)
    except ValidationError as error:
        raise InvalidAuthoringDocument(str(error)) from error
