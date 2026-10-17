"""Read-only collection of usable evidence from a Nextflow repository."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from pydantic import JsonValue

from nf_splice.domain.base import EvidenceProvenance
from nf_splice.domain.inspection import (
    EvidenceKind,
    RepositoryEvidence,
    RepositoryInspection,
)
from nf_splice.inspectors.splice_tree import inspect_splice_tree
from nf_splice.layout import PUBLISHED_DIR

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
    "work",
}
_INCLUDED_CONFIG = re.compile(r"\bincludeConfig\s*\(?\s*['\"]([^'\"]+)['\"]")
_PUBLISHED_OUTPUT = re.compile(r"\bpublishDir\b", re.IGNORECASE)
_NATIVE_OUTPUT = re.compile(r"\bpublish\s*:|\boutput\s*\{")
_WORKFLOW = re.compile(r"\bworkflow(?:\s+[A-Za-z0-9_]+)?\s*\{")
_PROCESS = re.compile(r"\bprocess\s+[A-Za-z0-9_]+\s*\{")
_CONTAINER = re.compile(r"\bcontainer\s*(?:=|\(|['\"])")
_CONDA = re.compile(r"\bconda\s*(?:=|\(|['\"])")


def _git_value(root: Path, *arguments: str) -> str | None:
    try:
        result = subprocess.run(
            ("git", "-C", str(root), *arguments),
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = result.stdout.strip()
    return value if result.returncode == 0 and value else None


def _repository_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for current, directory_names, file_names in os.walk(root, followlinks=False):
        directory_names[:] = sorted(
            name
            for name in directory_names
            if name not in _IGNORED_DIRECTORIES
            and not (name == PUBLISHED_DIR and Path(current) == root)
        )
        current_path = Path(current)
        files.extend(current_path / name for name in sorted(file_names))
    return files


def inspect_repository(repository_root: str | Path) -> RepositoryInspection:
    """Return detected evidence and collision state without changing the repository."""
    root = Path(repository_root).resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"repository root is not a directory: {root}")

    revision = _git_value(root, "rev-parse", "HEAD")
    evidence: list[RepositoryEvidence] = []

    def add(
        kind: EvidenceKind,
        location: str,
        observed_value: JsonValue,
        *,
        confidence: float = 1.0,
    ) -> None:
        evidence.append(
            RepositoryEvidence(
                id=f"{kind.value}:{len(evidence) + 1:04d}",
                kind=kind,
                provenance=EvidenceProvenance(
                    source=kind.value,
                    location=location,
                    repository_revision=revision,
                ),
                observed_value=observed_value,
                confidence=confidence,
            )
        )

    git_values = (
        (EvidenceKind.GIT_REMOTE, _git_value(root, "remote", "get-url", "origin")),
        (EvidenceKind.GIT_REVISION, revision),
        (EvidenceKind.GIT_TAG, _git_value(root, "describe", "--tags", "--exact-match")),
    )
    for kind, value in git_values:
        if value is not None:
            add(kind, ".git", value)

    files = _repository_files(root)
    for path in files:
        if path.is_symlink():
            continue
        relative = path.relative_to(root).as_posix()
        name = path.name

        if relative == "nextflow.config":
            add(EvidenceKind.PIPELINE_CONFIG, relative, relative)
        elif relative == "nextflow_schema.json":
            add(EvidenceKind.INPUT_SCHEMA, relative, relative)
        elif relative == "modules.json":
            add(EvidenceKind.MODULE_INDEX, relative, relative)
        elif relative == "ro-crate-metadata.json":
            add(EvidenceKind.RO_CRATE, relative, relative)

        if name in {"meta.yml", "meta.yaml"}:
            add(EvidenceKind.MODULE_METADATA, relative, relative)

        if path.suffix not in {".nf", ".config"}:
            continue

        if path.suffix == ".nf":
            add(EvidenceKind.NEXTFLOW_SOURCE, relative, relative)

        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line_number, line in enumerate(lines, start=1):
            location = f"{relative}:{line_number}"
            if path.suffix == ".nf" and _WORKFLOW.search(line):
                add(EvidenceKind.WORKFLOW, location, line.strip())
            if path.suffix == ".nf" and _PROCESS.search(line):
                add(EvidenceKind.MODULE, location, line.strip())
            for included_path in _INCLUDED_CONFIG.findall(line):
                add(
                    EvidenceKind.INCLUDED_CONFIG,
                    location,
                    {"path": included_path, "exists": (root / included_path).exists()},
                )
            if _PUBLISHED_OUTPUT.search(line):
                add(
                    EvidenceKind.PUBLISHED_OUTPUT,
                    location,
                    line.strip(),
                    confidence=0.9,
                )
            if _NATIVE_OUTPUT.search(line):
                add(
                    EvidenceKind.NATIVE_OUTPUT,
                    location,
                    line.strip(),
                    confidence=0.9,
                )
            if _CONTAINER.search(line):
                add(EvidenceKind.CONTAINER, location, line.strip(), confidence=0.9)
            if _CONDA.search(line):
                add(
                    EvidenceKind.CONDA_ENVIRONMENT,
                    location,
                    line.strip(),
                    confidence=0.9,
                )

    return RepositoryInspection(
        root=str(root),
        repository_revision=revision,
        evidence=tuple(evidence),
        splice_tree=inspect_splice_tree(root),
    )
