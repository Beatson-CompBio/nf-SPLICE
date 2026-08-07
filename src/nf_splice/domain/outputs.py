"""Reviewed output catalogue values and discovery candidates."""

from __future__ import annotations

import re
from enum import Enum

from pydantic import Field, model_validator

from nf_splice.domain.authoring import DomainModel, NonEmptyString


class OutputScope(str, Enum):
    """Supported scientific scope for one output."""

    RUN = "run"
    SAMPLE = "sample"
    LIBRARY = "library"


class OutputEntityType(str, Enum):
    """Physical kind of an output."""

    FILE = "file"
    DIRECTORY = "directory"


class OutputCategory(str, Enum):
    """Controlled presentation categories supported by the platform contract."""

    RUN_REPORT = "run_report"
    SAMPLE_METADATA = "sample_metadata"
    AGGREGATE_QC = "aggregate_qc"
    QUALITY_CONTROL = "quality_control"
    PREPROCESSING = "preprocessing"
    ALIGNMENT = "alignment"
    POSTPROCESSING = "postprocessing"
    COVERAGE = "coverage"
    QUANTIFICATION = "quantification"
    UMI = "umi"
    REFERENCE = "reference"


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


class OutputStage(str, Enum):
    """Optional controlled pipeline stage."""

    RAW = "raw"
    TRIMMED = "trimmed"
    FILTERED = "filtered"
    ALIGNED = "aligned"
    MARKDUPLICATES = "markduplicates"
    GENOMIC_DEDUP = "genomic_dedup"
    TRANSCRIPTOMIC_DEDUP = "transcriptomic_dedup"
    SORTED = "sorted"
    MERGED = "merged"
    FINAL = "final"


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
    category: OutputCategory
    formats: tuple[OutputFormat, ...]
    scopes: tuple[OutputScope, ...]
    entity_types: tuple[OutputEntityType, ...]
    path_patterns: tuple[NonEmptyString, ...]
    stage: OutputStage | None = None
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
        for pattern in self.path_patterns:
            if not pattern.startswith("^") or not pattern.endswith("$"):
                raise ValueError("path patterns must be anchored with ^ and $")
            try:
                re.compile(pattern)
            except re.error as error:
                raise ValueError(
                    f"invalid path pattern {pattern!r}: {error}"
                ) from error
        return self
