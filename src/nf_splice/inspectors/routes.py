"""Static analysis of Nextflow publication routes (no Nextflow execution).

A process ``output:`` declaration says what a task produces in its work
directory; it does not prove that the file reaches the published results.
This module separates **declared** outputs from **published** outputs by
tracing ``publishDir`` directives in processes and in configuration
``withName`` selectors (including the common nf-core default rule), and
records the workflow conditions under which each process is invoked.

The analysis is deliberately conservative. Anything it cannot establish
from the source text (dynamic publication paths, ``saveAs`` renaming,
processes that are never invoked) is reported with an explicit status
rather than guessed. It never claims exhaustive coverage.
"""

from __future__ import annotations

import fnmatch
import hashlib
import os
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Any

from nf_splice.layout import PUBLISHED_DIR

_IGNORED_DIRECTORIES = {
    ".git",
    ".mypy_cache",
    ".nextflow",
    ".nf-splice-local",
    ".splice-local",
    ".nf-test",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "node_modules",
    # tests/ holds nf-test assets and fixture pipelines: they configure and
    # verify runs, they are not the pipeline's routes (the config analyser
    # excludes them the same way below).
    "tests",
    "work",
}
_MAX_FILE_BYTES = 2_000_000
_IDENT = r"[A-Za-z_][A-Za-z0-9_]*"
_PROCESS = re.compile(rf"\bprocess\s+({_IDENT})\s*\{{")
_WORKFLOW = re.compile(rf"\bworkflow(?:\s+({_IDENT}))?\s*\{{")
_INCLUDE = re.compile(r"\binclude\s*\{([^}]*)\}\s*from\s*['\"]([^'\"]+)['\"]")
_SECTION = re.compile(r"^\s*(input|output|when|script|shell|exec|stub)\s*:")
_WORKFLOW_SECTION = re.compile(r"^\s*(take|main|emit|publish)\s*:")
_PATH_DECLARATION = re.compile(
    r"\b(?:path|file)\s*\(?\s*(?:[^'\"\n,()]*?\s*)?(['\"])(.*?)\1"
)
_UNQUOTED_PATH = re.compile(rf"\b(?:path|file)\s*\(\s*({_IDENT})\s*\)")
_EMIT = re.compile(rf"\bemit\s*:\s*({_IDENT})")
_OPTIONAL = re.compile(r"\boptional\s*:\s*true\b")
_STRING = re.compile(r"(['\"])(.*?)(?<!\\)\1", re.DOTALL)
_PATTERN = re.compile(r"\bpattern\s*:\s*(['\"])(.*?)\1")
_ENABLED = re.compile(r"\benabled\s*:\s*([^,\]\n]+)")
_SAVE_AS = re.compile(r"\bsaveAs\s*:")
_VERSIONS_SAVE_AS = re.compile(
    r"saveAs\s*:\s*\{\s*(\w+)\s*->\s*\1\s*\.equals\(\s*['\"]versions\.yml['\"]\s*\)"
    r"\s*\?\s*null\s*:\s*\1\s*\}"
)
_OUTDIR = re.compile(r"^\$\{?\s*params\.outdir\s*\}?/?")
_NF_CORE_DEFAULT = re.compile(
    r"\$\{\s*task\.process\.tokenize\(\s*['\"]:['\"]\s*\)\[-1\]"
    r"\.tokenize\(\s*['\"]_['\"]\s*\)\[0\]\.toLowerCase\(\)\s*\}"
)
_META_ID = re.compile(r"\$\{\s*meta\.id\s*\}|\$meta\.id\b")
#: How a route shows a name built from the process's ``meta.id``. It is what
#: the code says, not a scope: ``meta.id`` is often a sample, but in other
#: steps a reference, a batch or a plate. The author or agent decides.
META_ID = "{meta.id}"
_INTERPOLATION = re.compile(r"\$\{[^}]*\}|\$[A-Za-z_][A-Za-z0-9_.]*")
_WHEN_BOILERPLATE = re.compile(
    r"^task\.ext\.when\s*==\s*null\s*\|\|\s*task\.ext\.when$"
)
_NOT_CALLS = {
    "if",
    "for",
    "while",
    "switch",
    "catch",
    "return",
    "def",
    "println",
    "log",
    "error",
    "exit",
    "file",
    "path",
    "tuple",
    "val",
    "Channel",
    "channel",
}


class CoverageStatus(str, Enum):
    """How strongly a published output route is supported by evidence."""

    CONFIRMED_FROM_CODE = "confirmed_from_code"
    OBSERVED_IN_EXAMPLE = "observed_in_example"
    INFERRED_UNVERIFIED = "inferred_unverified"
    NOT_REACHABLE = "not_reachable"
    UNRESOLVED = "unresolved"
    NOT_PUBLISHED = "not_published"


@dataclass(frozen=True, slots=True)
class DeclaredOutput:
    """One ``path``/``file`` declaration in a process ``output:`` section."""

    process: str
    emit: str | None
    path: str | None
    optional: bool
    location: str
    named_by_meta: bool = False


@dataclass(frozen=True, slots=True)
class PublishRule:
    """A ``publishDir`` rule from a process or a configuration selector."""

    source: str
    location: str
    path_expression: str
    directory: str | None
    dynamic: bool
    patterns: tuple[str, ...] = ()
    save_as: str | None = None
    enabled: str | None = None
    selector: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "location": self.location,
            "path_expression": self.path_expression,
            "directory": self.directory,
            "dynamic": self.dynamic,
            "patterns": list(self.patterns),
            "save_as": self.save_as,
            "enabled": self.enabled,
            "selector": self.selector,
        }


@dataclass(frozen=True, slots=True)
class _Process:
    name: str
    location: str
    module_directory: str
    outputs: tuple[DeclaredOutput, ...]
    rules: tuple[PublishRule, ...]
    when: str | None


@dataclass(slots=True)
class _Workflow:
    name: str | None
    location: str
    calls: list[tuple[str, str, tuple[str, ...]]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class RouteOutput:
    """One declared process output with its publication and route evidence."""

    id: str
    process: str
    instance: str
    emit: str | None
    declared_path: str | None
    published_glob: str | None
    publication: PublishRule | None
    conditions: tuple[tuple[str, ...], ...]
    optional: bool
    reachable: bool | None
    invocations: tuple[str, ...]
    status: CoverageStatus
    evidence: tuple[str, ...]
    notes: tuple[str, ...] = ()

    @property
    def conditional(self) -> bool:
        return self.optional or any(path for path in self.conditions)

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "process": self.process,
            "instance": self.instance,
            "emit": self.emit,
            "declared_path": self.declared_path,
            "published_glob": self.published_glob,
            "published": self.publication is not None,
            "publication": None
            if self.publication is None
            else self.publication.to_json(),
            "conditions": [list(item) for item in self.conditions],
            "optional": self.optional,
            "reachable": self.reachable,
            "invocations": list(self.invocations),
            "status": self.status.value,
            "evidence": list(self.evidence),
            "notes": list(self.notes),
        }


@dataclass(frozen=True, slots=True)
class RouteAnalysis:
    """Every declared output, split into published and unpublished routes."""

    published: tuple[RouteOutput, ...]
    unpublished: tuple[RouteOutput, ...]
    entry_workflow: str | None
    files_scanned: int
    notes: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        statuses: dict[str, int] = {}
        for item in self.published:
            statuses[item.status.value] = statuses.get(item.status.value, 0) + 1
        return {
            "entry_workflow": self.entry_workflow,
            "files_scanned": self.files_scanned,
            "published": [item.to_json() for item in self.published],
            "unpublished": [item.to_json() for item in self.unpublished],
            "status_counts": statuses,
            "notes": list(self.notes),
        }


# ------------------------------------------------------------ source text


def _strip_comments(text: str) -> str:
    """Blank out comments while keeping strings, offsets and line numbers."""
    out: list[str] = []
    index = 0
    length = len(text)
    quote: str | None = None
    while index < length:
        char = text[index]
        if quote is not None:
            out.append(char)
            if char == "\\" and index + 1 < length:
                out.append(text[index + 1])
                index += 2
                continue
            if text.startswith(quote, index):
                out.extend(text[index + 1 : index + len(quote)])
                index += len(quote)
                quote = None
                continue
            index += 1
            continue
        if text.startswith('"""', index) or text.startswith("'''", index):
            quote = text[index : index + 3]
            out.append(quote)
            index += 3
            continue
        if char in {"'", '"'}:
            quote = char
            out.append(char)
            index += 1
            continue
        if text.startswith("//", index):
            end = text.find("\n", index)
            end = length if end == -1 else end
            out.append(" " * (end - index))
            index = end
            continue
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            end = length if end == -1 else end + 2
            out.append(
                "".join("\n" if item == "\n" else " " for item in text[index:end])
            )
            index = end
            continue
        out.append(char)
        index += 1
    return "".join(out)


def _matching(text: str, start: int, opening: str = "{", closing: str = "}") -> int:
    """Index of the bracket closing the one at ``start`` (string aware)."""
    depth = 0
    index = start
    quote: str | None = None
    while index < len(text):
        char = text[index]
        if quote is not None:
            if char == "\\":
                index += 2
                continue
            if text.startswith(quote, index):
                index += len(quote)
                quote = None
                continue
            index += 1
            continue
        if text.startswith('"""', index) or text.startswith("'''", index):
            quote = text[index : index + 3]
            index += 3
            continue
        if char in {"'", '"'}:
            quote = char
        elif char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return len(text) - 1


def _line(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _blocks(
    pattern: re.Pattern[str], text: str
) -> Iterator[tuple[re.Match[str], str, int]]:
    """Yield each match whose ``{`` opens a block, with body and body offset."""
    for match in pattern.finditer(text):
        open_index = match.end() - 1
        close_index = _matching(text, open_index)
        yield match, text[open_index + 1 : close_index], open_index + 1


def _source_files(root: Path, suffixes: tuple[str, ...]) -> list[Path]:
    files: list[Path] = []
    for current, directory_names, file_names in os.walk(root, followlinks=False):
        directory_names[:] = sorted(
            name
            for name in directory_names
            if name not in _IGNORED_DIRECTORIES
            and not (name == PUBLISHED_DIR and Path(current) == root)
        )
        for name in sorted(file_names):
            path = Path(current) / name
            if path.suffix in suffixes and not path.is_symlink():
                try:
                    if path.stat().st_size <= _MAX_FILE_BYTES:
                        files.append(path)
                except OSError:
                    continue
    return files


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


# ------------------------------------------------------------ publication


def _first_string(expression: str) -> str | None:
    match = _STRING.search(expression)
    return match.group(2) if match else None


def _resolve_literal(raw: str | None, process: str) -> tuple[str | None, bool]:
    """Directory relative to ``params.outdir`` and whether it is dynamic."""
    if raw is None:
        return None, True
    value = _NF_CORE_DEFAULT.sub(process.split("_")[0].lower(), raw.strip())
    value = _OUTDIR.sub("", value).strip("/")
    value = _META_ID.sub(META_ID, value)
    dynamic = bool(_INTERPOLATION.search(value))
    value = _INTERPOLATION.sub("*", value)
    return value or None, dynamic


def _bind(rule: PublishRule, instance: str) -> PublishRule:
    """Resolve a rule's directory for one process instance name."""
    literal = None if rule.path_expression.startswith("<") else rule.path_expression
    directory, dynamic = _resolve_literal(literal, instance)
    return replace(rule, directory=directory, dynamic=dynamic)


_BRANCHING = re.compile(r"\bif\b|\belse\b|\?|==|!=|\bswitch\b")


def _closure(expression: str) -> str | None:
    """The body of a ``{ ... }`` closure the expression starts with."""
    stripped = expression.lstrip()
    if not stripped.startswith("{"):
        return None
    depth = 0
    for index, char in enumerate(stripped):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return stripped[1:index]
    return stripped[1:]


def _rule(
    text: str,
    *,
    source: str,
    location: str,
    process: str,
    selector: str | None = None,
) -> PublishRule:
    path_match = re.search(r"\bpath\s*:\s*", text)
    expression = text[path_match.end() :] if path_match else text
    closure = _closure(expression)
    # A path computed by branching code has no single directory: the first
    # string literal could be a comparison operand. Report it unresolved.
    raw = (
        None
        if closure is not None and _BRANCHING.search(closure)
        else _first_string(expression)
    )
    directory, dynamic = _resolve_literal(raw, process)
    save_as: str | None = None
    if _VERSIONS_SAVE_AS.search(text):
        save_as = "excludes versions.yml"
    elif _SAVE_AS.search(text):
        save_as = "custom"
    enabled = _ENABLED.search(text)
    return PublishRule(
        source=source,
        location=location,
        path_expression=raw if raw is not None else f"<{expression.strip()[:80]}>",
        directory=directory,
        dynamic=dynamic,
        patterns=tuple(item.group(2) for item in _PATTERN.finditer(text)),
        save_as=save_as,
        enabled=enabled.group(1).strip() if enabled else None,
        selector=selector,
    )


def _map_items(value: str) -> list[str]:
    """Split ``[ [..], [..] ]`` into maps; a single map stays one item."""
    stripped = value.strip()
    if not stripped.startswith("["):
        return [stripped]
    inner = stripped[1 : _matching(stripped, 0, "[", "]")]
    if inner.lstrip().startswith("["):
        items = []
        index = 0
        while (start := inner.find("[", index)) != -1:
            end = _matching(inner, start, "[", "]")
            items.append(inner[start : end + 1])
            index = end + 1
        return items
    return [stripped]


def _assignment_value(body: str, start: int) -> str:
    """The value text of ``publishDir = ...`` beginning at ``start``."""
    rest = body[start:].lstrip()
    if rest.startswith("["):
        return rest[: _matching(rest, 0, "[", "]") + 1]
    return rest.split("\n", 1)[0]


def _expand_braces(pattern: str) -> list[str]:
    match = re.search(r"\{([^{}]*)\}", pattern)
    if not match:
        return [pattern]
    return [
        expanded
        for option in match.group(1).split(",")
        for expanded in _expand_braces(
            pattern[: match.start()] + option + pattern[match.end() :]
        )
    ]


def _passes_filters(declared: str, rule: PublishRule) -> bool:
    """Whether a declared glob can satisfy the rule's ``pattern`` filters."""
    name = declared.rsplit("/", 1)[-1]
    if rule.save_as == "excludes versions.yml" and name == "versions.yml":
        return False
    if not rule.patterns:
        return True
    samples = [
        item.replace("*", "x").replace("?", "x") for item in _expand_braces(name)
    ]
    return any(
        fnmatch.fnmatchcase(sample, option)
        for pattern in rule.patterns
        for option in _expand_braces(pattern)
        for sample in samples
    )


def _selector_matches(selector: str, name: str) -> bool:
    for alternative in selector.split("|"):
        alternative = alternative.strip().strip("'\"")
        if not alternative:
            continue
        last = alternative.rsplit(":", 1)[-1]
        for candidate in {alternative, last}:
            try:
                if re.fullmatch(candidate, name):
                    return True
            except re.error:
                if candidate == name:
                    return True
    return False


# ------------------------------------------------------------ parsing


def _declared_outputs(
    process: str, body: str, offset: int, text: str, relative: str
) -> tuple[tuple[DeclaredOutput, ...], str | None]:
    outputs: list[DeclaredOutput] = []
    section: str | None = None
    when_lines: list[str] = []
    position = offset
    for line in body.split("\n"):
        line_number = _line(text, position)
        position += len(line) + 1
        label = _SECTION.match(line)
        if label:
            section = label.group(1)
            line = line[label.end() :]
        if section == "when" and line.strip():
            when_lines.append(line.strip())
        if section != "output":
            continue
        emit = _EMIT.search(line)
        optional = bool(_OPTIONAL.search(line))
        named_by_meta = bool(re.search(r"\bval\s*\(\s*meta\s*\)", line))
        found = False
        for match in _PATH_DECLARATION.finditer(line):
            found = True
            outputs.append(
                DeclaredOutput(
                    process=process,
                    emit=emit.group(1) if emit else None,
                    path=match.group(2),
                    optional=optional,
                    location=f"{relative}:{line_number}",
                    named_by_meta=named_by_meta,
                )
            )
        if not found and _UNQUOTED_PATH.search(line):
            outputs.append(
                DeclaredOutput(
                    process=process,
                    emit=emit.group(1) if emit else None,
                    path=None,
                    optional=optional,
                    location=f"{relative}:{line_number}",
                )
            )
    when = " ".join(when_lines).strip() or None
    if when and _WHEN_BOILERPLATE.match(when):
        when = None
    return tuple(outputs), when


def _process_rules(
    process: str, body: str, offset: int, text: str, relative: str
) -> tuple[PublishRule, ...]:
    rules = []
    for match in re.finditer(r"\bpublishDir\b", body):
        line_end = body.find("\n", match.end())
        statement = body[match.end() : line_end if line_end != -1 else len(body)]
        # A directive may continue on following lines after a trailing comma.
        cursor = line_end
        while statement.rstrip().endswith(",") and cursor != -1:
            next_end = body.find("\n", cursor + 1)
            statement += body[cursor + 1 : next_end if next_end != -1 else len(body)]
            cursor = next_end
        if statement.lstrip().startswith("="):
            statement = statement.lstrip()[1:]
        rules.append(
            _rule(
                statement,
                source="process",
                location=f"{relative}:{_line(text, offset + match.start())}",
                process=process,
            )
        )
    return tuple(rules)


def _parse_processes(root: Path, files: list[Path]) -> dict[str, list[_Process]]:
    processes: dict[str, list[_Process]] = {}
    for path in files:
        raw = _read(path)
        if raw is None:
            continue
        text = _strip_comments(raw)
        relative = path.relative_to(root).as_posix()
        for match, body, offset in _blocks(_PROCESS, text):
            name = match.group(1)
            outputs, when = _declared_outputs(name, body, offset, text, relative)
            processes.setdefault(name, []).append(
                _Process(
                    name=name,
                    location=f"{relative}:{_line(text, match.start())}",
                    module_directory=path.parent.relative_to(root).as_posix(),
                    outputs=outputs,
                    rules=_process_rules(name, body, offset, text, relative),
                    when=when,
                )
            )
    return processes


def _aliases(files: list[Path]) -> dict[str, str]:
    """Map included alias -> original name across every source file."""
    aliases: dict[str, str] = {}
    for path in files:
        raw = _read(path)
        if raw is None:
            continue
        for match in _INCLUDE.finditer(_strip_comments(raw)):
            for item in re.split(r"[;\n]", match.group(1)):
                parts = item.split()
                if len(parts) == 3 and parts[1] == "as":
                    aliases[parts[2]] = parts[0]
    return aliases


def _condition_text(text: str) -> str:
    return " ".join(text.split())


def _workflow_calls(
    body: str, offset: int, text: str, relative: str, names: set[str]
) -> list[tuple[str, str, tuple[str, ...]]]:
    """Invocations with the stack of enclosing ``if`` conditions."""
    calls: list[tuple[str, str, tuple[str, ...]]] = []
    frames: list[tuple[int, str]] = []
    depth = 0
    index = 0
    last_closed: str | None = None
    pending_line_condition: tuple[int, str] | None = None
    quote: str | None = None
    section_ok = True
    while index < len(body):
        char = body[index]
        if quote is not None:
            if char == "\\":
                index += 2
                continue
            if body.startswith(quote, index):
                index += len(quote)
                quote = None
                continue
            index += 1
            continue
        if char in {"'", '"'}:
            quote = '"""' if body.startswith('"""', index) else char
            index += len(quote)
            continue
        if char == "\n":
            pending_line_condition = None
            line_end = body.find("\n", index + 1)
            line = body[index + 1 : line_end if line_end != -1 else len(body)]
            label = _WORKFLOW_SECTION.match(line)
            if label:
                section_ok = label.group(1) == "main"
            index += 1
            continue
        if char == "{":
            depth += 1
            index += 1
            continue
        if char == "}":
            depth -= 1
            last_closed = None
            if frames and frames[-1][0] == depth + 1:
                last_closed = frames.pop()[1]
            index += 1
            continue
        keyword = re.match(r"(else\s+if|if)\s*\(", body[index:])
        boundary = index == 0 or not (
            body[index - 1].isalnum() or body[index - 1] in "_."
        )
        if keyword and boundary:
            open_paren = index + keyword.end() - 1
            close_paren = _matching(body, open_paren, "(", ")")
            condition = _condition_text(body[open_paren + 1 : close_paren])
            if keyword.group(1).startswith("else") and last_closed is not None:
                condition = f"not ({last_closed}) and ({condition})"
            after = body[close_paren + 1 :].lstrip(" \t")
            if after.startswith("{"):
                brace = close_paren + 1 + (len(body[close_paren + 1 :]) - len(after))
                depth += 1
                frames.append((depth, condition))
                index = brace + 1
            else:
                pending_line_condition = (depth, condition)
                index = close_paren + 1
            continue
        else_match = re.match(r"else\s*\{", body[index:])
        if else_match and boundary and last_closed is not None:
            depth += 1
            frames.append((depth, f"not ({last_closed})"))
            index += else_match.end()
            continue
        call = re.match(rf"({_IDENT})\s*(?:\(|$|\s*\n)", body[index:])
        pipe = re.match(rf"\|\s*({_IDENT})\b", body[index:])
        if (call or pipe) and boundary:
            name = (call or pipe).group(1)  # type: ignore[union-attr]
            if name in names and name not in _NOT_CALLS and section_ok:
                after_name = body[index + len((call or pipe).group(0)) - 1 :]  # type: ignore[union-attr]
                if call is None or not after_name.startswith("."):
                    conditions = [item[1] for item in frames]
                    if pending_line_condition is not None:
                        conditions.append(pending_line_condition[1])
                    location = f"{relative}:{_line(text, offset + index)}"
                    calls.append((name, location, tuple(conditions)))
            # Step over the name only: the match may end with the line break,
            # which must still be seen so a following ``main:`` label counts.
            index += (
                body.index(name, index) - index + len(name)
                if call is not None
                else len(pipe.group(0))  # type: ignore[union-attr]
            )
            continue
        index += 1
    return calls


def _parse_workflows(
    root: Path, files: list[Path], names: set[str]
) -> dict[str | None, list[_Workflow]]:
    workflows: dict[str | None, list[_Workflow]] = {}
    for path in files:
        raw = _read(path)
        if raw is None:
            continue
        text = _strip_comments(raw)
        relative = path.relative_to(root).as_posix()
        for match, body, offset in _blocks(_WORKFLOW, text):
            workflow = _Workflow(
                name=match.group(1),
                location=f"{relative}:{_line(text, match.start())}",
            )
            workflow.calls = _workflow_calls(body, offset, text, relative, names)
            workflows.setdefault(workflow.name, []).append(workflow)
    return workflows


def _config_rules(
    root: Path, files: list[Path]
) -> tuple[list[PublishRule], list[tuple[str, str, str]]]:
    """``withName`` and default ``process`` publication rules from configs.

    Returns rules (selector ``None`` for the default rule) and ``ext.when``
    conditions as ``(selector, condition, location)``.
    """
    rules: list[PublishRule] = []
    whens: list[tuple[str, str, str]] = []
    selector_pattern = re.compile(r"\bwithName\s*:\s*(['\"]?)([^'\"{]+?)\1\s*\{")
    for path in files:
        raw = _read(path)
        if raw is None:
            continue
        text = _strip_comments(raw)
        relative = path.relative_to(root).as_posix()
        selector_spans: list[tuple[int, int]] = []
        for match, body, offset in _blocks(selector_pattern, text):
            selector = match.group(2).strip()
            selector_spans.append((offset, offset + len(body)))
            for assignment in re.finditer(r"\bpublishDir\s*=\s*", body):
                value = _assignment_value(body, assignment.end())
                location = f"{relative}:{_line(text, offset + assignment.start())}"
                for item in _map_items(value):
                    rules.append(
                        _rule(
                            item,
                            source="config",
                            location=location,
                            process="",
                            selector=selector,
                        )
                    )
            for when in re.finditer(r"\bext\.when\s*=\s*", body):
                value = body[when.end() :].split("\n", 1)[0].strip()
                value = value.strip("{} ")
                whens.append(
                    (
                        selector,
                        value,
                        f"{relative}:{_line(text, offset + when.start())}",
                    )
                )
        for match, body, offset in _blocks(re.compile(r"\bprocess\s*\{"), text):
            for assignment in re.finditer(r"\bpublishDir\s*=\s*", body):
                absolute = offset + assignment.start()
                if any(start <= absolute < end for start, end in selector_spans):
                    continue
                value = _assignment_value(body, assignment.end())
                for item in _map_items(value):
                    rules.append(
                        _rule(
                            item,
                            source="config_default",
                            location=f"{relative}:{_line(text, absolute)}",
                            process="",
                        )
                    )
            del match
    return rules, whens


# ------------------------------------------------------------ routes


def _route_conditions(
    workflows: dict[str | None, list[_Workflow]],
    aliases: dict[str, str],
    entry: _Workflow | None,
) -> dict[str, tuple[tuple[tuple[str, ...], ...], tuple[str, ...]]]:
    """Per invoked name: alternative condition paths and invocation sites."""
    found: dict[str, tuple[list[tuple[str, ...]], list[str]]] = {}
    roots = (
        [entry]
        if entry is not None
        else [item for group in workflows.values() for item in group]
    )
    stack: list[tuple[_Workflow, tuple[str, ...], frozenset[str]]] = [
        (item, (), frozenset()) for item in roots
    ]
    visits = 0
    while stack and visits < 10_000:
        visits += 1
        workflow, inherited, seen = stack.pop()
        for name, location, conditions in workflow.calls:
            path = inherited + conditions
            target = aliases.get(name, name)
            if name in workflows or target in workflows:
                key = name if name in workflows else target
                if key in seen:
                    continue
                for child in workflows[key]:
                    stack.append((child, path, seen | {key}))
                continue
            paths, sites = found.setdefault(name, ([], []))
            if path not in paths:
                paths.append(path)
            if location not in sites:
                sites.append(location)
    return {
        name: (tuple(paths), tuple(sorted(sites)))
        for name, (paths, sites) in found.items()
    }


def _glob_join(directory: str | None, declared: DeclaredOutput) -> str | None:
    """Published glob; a leading ``*`` named after an input ``meta`` map is
    shown as ``{meta.id}`` (nf-core's default prefix), never as a sample."""
    if declared.path is None:
        return None
    path = declared.path.lstrip("./")
    path = _META_ID.sub(META_ID, path)
    path = _INTERPOLATION.sub("*", path)
    joined = f"{directory}/{path}" if directory else path
    if declared.named_by_meta and META_ID not in joined:
        head, _, name = joined.rpartition("/")
        if name.startswith("*"):
            name = META_ID + name[1:]
            joined = f"{head}/{name}" if head else name
    return joined


def _route_id(*values: object) -> str:
    digest = hashlib.sha256("\0".join(str(item) for item in values).encode())
    return f"route:{digest.hexdigest()[:16]}"


def _status(
    rule: PublishRule | None, reachable: bool | None, declared: str | None
) -> tuple[CoverageStatus, list[str]]:
    notes: list[str] = []
    if reachable is False:
        notes.append("process is defined but never invoked from the entry workflow")
        return CoverageStatus.NOT_REACHABLE, notes
    if rule is None:
        return CoverageStatus.UNRESOLVED, notes
    if declared is None:
        notes.append("declared output path is a variable; file names are unknown")
        return CoverageStatus.UNRESOLVED, notes
    if rule.directory is None and rule.dynamic:
        notes.append("publication path is computed at run time")
        return CoverageStatus.UNRESOLVED, notes
    if rule.save_as == "custom":
        notes.append("saveAs may rename or drop published files")
        return CoverageStatus.INFERRED_UNVERIFIED, notes
    if rule.dynamic:
        notes.append("publication path contains run-time values")
        return CoverageStatus.INFERRED_UNVERIFIED, notes
    if rule.source == "config_default":
        notes.append("published by the configuration's default publishDir rule")
        return CoverageStatus.INFERRED_UNVERIFIED, notes
    if reachable is None:
        notes.append("no entry workflow was found, so reachability is unknown")
        return CoverageStatus.INFERRED_UNVERIFIED, notes
    return CoverageStatus.CONFIRMED_FROM_CODE, notes


def analyse_routes(repository_root: str | Path) -> RouteAnalysis:
    """Trace declared process outputs to their publication rules and routes."""
    root = Path(repository_root).resolve()
    nf_files = _source_files(root, (".nf",))
    # nf-test configurations (``tests/nextflow.config``) configure test runs,
    # not what the pipeline publishes.
    config_files = [
        path
        for path in _source_files(root, (".config",))
        if "tests" not in path.relative_to(root).parts[:-1]
    ]
    processes = _parse_processes(root, nf_files)
    aliases = _aliases(nf_files)
    workflows_first = _parse_workflows(root, nf_files, set())
    names = (
        set(processes)
        | set(aliases)
        | {name for name in workflows_first if name is not None}
    )
    workflows = _parse_workflows(root, nf_files, names)
    entries = workflows.get(None, [])
    entry = next(
        (item for item in entries if item.location.startswith("main.nf:")),
        entries[0] if entries else None,
    )
    notes: list[str] = []
    if entry is None:
        notes.append("no entry workflow (workflow { ... }) was found")
    if len(entries) > 1:
        notes.append(
            "several entry workflows found; using " + (entry.location if entry else "")
        )
    routes = _route_conditions(workflows, aliases, entry)
    config_rules, config_whens = _config_rules(root, config_files)
    instances: dict[str, list[str]] = {}
    for alias, original in aliases.items():
        if original in processes:
            instances.setdefault(original, []).append(alias)
    published: list[RouteOutput] = []
    unpublished: list[RouteOutput] = []
    for name in sorted(processes):
        invoked_names = [
            item for item in [name, *instances.get(name, [])] if item in routes
        ]
        names_for_routes = invoked_names or [name]
        for definition in processes[name]:
            for instance in names_for_routes:
                route = routes.get(instance)
                reachable: bool | None
                if entry is None:
                    reachable = None
                else:
                    reachable = route is not None
                paths = route[0] if route else ()
                sites = route[1] if route else ()
                selector_rules = [
                    item
                    for item in config_rules
                    if item.selector is not None
                    and _selector_matches(item.selector, instance)
                ]
                if selector_rules:
                    rules = selector_rules
                elif definition.rules:
                    rules = list(definition.rules)
                else:
                    rules = [item for item in config_rules if item.selector is None]
                # withName rules take precedence over process directives and the
                # default rule (Nextflow configuration precedence).
                rules = [_bind(item, instance) for item in rules]
                extra_conditions: list[str] = []
                if definition.when:
                    extra_conditions.append(f"when: {definition.when}")
                for selector, condition, _location in config_whens:
                    if _selector_matches(selector, instance):
                        extra_conditions.append(f"ext.when: {condition}")
                for declared in definition.outputs:
                    matching = [
                        rule
                        for rule in rules
                        if declared.path is None or _passes_filters(declared.path, rule)
                    ]
                    if not matching:
                        status = (
                            CoverageStatus.NOT_REACHABLE
                            if reachable is False
                            else CoverageStatus.NOT_PUBLISHED
                        )
                        unpublished.append(
                            RouteOutput(
                                id=_route_id(
                                    instance, declared.location, declared.path
                                ),
                                process=name,
                                instance=instance,
                                emit=declared.emit,
                                declared_path=declared.path,
                                published_glob=None,
                                publication=None,
                                conditions=paths,
                                optional=declared.optional,
                                reachable=reachable,
                                invocations=sites,
                                status=status,
                                evidence=(definition.location, declared.location),
                                notes=(
                                    "declared but not published by any publishDir rule",
                                ),
                            )
                        )
                        continue
                    for rule in matching:
                        if rule.enabled and rule.enabled.strip() == "false":
                            # Switched off in the code: nothing is published.
                            continue
                        rule_conditions = list(extra_conditions)
                        if rule.enabled and rule.enabled.strip() != "true":
                            rule_conditions.append(
                                f"publishDir enabled: {rule.enabled}"
                            )
                        condition_paths = tuple(
                            path + tuple(rule_conditions) for path in (paths or ((),))
                        )
                        status, notes_for = _status(rule, reachable, declared.path)
                        glob = _glob_join(rule.directory, declared)
                        published.append(
                            RouteOutput(
                                id=_route_id(
                                    instance,
                                    declared.location,
                                    declared.path,
                                    rule.location,
                                ),
                                process=name,
                                instance=instance,
                                emit=declared.emit,
                                declared_path=declared.path,
                                published_glob=glob,
                                publication=rule,
                                conditions=tuple(
                                    item for item in condition_paths if item
                                ),
                                optional=declared.optional,
                                reachable=reachable,
                                invocations=sites,
                                status=status,
                                evidence=(
                                    definition.location,
                                    declared.location,
                                    rule.location,
                                    *sites,
                                ),
                                notes=tuple(notes_for),
                            )
                        )
    return RouteAnalysis(
        published=tuple(published),
        unpublished=tuple(unpublished),
        entry_workflow=entry.location if entry else None,
        files_scanned=len(nf_files) + len(config_files),
        notes=tuple(notes),
    )


def glob_to_regex(value: str) -> str:
    """Anchored regular expression for a published glob.

    ``{meta.id}`` and ``*`` match one path segment; ``**`` any depth.
    """
    value = value.lstrip("./")
    parts: list[str] = []
    index = 0
    while index < len(value):
        if value.startswith(META_ID, index):
            parts.append("[^/]+")
            index += len(META_ID)
            continue
        char = value[index]
        if value.startswith("**", index):
            parts.append(".+")
            index += 2
            continue
        if char == "*":
            parts.append("[^/]+")
        elif char == "?":
            parts.append("[^/]")
        elif char == "{":
            end = value.find("}", index)
            if end == -1:
                parts.append(re.escape(char))
            else:
                options = value[index + 1 : end].split(",")
                parts.append(
                    "(?:" + "|".join(re.escape(item) for item in options) + ")"
                )
                index = end + 1
                continue
        else:
            parts.append(re.escape(char))
        index += 1
    return "^" + "".join(parts) + "$"


_ALTERNATION = re.compile(r"\((?:\?:)?([^()]*\|[^()]*)\)")


def glob_examples(glob: str, patterns: Sequence[str] = ()) -> list[str]:
    """Illustrative paths for a glob, for checking catalogue coverage.

    A ``*`` stands for a run-time value. Besides a neutral filler, each
    literal alternative a catalogue pattern names (``(CpG|CHG|CHH)``) is
    tried in its place, so a precise pattern covers the route without being
    weakened to ``{any}``.
    """
    examples = [example_path(glob)]
    if "*" not in glob.replace("**", ""):
        return examples
    for pattern in patterns:
        for group in _ALTERNATION.findall(pattern):
            for option in group.split("|"):
                literal = re.sub(r"\\(.)", r"\1", option)
                if re.fullmatch(r"[A-Za-z0-9_.+-]+", literal):
                    candidate = example_path(re.sub(r"(?<!\*)\*(?!\*)", literal, glob))
                    if candidate not in examples:
                        examples.append(candidate)
    return examples


def example_path(glob: str) -> str:
    """A concrete illustrative path for a glob (used for catalogue matching)."""
    value = glob.replace(META_ID, "ID1")
    value = re.sub(r"\{([^,{}]*)(?:,[^{}]*)?\}", r"\1", value)
    return value.replace("**", "dir/sub").replace("*", "x").replace("?", "x")
