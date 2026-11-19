"""Pipeline identity helpers shared by every detached contract."""

from __future__ import annotations

import re
from enum import Enum
from typing import Annotated, Literal

from pydantic import StringConstraints, model_validator

from nf_splice.domain.base import DomainModel, NonEmptyString


class PipelineIdError(ValueError):
    """Raised when a pipeline name cannot form a stable bundle identifier."""


def derive_pipeline_id(name: str) -> str:
    """Derive the stable, collision-safe slug used as the pipeline ``id``.

    The identifier is derived once from the reviewed name; later display-name
    changes must not silently re-identify an existing bundle.
    """
    identifier = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not identifier:
        raise PipelineIdError("pipeline name cannot form a stable bundle id")
    return identifier


_ORCID_BARE = re.compile(r"^(\d{4})-?(\d{4})-?(\d{4})-?(\d{3}[\dX])$")
_ORCID_URL = re.compile(r"^(?:https?://)?(?:www\.)?orcid\.org/(.+?)/?$", re.IGNORECASE)


def _orcid_checksum(digits: str) -> str:
    """ISO 7064 MOD 11-2 check character of the first 15 ORCID digits."""
    total = 0
    for digit in digits:
        total = (total + int(digit)) * 2
    result = (12 - total % 11) % 11
    return "X" if result == 10 else str(result)


def normalise_orcid(value: str) -> str | None:
    """The canonical ``https://orcid.org/…`` form of an ORCID iD, or ``None``.

    Accepts the bare identifier (``0000-0002-1825-0097``, with or without
    hyphens) or an ``orcid.org`` URL in any scheme or case, and checks the
    ISO 7064 check digit. A value that is not a valid ORCID iD is never
    repaired or guessed: the result is ``None``.
    """
    text = value.strip()
    match = _ORCID_URL.match(text)
    if match is not None:
        text = match.group(1)
    found = _ORCID_BARE.match(text.upper())
    if found is None:
        return None
    digits = "".join(found.groups())
    if _orcid_checksum(digits[:15]) != digits[15]:
        return None
    return "https://orcid.org/" + "-".join(found.groups())


# ---------------------------------------------------------------------------
# Reviewed pipeline metadata (bundle.draft.yaml -> bundle.json "pipeline")
# ---------------------------------------------------------------------------

PipelineId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]*$")]
HttpUrl = Annotated[
    str,
    StringConstraints(
        pattern=r"^https?://[^\s/@:]+(?::[0-9]+)?(?:/[^\s]*)?$", max_length=2048
    ),
]
Orcid = Annotated[
    str,
    StringConstraints(
        pattern=r"^https://orcid\.org/[0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9]{3}[0-9X]$"
    ),
]
Doi = Annotated[str, StringConstraints(pattern=r"^10\.[0-9]{4,9}/\S+$")]


class AgentType(str, Enum):
    """Whether a credited party is an individual or an organisation."""

    PERSON = "person"
    ORGANIZATION = "organization"


class Contributor(DomainModel):
    """One credited author, ordered as reviewed."""

    name: NonEmptyString
    type: AgentType = AgentType.PERSON
    affiliation: NonEmptyString | None = None
    orcid: Orcid | None = None
    role: NonEmptyString | None = None

    @model_validator(mode="after")
    def validate_orcid_owner(self) -> Contributor:
        if self.orcid is not None and self.type is AgentType.ORGANIZATION:
            raise ValueError("an ORCID identifies a person, not an organisation")
        return self


class Funder(DomainModel):
    """A funding body and optional award; identifiers are never guessed."""

    name: NonEmptyString
    award_id: NonEmptyString | None = None
    award_title: NonEmptyString | None = None
    url: HttpUrl | None = None


class Citation(DomainModel):
    """Structured citation metadata; at least one locator is required."""

    doi: Doi | None = None
    url: HttpUrl | None = None
    text: NonEmptyString | None = None
    cff_path: NonEmptyString | None = None

    @model_validator(mode="after")
    def validate_locator(self) -> Citation:
        if not any((self.doi, self.url, self.text, self.cff_path)):
            raise ValueError("a citation needs a DOI, URL, text or CFF path")
        return self


class Maintainer(DomainModel):
    """An explicitly approved public contact published in bundle.json."""

    name: NonEmptyString
    role: NonEmptyString | None = None
    affiliation: NonEmptyString | None = None
    contact_url: HttpUrl | None = None
    email: (
        Annotated[str, StringConstraints(pattern=r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")]
        | None
    ) = None


class VocabularyReference(DomainModel):
    """A SPLICE vocabulary entity, by id with its exact label."""

    entity_id: int
    label: NonEmptyString


class AssayEntity(DomainModel):
    """The assay a capability names: an ASSAY_METHOD or an ASSAY_TYPE."""

    entity_id: int
    entity_type: Literal["ASSAY_METHOD", "ASSAY_TYPE"]
    label: NonEmptyString


class AssayCapability(DomainModel):
    """One assay the workflow can process, classified by the SPLICE vocabulary.

    Built only by :mod:`nf_splice.catalogue` from a reviewed reference; never
    from free text. ``paths`` lists every path from the assay to a modality
    (entity ids, assay first), so multi-parent classifications are kept.
    """

    kind: Literal["registered_assay", "vocabulary_assay"]
    registered_code: (
        Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9_]*$")] | None
    ) = None
    assay: AssayEntity
    assay_types: tuple[VocabularyReference, ...] = ()
    modality_subtypes: tuple[VocabularyReference, ...] = ()
    modalities: tuple[VocabularyReference, ...]
    paths: tuple[tuple[int, ...], ...]

    @model_validator(mode="after")
    def validate_kind(self) -> AssayCapability:
        if (self.kind == "registered_assay") != (self.registered_code is not None):
            raise ValueError(
                "a registered_assay has a registered_code; a vocabulary_assay has none"
            )
        if not self.modalities or not self.paths:
            raise ValueError("an assay capability reaches at least one modality")
        return self

    @property
    def key(self) -> str:
        return self.registered_code or f"entity:{self.assay.entity_id}"


#: Canonical, documented order of ``pipeline`` keys in drafts and bundle.json.
PIPELINE_FIELD_ORDER = (
    "id",
    "name",
    "version",
    "engine",
    "title",
    "description",
    "long_description",
    "readme",
    "repository_url",
    "project_url",
    "release_url",
    "authors",
    "funders",
    "citation",
    "licence",
    "licence_url",
    "documentation_url",
    "support_url",
    "engine_version_min",
    "engine_versions_tested",
    "keywords",
    "pipeline_type",
    "assay_capabilities",
    "released_at",
)
#: Fields an ingestion-ready bundle must define.
REQUIRED_PIPELINE_FIELDS = ("id", "name", "version", "engine", "repository_url")


class PipelineMetadata(DomainModel):
    """Reviewed, publishable workflow identity and descriptive metadata."""

    id: PipelineId
    name: NonEmptyString
    version: NonEmptyString
    engine: Annotated[str, StringConstraints(pattern=r"^nextflow$")] = "nextflow"
    title: NonEmptyString | None = None
    description: NonEmptyString | None = None
    long_description: NonEmptyString | None = None
    readme: NonEmptyString | None = None
    repository_url: HttpUrl
    project_url: HttpUrl | None = None
    release_url: HttpUrl | None = None
    authors: tuple[Contributor, ...] = ()
    funders: tuple[Funder, ...] = ()
    citation: Citation | None = None
    licence: NonEmptyString | None = None
    licence_url: HttpUrl | None = None
    documentation_url: HttpUrl | None = None
    support_url: HttpUrl | None = None
    engine_version_min: NonEmptyString | None = None
    engine_versions_tested: NonEmptyString | None = None
    keywords: tuple[NonEmptyString, ...] = ()
    pipeline_type: NonEmptyString | None = None
    assay_capabilities: tuple[AssayCapability, ...] = ()
    released_at: (
        Annotated[
            str,
            StringConstraints(
                pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})$"
            ),
        ]
        | None
    ) = None

    @model_validator(mode="after")
    def validate_collections(self) -> PipelineMetadata:
        identities = [(item.name.casefold(), item.orcid) for item in self.authors]
        if len(identities) != len(set(identities)):
            raise ValueError("authors must not be duplicated")
        funders = [(item.name.casefold(), item.award_id) for item in self.funders]
        if len(funders) != len(set(funders)):
            raise ValueError("funders must not be duplicated")
        if len(self.keywords) != len(set(self.keywords)):
            raise ValueError("keywords must be unique")
        keys = [item.key for item in self.assay_capabilities]
        if len(keys) != len(set(keys)):
            raise ValueError("assay capabilities must not be duplicated")
        return self

    def reference(self) -> dict[str, str]:
        """Return the detached-contract identity envelope."""
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "engine": self.engine,
        }

    def ordered_document(self) -> dict[str, object]:
        """Return the JSON document in the canonical field order, nulls omitted."""
        dumped = self.model_dump(mode="json", exclude_none=True)
        return {
            key: dumped[key]
            for key in PIPELINE_FIELD_ORDER
            if key in dumped and dumped[key] not in ((), [])
        }


_PLACEHOLDER_VALUES = frozenset(
    {
        "example",
        "example-pipeline",
        "n/a",
        "none",
        "placeholder",
        "todo",
        "tbd",
        "unknown",
        "0.0.0",
        "changeme",
        "your name",
    }
)


def is_placeholder(value: str) -> bool:
    """Whether a value is a template placeholder rather than real metadata."""
    lowered = value.strip().lower()
    return (
        lowered in _PLACEHOLDER_VALUES
        or lowered.startswith("todo")
        or "example.com" in lowered
        or "example.org" in lowered
        or re.search(r"(?:^|/)example(?:-pipeline)?(?:/|$)", lowered) is not None
        or "nf-core/template" in lowered
    )
