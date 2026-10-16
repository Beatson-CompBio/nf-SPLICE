"""Read-only discovery of assay capability *candidates* from repository text.

A candidate is proposed only where the repository names an assay explicitly:
its exact vocabulary label, an alias or its registration code, as a whole
phrase, in documentation, the parameter schema or the configuration. Each
candidate cites every location.

Nothing is inferred from file types or tools: accepting FASTQ, or running an
aligner, does not establish a library preparation such as poly(A) selection.
A candidate is never a capability until a person (or an agent citing it under
an approved policy) declares it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nf_splice.catalogue import ASSAY_TYPES, Catalogue, default_catalogue

#: Files and folders read for evidence, relative to the repository root.
_FILES = ("README.md", "nextflow_schema.json", "nextflow.config", "main.nf")
_FOLDERS = ("docs", "conf", "assets")
_SUFFIXES = {".md", ".json", ".config", ".yml", ".yaml", ".txt", ".nf"}
_MAX_BYTES = 512_000
#: Names shorter than this are too generic to cite on their own (e.g. "WSI").
_MIN_LENGTH = 4


@dataclass(frozen=True, slots=True)
class AssayCandidate:
    """An assay the repository names, with every location."""

    key: str
    label: str
    entity_type: str
    term: str
    locations: tuple[str, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "reference": self.key,
            "label": self.label,
            "entity_type": self.entity_type,
            "matched_term": self.term,
            "locations": list(self.locations),
            "status": "candidate: confirm the pipeline supports this assay",
        }


def _texts(root: Path) -> list[tuple[str, str]]:
    found: list[Path] = [root / name for name in _FILES]
    for folder in _FOLDERS:
        base = root / folder
        if base.is_dir():
            found.extend(
                path
                for path in sorted(base.rglob("*"))
                if path.suffix in _SUFFIXES and path.is_file()
            )
    texts = []
    for path in found:
        if not path.is_file() or path.is_symlink() or path.stat().st_size > _MAX_BYTES:
            continue
        try:
            texts.append(
                (path.relative_to(root).as_posix(), path.read_text(encoding="utf-8"))
            )
        except (OSError, UnicodeError):
            continue
    return texts


def _pattern(term: str) -> re.Pattern[str]:
    return re.compile(
        r"(?<![A-Za-z0-9_])" + re.escape(term) + r"(?![A-Za-z0-9_])", re.IGNORECASE
    )


def detect_assay_candidates(
    repository_root: str | Path, catalogue: Catalogue | None = None
) -> tuple[AssayCandidate, ...]:
    """Assays the repository names explicitly, in a stable order."""
    root = Path(repository_root).resolve()
    catalogue = catalogue or default_catalogue()
    texts = _texts(root)
    candidates = []
    for entity in catalogue.entities():
        if entity.entity_type not in ASSAY_TYPES:
            continue
        registrations = catalogue.registrations_for(entity.entity_id)
        terms = {entity.label, *entity.aliases, *(item.code for item in registrations)}
        terms = {term for term in terms if len(term) >= _MIN_LENGTH}
        locations: set[str] = set()
        matched = ""
        for term in sorted(terms, key=lambda value: (-len(value), value)):
            pattern = _pattern(term)
            for name, text in texts:
                for match in pattern.finditer(text):
                    line = text.count("\n", 0, match.start()) + 1
                    locations.add(f"{name}:{line}")
                    matched = matched or term
        if locations:
            key = (
                registrations[0].code
                if len(registrations) == 1
                else f"entity:{entity.entity_id}"
            )
            candidates.append(
                AssayCandidate(
                    key,
                    entity.label,
                    entity.entity_type.value,
                    matched,
                    tuple(sorted(locations)),
                )
            )
    return tuple(candidates)
