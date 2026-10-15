"""Generate and validate the one ``analysis_output.json`` of a completed job.

For 0.3.0 bundles the classification catalogue is read only from
``outputs.schema.json`` -> ``x-output-catalog``; the same file validates the
generated document. ``outputs.yaml`` is never consulted for a 0.3.0 contract.
Bundles produced by nf-splice 0.1.0 are read through an explicit,
version-gated legacy path that keeps their original output semantics.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import yaml  # type: ignore[import-untyped]

from nf_splice.contracts import OUTPUTS_FAMILY, validate_contract_document
from nf_splice.domain import expand_output_path_pattern
from nf_splice.validators import (
    AnalysisOutputValidationReport,
    validate_analysis_output,
)

ANALYSIS_OUTPUT_FILENAME = "analysis_output.json"

_PATH_KEYS = ("path", "target", "publishedPath", "published_path", "file")
#: Top-level job identity and context fields of a 0.3.0 analysis output.
_JOB_FIELDS = ("job_id_short", "job_id_long", "config_profile", "execution_timestamp")
_JOB_METADATA_FIELDS = ("engine", "engine_execution_id", "nextflow", "annotations")
#: Top-level fields of the legacy (0.1.0) per-workflow-execution document.
_LEGACY_RUN_FIELDS = (
    "job_id_short",
    "job_id_long",
    "platform_run_id",
    "workflow_run_id",
    "nextflow_session_id",
    "nextflow_run_name",
    "config_profile",
    "execution_timestamp",
)
CONTRACT_0_3_0 = "0.3.0"
CONTRACT_LEGACY = "legacy-0.1.0"
_FORMAT_SUFFIXES = {
    ".html": "html",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".txt": "txt",
    ".tsv": "tsv",
    ".csv": "csv",
    ".log": "log",
    ".pdf": "pdf",
    ".png": "png",
    ".svg": "svg",
    ".parquet": "parquet",
    ".bam": "bam",
    ".bai": "bai",
    ".cram": "cram",
    ".crai": "crai",
    ".bed": "bed",
    ".bw": "bigwig",
    ".bigwig": "bigwig",
    ".bedgraph": "bedgraph",
    ".gtf": "gtf",
    ".gff": "gff",
    ".fa": "fasta",
    ".fasta": "fasta",
    ".fq": "fastq",
    ".fastq": "fastq",
    ".vcf": "vcf",
    ".rds": "rds",
    ".h5": "h5",
    ".mtx": "mtx",
    ".zip": "zip",
    ".gz": "gz",
}


class AnalysisOutputError(ValueError):
    """Raised when runtime evidence cannot produce a valid analysis output."""


@dataclass(frozen=True, slots=True)
class AnalysisOutputResult:
    """Generated runtime inventory, validation result, and unmatched evidence."""

    document: dict[str, Any]
    content: str
    validation: AnalysisOutputValidationReport
    unclassified: tuple[str, ...]
    path: Path | None


@dataclass(frozen=True, slots=True)
class _Entry:
    path: str
    is_directory: bool


def _load_mapping(path: Path, label: str) -> dict[str, Any]:
    try:
        loaded: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise AnalysisOutputError(f"invalid {label} JSON: {error}") from error
    if not isinstance(loaded, dict):
        raise AnalysisOutputError(f"{label} must contain a JSON object")
    return loaded


@dataclass(frozen=True, slots=True)
class OutputCatalogue:
    """Runtime view of one static output contract and its semantics."""

    semantics: str
    schema: dict[str, Any]
    schema_version: str
    schema_id: str
    pipeline: dict[str, Any]
    output_types: tuple[dict[str, Any], ...]

    @property
    def legacy(self) -> bool:
        return self.semantics == CONTRACT_LEGACY


_OUTPUT_TYPE_KEYS = (
    "key",
    "category",
    "scope",
    "entity_type",
    "format",
    "path_patterns",
)


def _complete_output_types(value: object) -> tuple[dict[str, Any], ...] | None:
    if not isinstance(value, list) or not value:
        return None
    if not all(
        isinstance(item, dict) and all(key in item for key in _OUTPUT_TYPE_KEYS)
        for item in value
    ):
        return None
    for item in value:
        for pattern in item["path_patterns"]:
            try:
                re.compile(expand_output_path_pattern(str(pattern)))
            except (re.error, ValueError) as error:
                raise AnalysisOutputError(
                    f"x-output-catalog output {item['key']!r} has invalid pattern "
                    f"{pattern!r}: {error}"
                ) from error
    return tuple(value)


def _const(schema: Mapping[str, Any], name: str) -> Any:
    properties = schema.get("properties", {})
    item = properties.get(name, {}) if isinstance(properties, dict) else {}
    return item.get("const") if isinstance(item, dict) else None


def _legacy_bundle_version(root: Path) -> str | None:
    bundle = root / "splice" / "bundle.json"
    if not bundle.is_file():
        return None
    try:
        loaded = json.loads(bundle.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    version = loaded.get("schema_version") if isinstance(loaded, dict) else None
    return version if isinstance(version, str) else None


def _legacy_catalogue(root: Path, schema: dict[str, Any]) -> OutputCatalogue:
    bundle_version = _legacy_bundle_version(root)
    if bundle_version not in {None, "1.0"}:
        raise AnalysisOutputError(
            "outputs.schema.json has no x-splice-contract but bundle.json declares "
            f"schema_version {bundle_version!r}; refusing to guess legacy semantics"
        )
    pipeline = {
        "name": _const(schema, "pipeline_name"),
        "version": _const(schema, "pipeline_version"),
        "repository_url": _const(schema, "repository_url"),
    }
    catalog = schema.get("x-output-catalog")
    output_types = _complete_output_types(
        catalog.get("output_types") if isinstance(catalog, dict) else None
    )
    schema_version = _const(schema, "analysis_output_schema_version")
    if output_types is None:
        catalogue_path = root / "splice" / "outputs.yaml"
        try:
            loaded: object = yaml.safe_load(catalogue_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError) as error:
            raise AnalysisOutputError(
                f"cannot load legacy output catalogue: {error}"
            ) from error
        if (
            not isinstance(loaded, dict)
            or loaded.get("vocabulary_version") != "1.0.0"
            or "catalogue_format_version" in loaded
        ):
            raise AnalysisOutputError(
                "legacy output catalogue outputs.yaml is not a recognised 0.1.0 "
                "catalogue (vocabulary_version 1.0.0)"
            )
        output_types = _complete_output_types(loaded.get("outputs"))
        if output_types is None:
            raise AnalysisOutputError("legacy output catalogue has incomplete outputs")
        pipeline = dict(loaded.get("pipeline") or pipeline)
        schema_version = loaded.get("schema_version", schema_version)
    if not all(pipeline.get(key) for key in ("name", "version")) or not schema_version:
        raise AnalysisOutputError("legacy output contract lacks pipeline identity")
    return OutputCatalogue(
        semantics=CONTRACT_LEGACY,
        schema=schema,
        schema_version=str(schema_version),
        schema_id=str(schema["$id"]),
        pipeline=pipeline,
        output_types=output_types,
    )


def load_output_catalogue(repository_root: str | Path) -> OutputCatalogue:
    """Load the runtime catalogue from ``outputs.schema.json`` (no YAML for 0.3.0).

    A 0.3.0 contract (declaring ``x-splice-contract``) must be complete and
    valid; it is never silently replaced by ``outputs.yaml``. Contracts
    without the declaration are accepted only as recognised 0.1.0 legacy
    contracts, whose catalogue is the legacy embedded extension or, failing
    that, the version-gated legacy ``outputs.yaml``.
    """
    root = Path(repository_root).resolve()
    schema = _load_mapping(root / "splice" / "outputs.schema.json", "output schema")
    if "x-splice-contract" not in schema:
        return _legacy_catalogue(root, schema)
    report = validate_contract_document(schema, OUTPUTS_FAMILY)
    if not report.valid:
        details = "; ".join(
            f"{item.json_pointer or '/'}: {item.message}" for item in report.issues[:5]
        )
        raise AnalysisOutputError(
            f"outputs.schema.json is not a valid {OUTPUTS_FAMILY} contract; repair "
            f"and republish it (no YAML fallback is used): {details}"
        )
    catalog = schema["x-output-catalog"]
    output_types = _complete_output_types(catalog["output_types"])
    if output_types is None:
        raise AnalysisOutputError("x-output-catalog output_types are incomplete")
    pipeline = dict(catalog["pipeline"])
    release_url = None
    properties = schema.get("properties", {})
    if isinstance(properties, dict):
        release_url = properties.get("release_url", {}).get("const")
    if release_url:
        pipeline["release_url"] = release_url
    return OutputCatalogue(
        semantics=CONTRACT_0_3_0,
        schema=schema,
        schema_version=str(catalog["analysis_output_schema_version"]),
        schema_id=str(schema["$id"]),
        pipeline=pipeline,
        output_types=output_types,
    )


def _safe_relative_path(value: object) -> str:
    raw = str(value).replace("\\", "/").removeprefix("./")
    pure = PurePosixPath(raw)
    if not raw or pure.is_absolute() or ".." in pure.parts or "//" in raw:
        raise AnalysisOutputError(
            f"runtime output path is not safely relative: {raw!r}"
        )
    return pure.as_posix()


def _walk_publish_directory(path: Path) -> list[_Entry]:
    entries = []
    for current, directory_names, file_names in os.walk(path, followlinks=False):
        directory_names.sort()
        file_names.sort()
        current_path = Path(current)
        relative_directory = current_path.relative_to(path)
        for name in directory_names:
            child = current_path / name
            relative = (relative_directory / name).as_posix()
            if child.is_symlink():
                raise AnalysisOutputError(
                    f"completed publish directory contains a symlink: {relative}"
                )
            entries.append(_Entry(relative, True))
        for name in file_names:
            child = current_path / name
            relative = (relative_directory / name).as_posix()
            if child.is_symlink():
                raise AnalysisOutputError(
                    f"completed publish directory contains a symlink: {relative}"
                )
            if relative != ANALYSIS_OUTPUT_FILENAME:
                entries.append(_Entry(relative, False))
    return entries


def _records_from_index(path: Path) -> list[_Entry]:
    suffix = path.suffix.lower()
    text = path.read_text(encoding="utf-8")
    records: object
    if suffix == ".json":
        records = json.loads(text)
    elif suffix in {".yaml", ".yml"}:
        records = yaml.safe_load(text)
    elif suffix in {".csv", ".tsv"}:
        delimiter = "\t" if suffix == ".tsv" else ","
        records = list(csv.DictReader(text.splitlines(), delimiter=delimiter))
    else:
        raise AnalysisOutputError(f"unsupported native output index format: {suffix}")
    if isinstance(records, dict):
        records = records.get("outputs", records.get("files", []))
    if not isinstance(records, list):
        raise AnalysisOutputError("native output index must contain a record list")
    entries = []
    for record in records:
        if not isinstance(record, dict):
            continue
        value = next((record.get(key) for key in _PATH_KEYS if record.get(key)), None)
        if value is None:
            continue
        entity = str(record.get("type") or record.get("entity_type") or "").lower()
        entries.append(
            _Entry(_safe_relative_path(value), entity in {"dir", "directory"})
        )
    return entries


def _entries_from_tree(path: Path) -> list[_Entry]:
    blocks: dict[str, list[str]] = {}
    current = "."
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.endswith(":"):
            current = line[:-1].removeprefix("./") or "."
            blocks.setdefault(current, [])
        else:
            blocks.setdefault(current, []).append(line)
    directories = {item for item in blocks if item != "."}
    entries = []
    for directory, names in blocks.items():
        for name in names:
            relative = name if directory == "." else f"{directory}/{name}"
            safe = _safe_relative_path(relative)
            entries.append(_Entry(safe, safe in directories))
    return entries


def _runtime_entries(
    *,
    publish_directory: Path | None,
    native_output_index: Path | None,
    output_tree: Path | None,
) -> tuple[list[_Entry], Path | None]:
    supplied = [
        item
        for item in (publish_directory, native_output_index, output_tree)
        if item is not None
    ]
    if len(supplied) != 1:
        raise AnalysisOutputError(
            "provide exactly one completed publish directory, native output index, "
            "or output tree listing"
        )
    if publish_directory is not None:
        if not publish_directory.is_dir():
            raise AnalysisOutputError(
                f"completed publish directory does not exist: {publish_directory}"
            )
        return _walk_publish_directory(publish_directory), publish_directory
    source = native_output_index or output_tree
    if source is None or not source.is_file():
        raise AnalysisOutputError(f"runtime output evidence does not exist: {source}")
    if native_output_index is not None:
        return _records_from_index(source), None
    return _entries_from_tree(source), None


def _specificity(output: Mapping[str, Any]) -> tuple[bool, int, str]:
    patterns = [str(item) for item in output.get("path_patterns", [])]
    return (
        any(".+" in item or ".*" in item for item in patterns),
        -max(map(len, patterns)),
        str(output["key"]),
    )


def _format_for(path: str, allowed: list[str], is_directory: bool) -> str:
    if is_directory and "directory" in allowed:
        return "directory"
    lowered = path.lower()
    for suffix, name in sorted(
        _FORMAT_SUFFIXES.items(), key=lambda item: len(item[0]), reverse=True
    ):
        if lowered.endswith(suffix) and name in allowed:
            return name
    return allowed[0]


@dataclass(frozen=True, slots=True)
class SampleIndex:
    """Known samples and, when supplied, each platform run's parent sample."""

    samples: frozenset[str]
    run_parents: Mapping[str, str]


def _compiled_outputs(
    outputs: tuple[dict[str, Any], ...],
) -> list[tuple[re.Pattern[str], Mapping[str, Any]]]:
    compiled: list[tuple[re.Pattern[str], Mapping[str, Any]]] = []
    for typed_output in sorted(outputs, key=_specificity):
        for pattern in typed_output.get("path_patterns", []):
            compiled.append(
                (re.compile(expand_output_path_pattern(str(pattern))), typed_output)
            )
    return compiled


def _matches(
    outputs: tuple[dict[str, Any], ...], entries: list[_Entry]
) -> tuple[list[tuple[_Entry, re.Match[str], Mapping[str, Any]]], tuple[str, ...]]:
    compiled = _compiled_outputs(outputs)
    directory_output_prefixes = []
    for entry in entries:
        if not entry.is_directory:
            continue
        for pattern, compiled_output in compiled:
            if (
                pattern.match(entry.path)
                and "directory" in compiled_output["entity_type"]
            ):
                directory_output_prefixes.append(f"{entry.path}/")
                break
    all_paths = {item.path for item in entries}
    matched = []
    unclassified = []
    for entry in sorted(entries, key=lambda item: item.path):
        if any(entry.path.startswith(prefix) for prefix in directory_output_prefixes):
            continue
        entity = "directory" if entry.is_directory else "file"
        found = next(
            (
                (match, candidate)
                for pattern, candidate in compiled
                if (match := pattern.match(entry.path))
                and entity in candidate["entity_type"]
            ),
            None,
        )
        if found is None:
            is_container = entry.is_directory and any(
                item != entry.path and item.startswith(f"{entry.path}/")
                for item in all_paths
            )
            if not is_container:
                unclassified.append(entry.path)
            continue
        matched.append((entry, found[0], found[1]))
    return matched, tuple(unclassified)


def _base_record(
    entry: _Entry, matched_output: Mapping[str, Any], scope: str
) -> dict[str, object]:
    return {
        "path": entry.path,
        "category": matched_output["category"],
        "output_type": matched_output["key"],
        "scope": scope,
        "entity_type": "directory" if entry.is_directory else "file",
        "format": _format_for(
            entry.path, list(matched_output["format"]), entry.is_directory
        ),
    }


def _descriptive_fields(
    record: dict[str, object],
    groups: Mapping[str, str | None],
    output: Mapping[str, Any],
) -> None:
    for name in ("read", "aligner"):
        if groups.get(name):
            record[name] = groups[name]
    if groups.get("stage"):
        record["stage"] = groups["stage"]
    elif output.get("stage"):
        record["stage"] = output["stage"]
    if output.get("labels"):
        record["labels"] = output["labels"]


def _classify(
    outputs: tuple[dict[str, Any], ...],
    entries: list[_Entry],
    index: SampleIndex | None,
) -> tuple[list[dict[str, object]], tuple[str, ...]]:
    """Classify job records at job, sample or run granularity (0.3.0)."""
    matched, unclassified = _matches(outputs, entries)
    files = []
    for entry, match, output in matched:
        scopes = [str(item) for item in output["scope"]]
        groups = match.groupdict()
        run_id = groups.get("run_id")
        sample_id = groups.get("sample_id")
        if run_id and "run" in scopes:
            scope = "run"
        elif sample_id and "sample" in scopes:
            scope = "sample"
        elif "job" in scopes:
            scope = "job"
        else:
            raise AnalysisOutputError(
                f"output path {entry.path!r} matches {output['key']!r} but captures "
                f"no identifier for its scopes {scopes}"
            )
        record = _base_record(entry, output, scope)
        if scope == "run":
            assert run_id is not None
            parent = index.run_parents.get(run_id) if index is not None else None
            if sample_id and parent and parent != sample_id:
                raise AnalysisOutputError(
                    f"run {run_id!r} at {entry.path!r} belongs to sample {parent!r} "
                    f"in the sample metadata, not {sample_id!r}"
                )
            sample_id = sample_id or parent
            if not sample_id:
                raise AnalysisOutputError(
                    f"run-scoped output {entry.path!r} has unresolved parent sample "
                    f"for run {run_id!r}; capture {{sample}} or supply sample "
                    "metadata with run_id and sample columns"
                )
            record["run_id"] = run_id
        if scope in {"run", "sample"}:
            assert sample_id is not None
            if index is not None and sample_id not in index.samples:
                raise AnalysisOutputError(
                    f"output path {entry.path!r} captures unknown sample {sample_id!r}"
                )
            record["sample_id"] = sample_id
        if groups.get("library_id"):
            record["library_id"] = groups["library_id"]
        _descriptive_fields(record, groups, output)
        files.append(record)
    return files, unclassified


def _classify_legacy(
    outputs: tuple[dict[str, Any], ...],
    entries: list[_Entry],
    index: SampleIndex | None,
) -> tuple[list[dict[str, object]], tuple[str, ...]]:
    """Classify with nf-splice 0.1.0 semantics for a legacy static contract."""
    matched, unclassified = _matches(outputs, entries)
    files = []
    for entry, match, output in matched:
        scope = str(output["scope"][0])
        groups = match.groupdict()
        record = _base_record(entry, output, scope)
        if scope == "sample":
            sample_id = groups.get("sample_id")
            if not sample_id:
                raise AnalysisOutputError(
                    f"sample-scoped output {output['key']!r} does not capture sample_id"
                )
            if index is not None and sample_id not in index.samples:
                raise AnalysisOutputError(
                    f"output path {entry.path!r} captures unknown sample {sample_id!r}"
                )
            record["sample_id"] = sample_id
        if scope == "library":
            library_id = groups.get("library_id")
            if not library_id:
                raise AnalysisOutputError(
                    f"library-scoped output {output['key']!r} does not capture "
                    "library_id"
                )
            record["library_id"] = library_id
        _descriptive_fields(record, groups, output)
        files.append(record)
    return files, unclassified


def _read_sample_index(path: Path | None) -> SampleIndex | None:
    if path is None:
        return None
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            return SampleIndex(frozenset(), {})
        lowered = {item.lower(): item for item in reader.fieldnames}
        sample_column = next(
            (
                lowered[name]
                for name in ("sample", "sample_id", "sampleid", "id", "name")
                if name in lowered
            ),
            reader.fieldnames[0],
        )
        run_column = next(
            (lowered[name] for name in ("run_id", "run", "runid") if name in lowered),
            None,
        )
        samples: set[str] = set()
        parents: dict[str, str] = {}
        for row in reader:
            sample = str(row.get(sample_column) or "").strip()
            if not sample:
                continue
            samples.add(sample)
            if run_column is None:
                continue
            run = str(row.get(run_column) or "").strip()
            if not run:
                continue
            if parents.get(run, sample) != sample:
                raise AnalysisOutputError(
                    f"sample metadata assigns run {run!r} to more than one sample"
                )
            parents[run] = sample
    return SampleIndex(frozenset(samples), parents)


def _checksum(path: Path, algorithm: str) -> str:
    try:
        digest = hashlib.new(algorithm)
    except ValueError as error:
        raise AnalysisOutputError(
            f"unsupported checksum algorithm {algorithm!r}"
        ) from error
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def legacy_run_metadata_to_job_metadata(
    run_metadata: Mapping[str, Any],
) -> dict[str, Any]:
    """Convert deprecated ``--run-metadata`` input into job metadata.

    Legacy keys described the whole workflow execution, which is a SPLICE job.
    ``platform_run_id`` cannot be converted safely: it is neither the job nor a
    file-level platform run, so it requires human clarification.
    """
    if "platform_run_id" in run_metadata:
        raise AnalysisOutputError(
            "legacy platform_run_id is ambiguous in 0.3.0 (a job is not a platform "
            "run); supply job_id_short/job_id_long and engine metadata explicitly"
        )
    converted: dict[str, Any] = {
        key: run_metadata[key]
        for key in _JOB_FIELDS
        if run_metadata.get(key) is not None
    }
    job: dict[str, Any] = {}
    nextflow: dict[str, Any] = {}
    if run_metadata.get("workflow_run_id") is not None:
        job["engine_execution_id"] = run_metadata["workflow_run_id"]
    if run_metadata.get("nextflow_session_id") is not None:
        nextflow["session_id"] = run_metadata["nextflow_session_id"]
    if run_metadata.get("nextflow_run_name") is not None:
        nextflow["run_name"] = run_metadata["nextflow_run_name"]
    if nextflow:
        job["nextflow"] = nextflow
    if job:
        job["engine"] = "nextflow"
    annotations = {
        key: value
        for key, value in run_metadata.items()
        if key not in (*_LEGACY_RUN_FIELDS, "run_metadata") and value is not None
    }
    nested = run_metadata.get("run_metadata")
    if nested is not None and not isinstance(nested, dict):
        raise AnalysisOutputError("run_metadata.run_metadata must be an object")
    if isinstance(nested, dict):
        annotations = {**nested, **annotations}
    if annotations:
        job["annotations"] = dict(sorted(annotations.items()))
    if job:
        converted["job_metadata"] = job
    return converted


def _job_document(job_metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    supplied = dict(job_metadata or {})
    unknown = sorted(set(supplied) - {*_JOB_FIELDS, "job_metadata"})
    if unknown:
        raise AnalysisOutputError(
            f"unsupported job metadata field(s): {', '.join(unknown)}"
        )
    document = {key: supplied[key] for key in _JOB_FIELDS if supplied.get(key)}
    nested = supplied.get("job_metadata")
    if nested is not None:
        if not isinstance(nested, dict):
            raise AnalysisOutputError("job_metadata must be an object")
        unknown = sorted(set(nested) - set(_JOB_METADATA_FIELDS))
        if unknown:
            raise AnalysisOutputError(
                f"unsupported job_metadata field(s): {', '.join(unknown)}; put "
                "free-form values under job_metadata.annotations"
            )
        if nested:
            document["job_metadata"] = {
                key: nested[key] for key in _JOB_METADATA_FIELDS if key in nested
            }
    if not document.get("job_id_short") and not document.get("job_id_long"):
        raise AnalysisOutputError(
            "job identity is required: supply job_id_short or job_id_long with "
            "--job-metadata"
        )
    return document


def _metadata(
    catalogue: OutputCatalogue,
    job_metadata: Mapping[str, Any] | None,
    publish_directory: Path | None,
) -> dict[str, Any]:
    pipeline = catalogue.pipeline
    metadata: dict[str, Any] = {
        "analysis_output_schema_version": catalogue.schema_version,
        "schema_id": catalogue.schema_id,
        "pipeline_name": pipeline["name"],
        "pipeline_version": pipeline["version"],
        "repository_url": pipeline["repository_url"],
    }
    if pipeline.get("release_url"):
        metadata["release_url"] = pipeline["release_url"]
    job = _job_document(job_metadata)
    for key in ("job_id_short", "job_id_long", "job_metadata", "config_profile"):
        if key in job:
            metadata[key] = job[key]
    if publish_directory is not None:
        metadata["publish_directory"] = str(publish_directory)
    if "execution_timestamp" in job:
        metadata["execution_timestamp"] = job["execution_timestamp"]
    return metadata


def _legacy_metadata(
    catalogue: OutputCatalogue,
    job_metadata: Mapping[str, Any] | None,
    publish_directory: Path | None,
) -> dict[str, Any]:
    """Build the 0.1.0 per-workflow-execution envelope for a legacy contract."""
    pipeline = catalogue.pipeline
    metadata: dict[str, Any] = {
        "analysis_output_schema_version": catalogue.schema_version,
        "schema_id": catalogue.schema_id,
        "pipeline_name": pipeline["name"],
        "pipeline_version": pipeline["version"],
        "repository_url": pipeline["repository_url"],
    }
    if pipeline.get("release_url"):
        metadata["release_url"] = pipeline["release_url"]
    if publish_directory is not None:
        metadata["publish_directory"] = str(publish_directory)
    job = dict(job_metadata or {})
    nested = job.get("job_metadata") or {}
    legacy = {key: job[key] for key in _JOB_FIELDS if job.get(key) is not None}
    if nested.get("engine_execution_id") is not None:
        legacy["workflow_run_id"] = nested["engine_execution_id"]
    nextflow = nested.get("nextflow") or {}
    if nextflow.get("session_id") is not None:
        legacy["nextflow_session_id"] = nextflow["session_id"]
    if nextflow.get("run_name") is not None:
        legacy["nextflow_run_name"] = nextflow["run_name"]
    for key in _LEGACY_RUN_FIELDS:
        if key in legacy:
            metadata[key] = legacy[key]
    if nested.get("annotations"):
        metadata["run_metadata"] = dict(sorted(nested["annotations"].items()))
    return metadata


def _write_atomic(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.nf-splice.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def generate_analysis_output(
    repository_root: str | Path,
    *,
    publish_directory: str | Path | None = None,
    native_output_index: str | Path | None = None,
    output_tree: str | Path | None = None,
    job_metadata: Mapping[str, Any] | None = None,
    run_metadata: Mapping[str, Any] | None = None,
    sample_metadata: str | Path | None = None,
    checksum_algorithm: str | None = None,
    allow_unclassified: bool = False,
    output_directory: str | Path | None = None,
) -> AnalysisOutputResult:
    """Generate, validate, and optionally write one completed job's inventory.

    ``run_metadata`` is the deprecated 0.1.0 input and is converted with
    :func:`legacy_run_metadata_to_job_metadata`; supply at most one of the two.
    """
    if job_metadata is not None and run_metadata is not None:
        raise AnalysisOutputError(
            "supply job metadata or legacy run metadata, not both"
        )
    if run_metadata is not None:
        job_metadata = legacy_run_metadata_to_job_metadata(run_metadata)
    root = Path(repository_root).resolve()
    catalogue = load_output_catalogue(root)
    entries, live_publish_directory = _runtime_entries(
        publish_directory=Path(publish_directory).resolve()
        if publish_directory is not None
        else None,
        native_output_index=Path(native_output_index).resolve()
        if native_output_index is not None
        else None,
        output_tree=Path(output_tree).resolve() if output_tree is not None else None,
    )
    index = _read_sample_index(
        Path(sample_metadata).resolve() if sample_metadata is not None else None
    )
    classify = _classify_legacy if catalogue.legacy else _classify
    files, unclassified = classify(catalogue.output_types, entries, index)
    if unclassified and not allow_unclassified:
        raise AnalysisOutputError(
            f"{len(unclassified)} produced path(s) are not in the reviewed output "
            "contract: " + ", ".join(unclassified)
        )
    if checksum_algorithm is not None:
        if live_publish_directory is None:
            raise AnalysisOutputError(
                "checksums require a completed publish directory as runtime evidence"
            )
        for record in files:
            path = live_publish_directory / str(record["path"])
            if path.is_file():
                record["size_bytes"] = path.stat().st_size
                record["checksum"] = _checksum(path, checksum_algorithm)
                record["checksum_algorithm"] = checksum_algorithm
    build_metadata = _legacy_metadata if catalogue.legacy else _metadata
    document = build_metadata(catalogue, job_metadata, live_publish_directory)
    document["files"] = files
    validation = validate_analysis_output(document, catalogue.schema)
    if not validation.valid:
        details = "; ".join(
            f"{item.json_pointer or '/'}: {item.message}" for item in validation.issues
        )
        raise AnalysisOutputError(
            f"generated analysis_output.json is invalid: {details}"
        )
    content = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    output_path = None
    if output_directory is not None:
        directory = Path(output_directory).resolve()
        if not directory.is_dir():
            raise AnalysisOutputError(f"output directory does not exist: {directory}")
        output_path = directory / ANALYSIS_OUTPUT_FILENAME
        _write_atomic(output_path, content)
    return AnalysisOutputResult(
        document=document,
        content=content,
        validation=validation,
        unclassified=unclassified,
        path=output_path,
    )


def load_and_validate_analysis_output(
    repository_root: str | Path, analysis_output: str | Path
) -> AnalysisOutputValidationReport:
    """Validate an existing analysis_output.json against the static contract."""
    catalogue = load_output_catalogue(Path(repository_root).resolve())
    document = _load_mapping(Path(analysis_output).resolve(), "analysis output")
    return validate_analysis_output(document, catalogue.schema)
