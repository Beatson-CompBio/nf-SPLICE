"""Reviewed execution-profile and configuration domain models."""

from __future__ import annotations

from enum import Enum

from nf_splice.domain.base import DomainModel, NonEmptyString


class ExecutionProfileType(str, Enum):
    """Platform vocabulary for an execution profile's purpose."""

    TEST = "test"
    DEVELOPMENT = "development"
    PRODUCTION = "production"


class ExecutionEngine(str, Enum):
    """Workflow-engine vocabulary understood by the platform."""

    NEXTFLOW = "nextflow"


class ExecutionExecutor(str, Enum):
    """Nextflow executor vocabulary supported by this schema version."""

    LOCAL = "local"
    AWS_BATCH = "awsbatch"
    AZURE_BATCH = "azurebatch"
    GOOGLE_BATCH = "google-batch"
    KUBERNETES = "k8s"
    SEQERA = "seqera"
    BRIDGE = "bridge"
    FLUX = "flux"
    HTCONDOR = "condor"
    HYPERQUEUE = "hq"
    LSF = "lsf"
    MOAB = "moab"
    NQSII = "nqsii"
    OAR = "oar"
    PBS = "pbs"
    PBS_PRO = "pbspro"
    SGE = "sge"
    SLURM = "slurm"
    TCS = "tcs"


class ContainerEngine(str, Enum):
    """Container-runtime vocabulary understood by nf-splice and Nextflow."""

    APPTAINER = "apptainer"
    CHARLIECLOUD = "charliecloud"
    CONDA = "conda"
    DOCKER = "docker"
    PODMAN = "podman"
    SHIFTER = "shifter"
    SINGULARITY = "singularity"


class ExecutionProfileCandidate(DomainModel):
    """Detected profile evidence that has not yet been selected for SPLICE."""

    id: NonEmptyString
    name: NonEmptyString
    source_profile: NonEmptyString
    config_sources: tuple[NonEmptyString, ...] = ()
    executors: tuple[NonEmptyString, ...] = ()
    container_engines: tuple[NonEmptyString, ...] = ()
    unresolved_fields: tuple[NonEmptyString, ...] = ()
