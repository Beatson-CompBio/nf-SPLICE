"""Read-only browsing of the pipeline's sources and published routes.

Both run in workers. The source list walks recognised file types only, with
a bound on the number of entries; nothing is parsed into metadata here.
"""

from __future__ import annotations

import os
from pathlib import Path

from nf_splice.layout import PRIVATE_DIR, PUBLISHED_DIR

#: File types a person may want to read while authoring.
RECOGNISED = {
    ".nf": "Nextflow",
    ".config": "Nextflow config",
    ".json": "JSON",
    ".yml": "YAML",
    ".yaml": "YAML",
    ".md": "documentation",
    ".cff": "citation",
    ".txt": "text",
    ".csv": "table",
    ".tsv": "table",
}
_SKIP = {
    ".git",
    PRIVATE_DIR,
    ".nf-splice-local",
    "work",
    ".nextflow",
    "node_modules",
    "__pycache__",
    ".venv",
}
MAX_ENTRIES = 3000


def _size(value: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024:
            return f"{value:.0f} {unit}"
        value //= 1024
    return f"{value} TB"


def list_sources(root: Path) -> list[tuple[str, str, str]]:
    """(relative path, kind, size) of recognised files, bounded."""
    found: list[tuple[str, str, str]] = []
    for directory, names, files in os.walk(root):
        names[:] = sorted(
            name
            for name in names
            if (name not in _SKIP and not name.startswith(".")) or name == ".github"
        )
        current = Path(directory)
        if current == root / PUBLISHED_DIR:
            names[:] = []
        for name in sorted(files):
            path = current / name
            kind = RECOGNISED.get(path.suffix.lower())
            if kind is None or path.is_symlink():
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            found.append((path.relative_to(root).as_posix(), kind, _size(size)))
            if len(found) >= MAX_ENTRIES:
                return found
    return found


def route_rows(root: Path) -> list[tuple[str, str, str, str]]:
    """Published routes with whether the catalogue covers them."""
    from nf_splice.layers.outputs import route_coverage

    coverage = route_coverage(root)
    rows = [
        (f"not covered ({item.kind})", item.instance, glob, item.location or "")
        for item in coverage.uncovered
        for glob in item.globs
    ]
    rows += [
        ("covered", instance, glob, "") for instance, glob in coverage.covered_routes
    ]
    rows += [
        ("excluded", instance, glob, "") for instance, glob in coverage.excluded_routes
    ]
    if not rows:
        rows.append(("-", "", coverage.summary(), ""))
    return rows
