"""Reviewed output catalogue values and discovery candidates."""

from __future__ import annotations

import re
from enum import Enum
from typing import Annotated

from pydantic import Field, StringConstraints, model_validator

from nf_splice.domain.authoring import DomainModel, NonEmptyString

#: Developer-chosen descriptive label: safe, non-empty free text. Scientific
#: categories and stages are never restricted to a central vocabulary.
OutputLabelText = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=r"^[^\x00-\x1f\x7f]+$",
    ),
]

#: Default category suggested for workflow-wide (job-scoped) outputs.
DEFAULT_JOB_CATEGORY = "job_report"
#: Non-binding suggestions offered by interfaces; any safe label is valid.
SUGGESTED_OUTPUT_CATEGORIES = (
    DEFAULT_JOB_CATEGORY,
    "sample_metadata",
    "aggregate_qc",
    "quality_control",
    "preprocessing",
    "alignment",
    "postprocessing",
    "coverage",
    "quantification",
    "umi",
    "reference",
)
SUGGESTED_OUTPUT_STAGES = (
    "raw",
    "trimmed",
    "filtered",
    "aligned",
    "markduplicates",
    "genomic_dedup",
    "transcriptomic_dedup",
    "sorted",
    "merged",
    "final",
)

_PATH_PLACEHOLDERS = {
    "{sample}": r"(?P<sample_id>[^/]+)",
    "{run}": r"(?P<run_id>[^/]+)",
    "{library}": r"(?P<library_id>[^/]+)",
    "{aligner}": r"(?P<aligner>[^/]+)",
    "{stage}": r"(?P<stage>[^/]+)",
    "{read}": r"(?P<read>[^/]+)",
    "{any}": r"[^/]+",
    "{anypath}": r".+",
}


def expand_output_path_pattern(pattern: str) -> str:
    """Expand controlled catalogue placeholders into named Python regex groups."""
    expanded = pattern
    for placeholder, replacement in _PATH_PLACEHOLDERS.items():
        expanded = expanded.replace(placeholder, replacement)
    unknown = re.findall(r"\{[A-Za-z_][A-Za-z0-9_]*\}", expanded)
    if unknown:
        raise ValueError(f"unknown output path placeholder {unknown[0]!r}")
    return expanded


class OutputScope(str, Enum):
    """SPLICE platform granularity that owns one output record.

    ``job`` is workflow-execution-wide, ``sample`` is one biological sample
    (or its aggregate result) and ``run`` is one platform file-level or
    acquisition-level unit belonging to a sample.
    """

    JOB = "job"
    SAMPLE = "sample"
    RUN = "run"


class LegacyOutputScope(str, Enum):
    """Scope values of nf-splice 0.1.0 contracts, read only for migration.

    Legacy ``run`` meant workflow-wide (now ``job``); legacy ``library`` meant
    per-library and becomes ``run`` only with a reviewed platform-run mapping.
    """

    RUN = "run"
    SAMPLE = "sample"
    LIBRARY = "library"


class OutputEntityType(str, Enum):
    """Physical kind of an output."""

    FILE = "file"
    DIRECTORY = "directory"


class OutputFormat(str, Enum):
    """Controlled output formats used by output review selectors."""

    HTML = "html"
    JSON = "json"
    YAML = "yaml"
    TXT = "txt"
    TSV = "tsv"
    CSV = "csv"
    LOG = "log"
    PDF = "pdf"
    PNG = "png"
    SVG = "svg"
    PARQUET = "parquet"
    BAM = "bam"
    BAI = "bai"
    CRAM = "cram"
    CRAI = "crai"
    BED = "bed"
    BIGWIG = "bigwig"
    BEDGRAPH = "bedgraph"
    GTF = "gtf"
    GFF = "gff"
    FASTA = "fasta"
    FASTQ = "fastq"
    VCF = "vcf"
    RDS = "rds"
    H5 = "h5"
    MTX = "mtx"
    ZIP = "zip"
    GZ = "gz"
    DIRECTORY = "directory"


class OutputLabel(DomainModel):
    """Optional domain-specific label retained with a reviewed output."""

    name: NonEmptyString
    value: NonEmptyString


class OutputCandidate(DomainModel):
    """One explainable output proposal created from detected evidence."""

    id: NonEmptyString
    suggested_key: NonEmptyString
    path_pattern: NonEmptyString | None = None
    source_locations: tuple[NonEmptyString, ...]
    processes: tuple[NonEmptyString, ...] = ()
    suggested_title: NonEmptyString | None = None
    suggested_description: NonEmptyString | None = None
    suggested_format: OutputFormat | None = None
    likely_scope: OutputScope | None = None
    likely_entity_type: OutputEntityType | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    conditional: bool = False
    unresolved_fields: tuple[NonEmptyString, ...]

    @model_validator(mode="after")
    def validate_collections(self) -> OutputCandidate:
        """Keep merged discovery evidence deterministic and unambiguous."""
        for values, label in (
            (self.source_locations, "source_locations"),
            (self.processes, "processes"),
            (self.unresolved_fields, "unresolved_fields"),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{label} must be unique")
        return self


class ReviewedOutput(DomainModel):
    """Complete scientific and presentation meaning for one output."""

    key: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    title: NonEmptyString
    description: NonEmptyString
    category: OutputLabelText
    formats: tuple[OutputFormat, ...]
    scopes: tuple[OutputScope, ...]
    entity_types: tuple[OutputEntityType, ...]
    path_patterns: tuple[NonEmptyString, ...]
    stage: OutputLabelText | None = None
    labels: tuple[OutputLabel, ...] = ()

    @model_validator(mode="after")
    def validate_reviewed_output(self) -> ReviewedOutput:
        """Validate uniqueness and path-pattern syntax before persistence."""
        for values, label in (
            (self.formats, "formats"),
            (self.scopes, "scopes"),
            (self.entity_types, "entity_types"),
            (self.path_patterns, "path_patterns"),
        ):
            if not values:
                raise ValueError(f"{label} must not be empty")
            if len(values) != len(set(values)):
                raise ValueError(f"{label} must be unique")
        if len(self.labels) != len({item.name for item in self.labels}):
            raise ValueError("label names must be unique")
        captures: list[set[str]] = []
        for pattern in self.path_patterns:
            if not pattern.startswith("^") or not pattern.endswith("$"):
                raise ValueError("path patterns must be anchored with ^ and $")
            try:
                compiled = re.compile(expand_output_path_pattern(pattern))
            except re.error as error:
                raise ValueError(
                    f"invalid path pattern {pattern!r}: {error}"
                ) from error
            captures.append(set(compiled.groupindex))
        self._validate_scope_bindings(captures)
        return self

    def _validate_scope_bindings(self, captures: list[set[str]]) -> None:
        """Require identifiers that let every pattern resolve its owner."""
        scopes = set(self.scopes)
        if OutputScope.RUN in scopes and not any("run_id" in item for item in captures):
            raise ValueError(
                "run-scoped outputs require a path pattern capturing the platform "
                "run identifier with {run}"
            )
        if OutputScope.SAMPLE in scopes and not any(
            "sample_id" in item for item in captures
        ):
            raise ValueError(
                "sample-scoped outputs require a path pattern capturing {sample}"
            )
        for pattern, groups in zip(self.path_patterns, captures, strict=True):
            owners = {
                OutputScope.RUN if "run_id" in groups else None,
                OutputScope.SAMPLE if "sample_id" in groups else None,
                OutputScope.JOB,
            } - {None}
            if not owners & scopes:
                raise ValueError(
                    f"path pattern {pattern!r} captures no identifier for "
                    f"scopes {sorted(item.value for item in scopes)}"
                )
