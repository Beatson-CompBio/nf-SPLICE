"""Generate and validate one completed run's analysis_output.json."""

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

from nf_splice.domain import expand_output_path_pattern
from nf_splice.validators import (
    AnalysisOutputValidationReport,
    validate_analysis_output,
)

ANALYSIS_OUTPUT_FILENAME = "analysis_output.json"

_PATH_KEYS = ("path", "target", "publishedPath", "published_path", "file")
_RUN_FIELDS = (
    "job_id_short",
    "job_id_long",
    "platform_run_id",
    "workflow_run_id",
    "nextflow_session_id",
    "nextflow_run_name",
    "config_profile",
    "execution_timestamp",
)
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


def _load_contracts(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    catalogue_path = root / "splice" / "outputs.yaml"
    schema_path = root / "splice" / "outputs.schema.json"
    try:
        catalogue: object = yaml.safe_load(catalogue_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise AnalysisOutputError(f"cannot load output catalogue: {error}") from error
    if not isinstance(catalogue, dict) or not isinstance(
        catalogue.get("outputs"), list
    ):
        raise AnalysisOutputError("output catalogue must contain an outputs list")
    return catalogue, _load_mapping(schema_path, "output schema")


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


def _classify(
    outputs: list[object], entries: list[_Entry], sample_ids: set[str] | None
) -> tuple[list[dict[str, object]], tuple[str, ...]]:
    compiled: list[tuple[re.Pattern[str], Mapping[str, Any]]] = []
    typed_outputs = [item for item in outputs if isinstance(item, dict)]
    for typed_output in sorted(typed_outputs, key=_specificity):
        for pattern in typed_output.get("path_patterns", []):
            compiled.append(
                (re.compile(expand_output_path_pattern(str(pattern))), typed_output)
            )

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
    files = []
    unclassified = []
    for entry in sorted(entries, key=lambda item: item.path):
        if any(entry.path.startswith(prefix) for prefix in directory_output_prefixes):
            continue
        match: re.Match[str] | None = None
        matched_output: Mapping[str, Any] | None = None
        entity = "directory" if entry.is_directory else "file"
        for pattern, candidate in compiled:
            found = pattern.match(entry.path)
            if found and entity in candidate["entity_type"]:
                match, matched_output = found, candidate
                break
        if matched_output is None or match is None:
            is_container = entry.is_directory and any(
                item != entry.path and item.startswith(f"{entry.path}/")
                for item in all_paths
            )
            if not is_container:
                unclassified.append(entry.path)
            continue
        scopes = [str(item) for item in matched_output["scope"]]
        groups = match.groupdict()
        scope = scopes[0]
        record: dict[str, object] = {
            "path": entry.path,
            "category": matched_output["category"],
            "output_type": matched_output["key"],
            "scope": scope,
            "entity_type": entity,
            "format": _format_for(
                entry.path, list(matched_output["format"]), entry.is_directory
            ),
        }
        if scope == "sample":
            sample_id = groups.get("sample_id")
            if not sample_id:
                raise AnalysisOutputError(
                    f"sample-scoped output {matched_output['key']!r} does not "
                    "capture sample_id"
                )
            if sample_ids is not None and sample_id not in sample_ids:
                raise AnalysisOutputError(
                    f"output path {entry.path!r} captures unknown sample {sample_id!r}"
                )
            record["sample_id"] = sample_id
        if scope == "library":
            library_id = groups.get("library_id")
            if not library_id:
                raise AnalysisOutputError(
                    f"library-scoped output {matched_output['key']!r} does not "
                    "capture library_id"
                )
            record["library_id"] = library_id
        if groups.get("read"):
            record["read"] = groups["read"]
        if groups.get("aligner"):
            record["aligner"] = groups["aligner"]
        if groups.get("stage"):
            record["stage"] = groups["stage"]
        elif matched_output.get("stage"):
            record["stage"] = matched_output["stage"]
        if matched_output.get("labels"):
            record["labels"] = matched_output["labels"]
        files.append(record)
    return files, tuple(unclassified)


def _read_sample_ids(path: Path | None) -> set[str] | None:
    if path is None:
        return None
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            return set()
        lowered = {item.lower(): item for item in reader.fieldnames}
        column = next(
            (
                lowered[name]
                for name in ("sample", "sample_id", "sampleid", "id", "name")
                if name in lowered
            ),
            reader.fieldnames[0],
        )
        return {
            str(row[column]).strip()
            for row in reader
            if row.get(column) and str(row[column]).strip()
        }


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


def _metadata(
    catalogue: Mapping[str, Any],
    schema: Mapping[str, Any],
    run_metadata: Mapping[str, Any] | None,
    publish_directory: Path | None,
) -> dict[str, Any]:
    pipeline = catalogue["pipeline"]
    metadata: dict[str, Any] = {
        "analysis_output_schema_version": catalogue["schema_version"],
        "schema_id": schema["$id"],
        "pipeline_name": pipeline["name"],
        "pipeline_version": pipeline["version"],
        "repository_url": pipeline["repository_url"],
    }
    if pipeline.get("release_url"):
        metadata["release_url"] = pipeline["release_url"]
    if publish_directory is not None:
        metadata["publish_directory"] = str(publish_directory)
    if run_metadata:
        for key in _RUN_FIELDS:
            if run_metadata.get(key) is not None:
                metadata[key] = run_metadata[key]
        nested = {
            key: value
            for key, value in run_metadata.items()
            if key not in _RUN_FIELDS and key != "run_metadata" and value is not None
        }
        supplied_nested = run_metadata.get("run_metadata")
        if supplied_nested is not None and not isinstance(supplied_nested, dict):
            raise AnalysisOutputError("run_metadata.run_metadata must be an object")
        if isinstance(supplied_nested, dict):
            nested = {**supplied_nested, **nested}
        if nested:
            metadata["run_metadata"] = dict(sorted(nested.items()))
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
    run_metadata: Mapping[str, Any] | None = None,
    sample_metadata: str | Path | None = None,
    checksum_algorithm: str | None = None,
    allow_unclassified: bool = False,
    output_directory: str | Path | None = None,
) -> AnalysisOutputResult:
    """Generate, validate, and optionally write one runtime output inventory."""
    root = Path(repository_root).resolve()
    catalogue, schema = _load_contracts(root)
    entries, live_publish_directory = _runtime_entries(
        publish_directory=Path(publish_directory).resolve()
        if publish_directory is not None
        else None,
        native_output_index=Path(native_output_index).resolve()
        if native_output_index is not None
        else None,
        output_tree=Path(output_tree).resolve() if output_tree is not None else None,
    )
    files, unclassified = _classify(
        catalogue["outputs"],
        entries,
        _read_sample_ids(Path(sample_metadata).resolve())
        if sample_metadata is not None
        else None,
    )
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
    document = _metadata(catalogue, schema, run_metadata, live_publish_directory)
    document["files"] = files
    validation = validate_analysis_output(document, schema)
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
    _, schema = _load_contracts(Path(repository_root).resolve())
    document = _load_mapping(Path(analysis_output).resolve(), "analysis output")
    return validate_analysis_output(document, schema)
