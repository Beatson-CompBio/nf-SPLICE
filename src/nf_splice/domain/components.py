"""Reviewed software-component and container inventory models."""

from __future__ import annotations

from enum import Enum

from pydantic import Field, model_validator

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


# ---------------------------------------------------------------------------
# 0.3.0 container provenance: sources, runtime variants and distributions
# ---------------------------------------------------------------------------


class ContainerRuntime(str, Enum):
    """Runtime a container reference is selected for."""

    DOCKER = "docker"
    SINGULARITY = "singularity"
    APPTAINER = "apptainer"
    ANY = "any"


class ReferenceKind(str, Enum):
    """What a raw container reference actually denotes."""

    OCI_REGISTRY = "oci_registry"
    DOCKER_URI = "docker_uri"
    ORAS = "oras"
    HTTPS_IMAGE = "https_image"
    INSECURE_HTTP = "insecure_http"
    LOCAL_IMAGE = "local_image"
    UNRESOLVED_EXPRESSION = "unresolved_expression"
    UNSUPPORTED = "unsupported"


class ResolutionStatus(str, Enum):
    """Readiness of one container for ingestion."""

    DISCOVERED = "discovered"
    NEEDS_REVIEW = "needs_review"
    RESOLVED = "resolved"
    NEEDS_MATERIALISATION = "needs_materialisation"
    PUBLISHED = "published"
    VERIFIED = "verified"
    BLOCKED = "blocked"


class ImageFormat(str, Enum):
    """Verified static image file formats."""

    SIF = "sif"
    IMG = "img"


class ContainerSource(DomainModel):
    """One observed container reference with its provenance and condition."""

    raw: NonEmptyString
    runtime: ContainerRuntime
    kind: ReferenceKind
    location: NonEmptyString
    confidence: float = 1.0


class ContainerDistribution(DomainModel):
    """A verified, directly downloadable static image file."""

    download_uri: str = Field(pattern=r"^https://")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=1)
    filename: NonEmptyString
    format: ImageFormat
    cache_filename: NonEmptyString
    source_runtime: ContainerRuntime
    source_image_digest: str | None = Field(
        default=None, pattern=r"^sha256:[0-9a-f]{64}$"
    )


class ReviewedContainer(DomainModel):
    """A reviewed logical image with per-runtime sources and distribution."""

    id: str = Field(pattern=r"^container-[0-9a-f]{12}$")
    source_images: dict[ContainerRuntime, NonEmptyString]
    distribution: ContainerDistribution | None = None
    legacy_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_sources(self) -> ReviewedContainer:
        if not self.source_images:
            raise ValueError("a container needs at least one source image")
        if ContainerRuntime.ANY in self.source_images:
            raise ValueError("source images must name a concrete runtime")
        return self
