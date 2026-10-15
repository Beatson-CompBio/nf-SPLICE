"""Domain models for read-only pipeline repository inspection."""

from __future__ import annotations

from enum import Enum

from nf_splice.domain.base import DomainModel, Evidence, NonEmptyString


class EvidenceKind(str, Enum):
    """Repository facts that can support later authoring decisions."""

    PIPELINE_CONFIG = "pipeline_config"
    INCLUDED_CONFIG = "included_config"
    INPUT_SCHEMA = "input_schema"
    NEXTFLOW_SOURCE = "nextflow_source"
    WORKFLOW = "workflow"
    MODULE = "module"
    NATIVE_OUTPUT = "native_output"
    PUBLISHED_OUTPUT = "published_output"
    MODULE_INDEX = "module_index"
    MODULE_METADATA = "module_metadata"
    CONTAINER = "container"
    CONDA_ENVIRONMENT = "conda_environment"
    GIT_REMOTE = "git_remote"
    GIT_REVISION = "git_revision"
    GIT_TAG = "git_tag"
    RO_CRATE = "ro_crate"


class RepositoryEvidence(Evidence):
    """Detected repository evidence with a machine-readable kind."""

    kind: EvidenceKind


class TreeState(str, Enum):
    """Coarse state of the repository-root ``splice/`` tree."""

    ABSENT = "absent"
    EMPTY = "empty"
    RECOGNIZED = "recognized"
    MALFORMED = "malformed"
    UNKNOWN = "unknown"
    MIXED = "mixed"


class EntryType(str, Enum):
    """Filesystem entry type without following symbolic links."""

    FILE = "file"
    DIRECTORY = "directory"
    SYMLINK = "symlink"


class PathClassification(str, Enum):
    """Relationship of an existing path to the supported bundle shape."""

    RECOGNIZED = "recognized"
    MALFORMED = "malformed"
    UNKNOWN = "unknown"


class InspectedPath(DomainModel):
    """Classification of one path below the integration root."""

    path: NonEmptyString
    entry_type: EntryType
    classification: PathClassification
    affected_layers: tuple[NonEmptyString, ...] = ()
    detail: NonEmptyString | None = None


class UnsafeCollision(DomainModel):
    """Existing path that cannot be replaced safely without review."""

    path: NonEmptyString
    affected_layers: tuple[NonEmptyString, ...]
    reason: NonEmptyString


class SpliceTreeInspection(DomainModel):
    """Complete, read-only classification of the existing integration tree."""

    state: TreeState
    paths: tuple[InspectedPath, ...] = ()
    collisions: tuple[UnsafeCollision, ...] = ()


class RepositoryInspection(DomainModel):
    """Repository evidence and current integration-tree safety state."""

    root: NonEmptyString
    repository_revision: NonEmptyString | None = None
    evidence: tuple[RepositoryEvidence, ...] = ()
    splice_tree: SpliceTreeInspection
