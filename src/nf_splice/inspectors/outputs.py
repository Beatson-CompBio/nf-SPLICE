"""Deterministic output-candidate discovery from repository and run evidence."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path

import yaml  # type: ignore[import-untyped]

from nf_splice.domain import (
    Evidence,
    EvidenceProvenance,
    OutputCandidate,
    OutputEntityType,
    OutputFormat,
    OutputScope,
)
from nf_splice.inspectors.routes import CoverageStatus, analyse_routes, glob_to_regex

_IGNORED_DIRECTORIES = {
    ".git",
    ".mypy_cache",
    ".nextflow",
    ".nf-test",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "node_modules",
    "splice",
    "work",
}
_WORKFLOW_OUTPUT = re.compile(r"^\s*([A-Za-z][A-Za-z0-9_]*)\s*=\s*.+\.out\b")
_KEY = re.compile(r"[^a-z0-9]+")
_FORMAT_BY_SUFFIX = {
    ".html": OutputFormat.HTML,
    ".json": OutputFormat.JSON,
    ".yaml": OutputFormat.YAML,
    ".yml": OutputFormat.YAML,
    ".txt": OutputFormat.TXT,
    ".tsv": OutputFormat.TSV,
    ".csv": OutputFormat.CSV,
    ".log": OutputFormat.LOG,
    ".pdf": OutputFormat.PDF,
    ".png": OutputFormat.PNG,
    ".svg": OutputFormat.SVG,
    ".parquet": OutputFormat.PARQUET,
    ".bam": OutputFormat.BAM,
    ".bai": OutputFormat.BAI,
    ".cram": OutputFormat.CRAM,
    ".crai": OutputFormat.CRAI,
    ".bed": OutputFormat.BED,
    ".bw": OutputFormat.BIGWIG,
    ".bigwig": OutputFormat.BIGWIG,
    ".bedgraph": OutputFormat.BEDGRAPH,
    ".gtf": OutputFormat.GTF,
    ".gff": OutputFormat.GFF,
    ".fa": OutputFormat.FASTA,
    ".fasta": OutputFormat.FASTA,
    ".fq": OutputFormat.FASTQ,
    ".fastq": OutputFormat.FASTQ,
    ".vcf": OutputFormat.VCF,
    ".rds": OutputFormat.RDS,
    ".h5": OutputFormat.H5,
    ".mtx": OutputFormat.MTX,
    ".zip": OutputFormat.ZIP,
    ".gz": OutputFormat.GZ,
}


@dataclass(frozen=True, slots=True)
class DiscoveredOutput:
    """One candidate paired with the evidence records supporting it."""

    candidate: OutputCandidate
    evidence: tuple[Evidence, ...]


@dataclass(frozen=True, slots=True)
class _RawCandidate:
    key: str
    path_pattern: str | None
    location: str
    source: str
    process: str | None = None
    title: str | None = None
    description: str | None = None
    output_format: OutputFormat | None = None
    scope: OutputScope | None = None
    entity_type: OutputEntityType | None = None
    confidence: float = 0.7
    conditional: bool = False


def _stable_id(prefix: str, *values: object) -> str:
    digest = hashlib.sha256(
        "\0".join(str(item) for item in values).encode()
    ).hexdigest()[:16]
    return f"{prefix}:{digest}"


def _repository_revision(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ("git", "-C", str(root), "rev-parse", "HEAD"),
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    revision = result.stdout.strip()
    return revision if result.returncode == 0 and revision else None


def _safe_key(value: str) -> str:
    key = _KEY.sub("_", value.lower()).strip("_")
    if not key:
        key = "output"
    if not key[0].isalpha():
        key = f"output_{key}"
    return key


def _format_for(value: str | None) -> OutputFormat | None:
    if not value:
        return None
    lowered = value.lower().replace("\\.", ".")
    for suffix, output_format in sorted(
        _FORMAT_BY_SUFFIX.items(), key=lambda item: len(item[0]), reverse=True
    ):
        if lowered.endswith(suffix) or lowered.endswith(f"{suffix}$"):
            return output_format
    return None


def _source_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for current, directory_names, file_names in os.walk(root, followlinks=False):
        directory_names[:] = sorted(
            name for name in directory_names if name not in _IGNORED_DIRECTORIES
        )
        current_path = Path(current)
        files.extend(
            current_path / name
            for name in sorted(file_names)
            if Path(name).suffix in {".nf", ".config"}
        )
    return files


def _meta_descriptions(root: Path) -> dict[tuple[str, str], str]:
    """Module ``meta.yml`` output descriptions keyed by (module dir, emit)."""
    found: dict[tuple[str, str], str] = {}
    for name in ("meta.yml", "meta.yaml"):
        for path in sorted(root.rglob(name)):
            if any(part in _IGNORED_DIRECTORIES for part in path.parts):
                continue
            try:
                loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
            except (OSError, yaml.YAMLError):
                continue
            if not isinstance(loaded, dict):
                continue
            output = loaded.get("output")
            entries: list[tuple[object, object]] = []
            if isinstance(output, dict):
                entries.extend(output.items())
            elif isinstance(output, list):
                for item in output:
                    if isinstance(item, dict):
                        entries.extend(item.items())
            directory = path.parent.relative_to(root).as_posix()
            for output_name, specification in entries:
                description = None
                if isinstance(specification, dict):
                    description = specification.get("description")
                elif isinstance(specification, list):
                    for nested in specification:
                        if isinstance(nested, dict):
                            for details in nested.values():
                                if isinstance(details, dict):
                                    description = description or details.get(
                                        "description"
                                    )
                if description:
                    found[(directory, str(output_name))] = str(description)
    return found


_ROUTE_CONFIDENCE = {
    CoverageStatus.CONFIRMED_FROM_CODE: 0.85,
    CoverageStatus.INFERRED_UNVERIFIED: 0.6,
    CoverageStatus.UNRESOLVED: 0.4,
    CoverageStatus.NOT_REACHABLE: 0.3,
}


def _route_candidates(root: Path) -> list[_RawCandidate]:
    """Candidates for **published** process outputs only.

    Declared outputs that no publication rule reaches are intermediates and
    never become candidates; the coverage assessment lists them separately.
    """
    analysis = analyse_routes(root)
    instances_by_emit: dict[str, set[str]] = {}
    for item in analysis.published:
        if item.emit:
            instances_by_emit.setdefault(item.emit, set()).add(item.instance)
    descriptions = _meta_descriptions(root)
    found: list[_RawCandidate] = []
    for item in analysis.published:
        stem = Path(item.declared_path or "output").name.split(".")[0] or "output"
        name = item.emit or stem
        if len(instances_by_emit.get(name, {item.instance})) > 1 or not item.emit:
            name = f"{item.instance}_{name}"
        key = _safe_key(name)
        pattern = glob_to_regex(item.published_glob) if item.published_glob else None
        module_directory = (
            item.evidence[0].rsplit("/", 1)[0] if "/" in item.evidence[0] else "."
        )
        description = (
            descriptions.get((module_directory, item.emit)) if item.emit else None
        )
        candidate = _RawCandidate(
            key=key,
            path_pattern=pattern,
            location=item.evidence[1],
            source="process_output",
            process=item.instance,
            description=description,
            output_format=_format_for(item.declared_path),
            entity_type=OutputEntityType.FILE if item.declared_path else None,
            confidence=_ROUTE_CONFIDENCE.get(item.status, 0.5),
            conditional=item.conditional or item.status is CoverageStatus.NOT_REACHABLE,
        )
        found.append(candidate)
        if item.publication is not None:
            found.append(
                replace(
                    candidate,
                    location=item.publication.location,
                    source="publish_rule",
                )
            )
    return found


def _workflow_output_candidates(root: Path) -> list[_RawCandidate]:
    found: list[_RawCandidate] = []
    for source_path in _source_files(root):
        if source_path.suffix != ".nf":
            continue
        relative = source_path.relative_to(root).as_posix()
        try:
            lines = source_path.read_text(
                encoding="utf-8", errors="replace"
            ).splitlines()
        except OSError:
            continue
        for line_number, line in enumerate(lines, start=1):
            workflow_match = _WORKFLOW_OUTPUT.search(line)
            if workflow_match:
                found.append(
                    _RawCandidate(
                        key=_safe_key(workflow_match.group(1)),
                        path_pattern=None,
                        location=f"{relative}:{line_number}",
                        source="workflow_output",
                        confidence=0.55,
                    )
                )
    return found


def _tree_entries(path: Path) -> list[tuple[str, bool]]:
    if path.is_dir():
        directory_entries: list[tuple[str, bool]] = []
        for current, directory_names, file_names in os.walk(path):
            directory_names.sort()
            file_names.sort()
            current_path = Path(current)
            for name in file_names:
                directory_entries.append(
                    ((current_path / name).relative_to(path).as_posix(), False)
                )
        return directory_entries
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        loaded = json.loads(text)
        records = loaded if isinstance(loaded, list) else loaded.get("outputs", [])
        return [
            (str(item.get("path", "")).lstrip("./"), False)
            for item in records
            if isinstance(item, dict) and item.get("path")
        ]
    blocks: dict[str, list[str]] = {}
    current_directory = "."
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.endswith(":"):
            current_directory = stripped[:-1].lstrip("./") or "."
            blocks.setdefault(current_directory, [])
            continue
        blocks.setdefault(current_directory, []).append(stripped)
    text_entries: list[tuple[str, bool]] = []
    known_directories = {item for item in blocks if item != "."}
    for directory, names in blocks.items():
        prefix = "" if directory == "." else f"{directory}/"
        for name in names:
            relative = f"{prefix}{name}".lstrip("./")
            text_entries.append((relative, relative.rstrip("/") in known_directories))
    return text_entries


def _tree_candidates(path: Path, source: str) -> list[_RawCandidate]:
    entries = [(item, is_dir) for item, is_dir in _tree_entries(path) if item]
    found: list[_RawCandidate] = []
    # Identical file names below two or more sibling directories are one
    # per-sample output: quant/S1/counts.tsv + quant/S2/counts.tsv.
    siblings: dict[tuple[str, str], set[str]] = {}
    for relative, is_dir in entries:
        item = Path(relative)
        if not is_dir and len(item.parts) >= 2:
            key = (item.parent.parent.as_posix(), item.name)
            siblings.setdefault(key, set()).add(item.parent.name)
    per_sample = {key for key, parents in siblings.items() if len(parents) > 1}
    for grandparent, name in sorted(per_sample):
        prefix = "" if grandparent == "." else re.escape(grandparent) + "/"
        found.append(
            _RawCandidate(
                key=_safe_key(f"{grandparent}_{name}"),
                path_pattern=f"^{prefix}{{sample}}/{re.escape(name)}$",
                location=f"{path}:{grandparent}/{{sample}}/{name}",
                source=source,
                output_format=_format_for(name),
                scope=OutputScope.SAMPLE,
                entity_type=OutputEntityType.FILE,
                confidence=0.9,
            )
        )
    grouped: dict[tuple[str, str], list[str]] = {}
    for relative, is_dir in entries:
        if is_dir:
            continue
        item = Path(relative)
        if (
            len(item.parts) >= 2
            and (
                item.parent.parent.as_posix(),
                item.name,
            )
            in per_sample
        ):
            continue
        grouped.setdefault((item.parent.as_posix(), item.suffix.lower()), []).append(
            item.name
        )
    for (parent, _), names in sorted(grouped.items()):
        if len(names) > 1:
            # Character-wise on reversed names: the shared filename suffix.
            suffix = os.path.commonprefix(  # noqa: RUF071
                [name[::-1] for name in names]
            )[::-1]
            suffix = suffix[suffix.find(".") :] if "." in suffix else ""
        else:
            suffix = ""
        if len(names) > 1 and suffix:
            filename = f"{{sample}}{suffix}"
            pattern = f"^{'' if parent == '.' else re.escape(parent) + '/'}"
            pattern += rf"(?P<sample_id>[^/]+){re.escape(suffix)}$"
            key_source = f"{parent}_{suffix.lstrip('.')}"
            scope = OutputScope.SAMPLE
        else:
            filename = names[0]
            relative = filename if parent == "." else f"{parent}/{filename}"
            pattern = f"^{re.escape(relative)}$"
            key_source = relative
            # One file for the whole tree is a workflow-wide (job) output. A
            # platform run is never inferred from a filename.
            scope = OutputScope.JOB
        location = f"{path}:{filename}"
        found.append(
            _RawCandidate(
                key=_safe_key(key_source),
                path_pattern=pattern,
                location=location,
                source=source,
                output_format=_format_for(filename),
                scope=scope,
                entity_type=OutputEntityType.FILE,
                confidence=0.95,
            )
        )
    return found


def _catalogue_scope(value: str | None) -> OutputScope | None:
    """Interpret a scope from a published 0.3.0 catalogue."""
    if value is None:
        return None
    try:
        return OutputScope(value)
    except ValueError:
        return None


def _existing_outputs(root: Path) -> list[_RawCandidate]:
    path = root / "splice" / "outputs.yaml"
    if not path.is_file() or path.is_symlink():
        return []
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return []
    if (
        not isinstance(loaded, dict)
        or "catalogue_format_version" not in loaded
        or not isinstance(loaded.get("outputs"), list)
    ):
        return []
    found: list[_RawCandidate] = []
    for index, output in enumerate(loaded["outputs"]):
        if not isinstance(output, dict) or not output.get("key"):
            continue
        patterns = output.get("path_patterns")
        pattern = patterns[0] if isinstance(patterns, list) and patterns else None
        formats = output.get("format")
        output_format = None
        if isinstance(formats, list) and formats:
            try:
                output_format = OutputFormat(str(formats[0]))
            except ValueError:
                pass
        scopes = output.get("scope")
        scope = _catalogue_scope(
            str(scopes[0]) if isinstance(scopes, list) and scopes else None
        )
        entities = output.get("entity_type")
        entity = None
        if isinstance(entities, list) and entities:
            try:
                entity = OutputEntityType(str(entities[0]))
            except ValueError:
                pass
        found.append(
            _RawCandidate(
                key=_safe_key(str(output["key"])),
                path_pattern=str(pattern) if pattern else None,
                location=f"splice/outputs.yaml:outputs[{index}]",
                source="existing_integration",
                title=str(output["title"]) if output.get("title") else None,
                description=(
                    str(output["description"]) if output.get("description") else None
                ),
                output_format=output_format,
                scope=scope,
                entity_type=entity,
                confidence=0.9,
            )
        )
    return found


def discover_output_candidates(
    repository_root: str | Path,
    *,
    example_output_tree: str | Path | None = None,
    publish_directory: str | Path | None = None,
) -> tuple[DiscoveredOutput, ...]:
    """Discover stable, merged candidates without making review decisions."""
    root = Path(repository_root).resolve()
    revision = _repository_revision(root)
    raw = [
        *_route_candidates(root),
        *_workflow_output_candidates(root),
        *_existing_outputs(root),
    ]
    if example_output_tree is not None:
        raw.extend(_tree_candidates(Path(example_output_tree), "example_output_tree"))
    if publish_directory is not None:
        raw.extend(_tree_candidates(Path(publish_directory), "publish_directory"))

    grouped: dict[tuple[str, str | None], list[_RawCandidate]] = {}
    for item in raw:
        grouped.setdefault((item.key, item.path_pattern), []).append(item)

    discovered: list[DiscoveredOutput] = []
    for (key, pattern), group in sorted(
        grouped.items(), key=lambda item: (item[0][0], item[0][1] or "")
    ):
        evidence: list[Evidence] = []
        for item in sorted(group, key=lambda value: (value.source, value.location)):
            evidence.append(
                Evidence(
                    id=_stable_id(
                        "output-evidence",
                        item.source,
                        item.location,
                        item.key,
                        item.path_pattern,
                    ),
                    provenance=EvidenceProvenance(
                        source=item.source,
                        location=item.location,
                        repository_revision=revision,
                    ),
                    observed_value={
                        "suggested_key": item.key,
                        "path_pattern": item.path_pattern,
                    },
                    confidence=item.confidence,
                )
            )
        output_format = next(
            (item.output_format for item in group if item.output_format is not None),
            _format_for(pattern),
        )
        scope = next(
            (item.scope for item in group if item.scope is not None),
            OutputScope.RUN
            if pattern and ("{run}" in pattern or "run_id" in pattern)
            else OutputScope.SAMPLE
            if pattern and ("{sample}" in pattern or "sample_id" in pattern)
            else None,
        )
        entity = next(
            (item.entity_type for item in group if item.entity_type is not None), None
        )
        unresolved = ["key", "title", "description", "category"]
        if output_format is None:
            unresolved.append("formats")
        if scope is None:
            unresolved.append("scopes")
        if entity is None:
            unresolved.append("entity_types")
        if pattern is None:
            unresolved.append("path_patterns")
        candidate = OutputCandidate(
            id=_stable_id("output", key, pattern),
            suggested_key=key,
            path_pattern=pattern,
            source_locations=tuple(sorted({item.location for item in group})),
            processes=tuple(sorted({item.process for item in group if item.process})),
            suggested_title=next(
                (item.title for item in group if item.title),
                key.replace("_", " ").title(),
            ),
            suggested_description=next(
                (item.description for item in group if item.description), None
            ),
            suggested_format=output_format,
            likely_scope=scope,
            likely_entity_type=entity,
            confidence=max(item.confidence for item in group),
            conditional=any(item.conditional for item in group),
            unresolved_fields=tuple(unresolved),
        )
        discovered.append(DiscoveredOutput(candidate, tuple(evidence)))
    return tuple(discovered)
