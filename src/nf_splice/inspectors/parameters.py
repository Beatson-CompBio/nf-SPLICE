"""Where a pipeline's source reads ``params.*``, compared with its schema.

A deterministic navigation index, not an authority: it separates real
executable references in workflow code from parameters that only appear in
comments and from values a configuration file defines for itself (such as
nf-core's ``params.genomes`` reference map). People and agents read the
original files to decide what a finding means.
"""

from __future__ import annotations

import os
import re
from collections.abc import Collection
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nf_splice.layout import PUBLISHED_DIR

_IGNORED = {
    ".git",
    ".splice-local",
    ".nf-splice-local",
    ".nextflow",
    ".nf-test",
    "work",
    "node_modules",
    "__pycache__",
    ".venv",
}
_REFERENCE = re.compile(r"\bparams\.([A-Za-z_][A-Za-z0-9_]*)")
_INDEXED = re.compile(r"\bparams\.([A-Za-z_][A-Za-z0-9_]*)\s*\[")
_CONFIG_ASSIGNMENT = re.compile(
    r"^\s*(?:params\.)?([A-Za-z_][A-Za-z0-9_]*)\s*=(?!=)", re.M
)
_MAX_BYTES = 2_000_000
#: Groovy map methods called on ``params`` itself, not parameter names.
_MAP_METHODS = frozenset(
    {
        "containsKey",
        "each",
        "entrySet",
        "findAll",
        "get",
        "getOrDefault",
        "keySet",
        "collect",
        "size",
        "subMap",
        "toString",
        "values",
    }
)


def _strip_comments(text: str) -> str:
    """Remove ``//`` and ``/* */`` comments, keeping line numbers and strings."""
    result: list[str] = []
    index = 0
    quote: str | None = None
    while index < len(text):
        char = text[index]
        if quote is not None:
            result.append(char)
            if char == "\\" and index + 1 < len(text):
                result.append(text[index + 1])
                index += 2
                continue
            if text.startswith(quote, index):
                result.extend(quote[1:])
                index += len(quote)
                quote = None
                continue
            index += 1
            continue
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            end = len(text) if end == -1 else end + 2
            result.append("\n" * text.count("\n", index, end))
            index = end
            continue
        if text.startswith("//", index) and (index == 0 or text[index - 1] != ":"):
            end = text.find("\n", index)
            index = len(text) if end == -1 else end
            continue
        if char in {"'", '"'}:
            quote = (
                text[index : index + 3] if text.startswith(char * 3, index) else char
            )
            result.append(quote)
            index += len(quote)
            continue
        result.append(char)
        index += 1
    return "".join(result)


@dataclass(slots=True)
class ParameterReference:
    """Every place one parameter name occurs in the pipeline source."""

    name: str
    code: list[str] = field(default_factory=list)
    config: list[str] = field(default_factory=list)
    defined_in_config: list[str] = field(default_factory=list)
    comments_only: list[str] = field(default_factory=list)
    indexed: bool = False

    def classification(self, declared: Collection[str]) -> str:
        if self.name in declared:
            return "declared"
        if not self.code and not self.config and not self.defined_in_config:
            return "comment_only"
        if self.defined_in_config and (self.indexed or self.name == "genomes"):
            return "internal_mapping"
        if self.defined_in_config:
            return "defined_in_config"
        return "undeclared"

    def to_json(self, declared: Collection[str]) -> dict[str, Any]:
        return {
            "name": self.name,
            "classification": self.classification(declared),
            "code": self.code[:20],
            "config": self.config[:20],
            "defined_in_config": self.defined_in_config[:20],
            "comments_only": self.comments_only[:20],
        }


@dataclass(frozen=True, slots=True)
class ParameterUsage:
    """``params.*`` references across the source, keyed by name."""

    references: dict[str, ParameterReference]
    files_scanned: int

    def undeclared(self, declared: Collection[str]) -> tuple[ParameterReference, ...]:
        """Executable references to parameters the schema does not declare."""
        return tuple(
            item
            for _, item in sorted(self.references.items())
            if item.classification(declared) == "undeclared"
        )

    def unused(self, declared: Collection[str]) -> tuple[str, ...]:
        """Declared parameters no workflow code or config reads."""
        return tuple(
            name
            for name in sorted(declared)
            if name not in self.references
            or not (self.references[name].code or self.references[name].config)
        )

    def to_json(self, declared: Collection[str]) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for item in self.references.values():
            kind = item.classification(declared)
            counts[kind] = counts.get(kind, 0) + 1
        return {
            "files_scanned": self.files_scanned,
            "counts": counts,
            "undeclared": [
                item.to_json(declared) for item in self.undeclared(declared)
            ],
            "internal_or_config": [
                item.to_json(declared)
                for _, item in sorted(self.references.items())
                if item.classification(declared)
                in {"internal_mapping", "defined_in_config"}
            ],
            "comment_only": sorted(
                item.name
                for item in self.references.values()
                if item.classification(declared) == "comment_only"
            ),
            "declared_but_unused": list(self.unused(declared)),
        }


def _files(root: Path) -> list[Path]:
    found = []
    for current, directories, names in os.walk(root, followlinks=False):
        directories[:] = sorted(
            name
            for name in directories
            if name not in _IGNORED
            and not (name == PUBLISHED_DIR and Path(current) == root)
        )
        for name in sorted(names):
            path = Path(current) / name
            if path.suffix in {".nf", ".config"} and not path.is_symlink():
                parts = path.relative_to(root).parts
                if "tests" in parts[:-1]:
                    continue
                try:
                    if path.stat().st_size <= _MAX_BYTES:
                        found.append(path)
                except OSError:
                    continue
    return found


def parameter_usage(repository_root: str | Path) -> ParameterUsage:
    """Index every ``params.*`` occurrence in workflow code and configuration."""
    root = Path(repository_root).resolve()
    references: dict[str, ParameterReference] = {}
    files = _files(root)
    for path in files:
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        relative = path.relative_to(root).as_posix()
        code = _strip_comments(raw)
        raw_lines = raw.splitlines()
        code_lines = code.splitlines()
        is_config = path.suffix == ".config"
        depth = 0
        for number, line in enumerate(code_lines, start=1):
            location = f"{relative}:{number}"
            if is_config:
                opening = re.match(r"^\s*params\s*\{", line)
                if depth == 0 and opening:
                    depth = 1
                    line_body = line[opening.end() :]
                else:
                    line_body = line
                top_level = depth == 1 and not opening
                assigned = _CONFIG_ASSIGNMENT.match(line_body if opening else line)
                if assigned and (
                    (top_level and depth == 1) or re.match(r"^\s*params\.", line)
                ):
                    name = assigned.group(1)
                    if name != "params":
                        entry = references.setdefault(name, ParameterReference(name))
                        if location not in entry.defined_in_config:
                            entry.defined_in_config.append(location)
                if depth:
                    depth += line_body.count("{") - line_body.count("}")
                    depth = max(depth, 0)
            for match in _REFERENCE.finditer(line):
                if match.group(1) in _MAP_METHODS:
                    continue
                entry = references.setdefault(
                    match.group(1), ParameterReference(match.group(1))
                )
                bucket = entry.config if is_config else entry.code
                if location not in bucket:
                    bucket.append(location)
            for match in _INDEXED.finditer(line):
                references.setdefault(
                    match.group(1), ParameterReference(match.group(1))
                ).indexed = True
        for number, line in enumerate(raw_lines, start=1):
            stripped = code_lines[number - 1] if number <= len(code_lines) else ""
            for match in _REFERENCE.finditer(line):
                if match.group(1) in _MAP_METHODS:
                    continue
                if match.group(0) not in stripped:
                    entry = references.setdefault(
                        match.group(1), ParameterReference(match.group(1))
                    )
                    location = f"{relative}:{number}"
                    if location not in entry.comments_only:
                        entry.comments_only.append(location)
    return ParameterUsage(references, len(files))
