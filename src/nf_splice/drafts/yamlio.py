"""Restricted YAML 1.2 for editable drafts, preserving human comments.

Drafts are parsed with YAML 1.2 core-schema semantics and must represent a
JSON-compatible document: no aliases/anchors, no custom or language tags, no
duplicate keys, no non-string keys, a single document, and no unquoted
timestamps. Edits are applied as targeted operations on the round-trip node
tree so comments and formatting of untouched content survive.
"""

from __future__ import annotations

import datetime
import io
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq, TaggedScalar
from ruamel.yaml.error import MarkedYAMLError, YAMLError
from ruamel.yaml.events import (
    AliasEvent,
    CollectionStartEvent,
    DocumentStartEvent,
    ScalarEvent,
)
from ruamel.yaml.scalarstring import DoubleQuotedScalarString

from nf_splice.drafts.patch import (
    ABSENT,
    JsonValue,
    PatchConflictError,
    PatchOp,
    merge,
    resolve,
    split,
)

_CORE_TAGS = frozenset(
    f"tag:yaml.org,2002:{name}"
    for name in ("str", "int", "float", "bool", "null", "map", "seq")
)
_SHORT_CORE_TAGS = frozenset(
    f"!!{name}" for name in ("str", "int", "float", "bool", "null", "map", "seq")
)
_YAML11_AMBIGUOUS = re.compile(
    r"^(?:y|Y|yes|Yes|YES|n|N|no|No|NO|on|On|ON|off|Off|OFF|"
    r"[-+]?0[0-9_]+|[-+]?[0-9][0-9_]*(?::[0-5]?[0-9])+(?:\.[0-9_]*)?|"
    r"[0-9]{4}-[0-9]{1,2}-[0-9]{1,2}.*|~|null|Null|NULL|true|True|TRUE|"
    r"false|False|FALSE|[-+]?(?:\.inf|\.Inf|\.INF)|\.nan|\.NaN|\.NAN|"
    r"[-+]?(?:[0-9][0-9_]*)?(?:\.[0-9_]*)?(?:[eE][-+]?[0-9]+)?|"
    r"0x[0-9a-fA-F_]+|0o[0-7_]+|0b[01_]+)$"
)


class DraftSyntaxError(ValueError):
    """A draft that cannot be parsed safely; the file is left untouched."""

    def __init__(
        self, message: str, line: int | None = None, column: int | None = None
    ):
        location = (
            f"line {line}" + (f", column {column}" if column else "") if line else ""
        )
        super().__init__(f"{location}: {message}" if location else message)
        self.line = line
        self.column = column
        self.detail = message


@dataclass(frozen=True, slots=True)
class YamlDraft:
    """A parsed draft: its round-trip node tree, JSON data and lint warnings."""

    node: Any
    data: JsonValue
    warnings: tuple[str, ...]


def _yaml() -> YAML:
    parser = YAML(typ="rt")
    parser.preserve_quotes = True
    parser.allow_duplicate_keys = False
    parser.width = 4096
    parser.indent(mapping=2, sequence=4, offset=2)
    return parser


def _mark(error: MarkedYAMLError) -> tuple[int | None, int | None]:
    mark = error.problem_mark or error.context_mark
    if mark is None:
        return None, None
    return mark.line + 1, mark.column + 1


def _check_events(text: str) -> list[str]:
    warnings: list[str] = []
    documents = 0
    for event in _yaml().parse(text):
        line = event.start_mark.line + 1 if event.start_mark else None
        if isinstance(event, DocumentStartEvent):
            documents += 1
            if documents > 1:
                raise DraftSyntaxError(
                    "a draft must contain exactly one document", line
                )
        if isinstance(event, AliasEvent):
            raise DraftSyntaxError("YAML aliases are not permitted in drafts", line)
        if isinstance(event, ScalarEvent | CollectionStartEvent):
            if event.anchor is not None:
                raise DraftSyntaxError("YAML anchors are not permitted in drafts", line)
            tag = getattr(event, "tag", None)
            if tag is not None and str(tag) not in _CORE_TAGS | _SHORT_CORE_TAGS:
                raise DraftSyntaxError(
                    f"YAML tag {tag} is not permitted in drafts", line
                )
        if (
            isinstance(event, ScalarEvent)
            and event.style is None
            and event.value
            and re.fullmatch(
                r"(?:y|Y|yes|Yes|YES|n|N|no|No|NO|on|On|ON|off|Off|OFF|[-+]?0[0-9]+)",
                event.value,
            )
        ):
            warnings.append(
                f"line {line}: unquoted {event.value!r} is read with YAML 1.2 "
                "semantics; quote it if a YAML 1.1 reader must agree"
            )
    return warnings


def to_plain(node: Any, path: str = "") -> JsonValue:
    """Convert a round-trip node tree into plain JSON-compatible values."""
    if isinstance(node, TaggedScalar):
        tag = str(node.tag)
        if tag not in {"tag:yaml.org,2002:str", "!!str"}:
            raise DraftSyntaxError(f"{path or '/'}: unsupported tagged scalar {tag}")
        return str(node.value)
    if isinstance(node, Mapping):
        result: dict[str, JsonValue] = {}
        for key, value in node.items():
            if not isinstance(key, str):
                raise DraftSyntaxError(f"{path or '/'}: mapping keys must be strings")
            result[str(key)] = to_plain(value, f"{path}/{key}")
        return result
    if isinstance(node, list):
        return [to_plain(item, f"{path}/{index}") for index, item in enumerate(node)]
    if isinstance(node, bool) or node is None:
        return node
    if isinstance(node, datetime.date | datetime.datetime):
        raise DraftSyntaxError(
            f"{path or '/'}: unquoted timestamps are not JSON values; quote the value"
        )
    if isinstance(node, int):
        return int(node)
    if isinstance(node, float):
        if math.isnan(node) or math.isinf(node):
            raise DraftSyntaxError(
                f"{path or '/'}: NaN and infinity are not JSON values"
            )
        return float(node)
    if isinstance(node, str):
        return str(node)
    raise DraftSyntaxError(
        f"{path or '/'}: unsupported value of type {type(node).__name__}"
    )


def to_node(value: JsonValue) -> Any:
    """Build round-trip nodes for plain values, quoting ambiguous strings."""
    if isinstance(value, Mapping):
        mapping = CommentedMap()
        for key, item in value.items():
            mapping[str(key)] = to_node(item)
        return mapping
    if isinstance(value, list | tuple):
        sequence = CommentedSeq()
        sequence.extend(to_node(item) for item in value)
        return sequence
    if isinstance(value, str) and (
        value == ""
        or _YAML11_AMBIGUOUS.fullmatch(value)
        or value != value.strip()
        or value[:1] in "!&*?|>'\"%@`{[#,-:"
        or ": " in value
        or " #" in value
    ):
        return DoubleQuotedScalarString(value)
    return value


def load_yaml_draft(text: str) -> YamlDraft:
    """Parse and validate one draft without modifying it."""
    try:
        warnings = _check_events(text)
        node = _yaml().load(text)
    except DraftSyntaxError:
        raise
    except MarkedYAMLError as error:
        line, column = _mark(error)
        raise DraftSyntaxError(str(error.problem or error), line, column) from error
    except YAMLError as error:
        raise DraftSyntaxError(str(error)) from error
    return YamlDraft(node=node, data=to_plain(node), warnings=tuple(warnings))


def dump_yaml_node(node: Any) -> str:
    """Serialise a node tree deterministically."""
    buffer = io.StringIO()
    _yaml().dump(node, buffer)
    return buffer.getvalue()


def dump_yaml_data(value: JsonValue, *, header: Sequence[str] = ()) -> str:
    """Serialise plain data as a new draft with optional leading comment lines."""
    node = to_node(value)
    text = dump_yaml_node(node)
    if header:
        text = "".join(f"# {line}".rstrip() + "\n" for line in header) + text
    return text


def _node_parent(root: Any, path: str) -> tuple[Any, str]:
    tokens = split(path)
    current = root
    for token in tokens[:-1]:
        current = current[int(token)] if isinstance(current, list) else current[token]
    return current, tokens[-1]


def apply_ops_to_node(
    root: Any, operations: Sequence[PatchOp]
) -> tuple[Any, JsonValue]:
    """Apply merge-checked operations to a round-trip tree in place.

    Raises ``PatchConflictError`` before touching the tree if any operation
    overlaps a change it was not planned against.
    """
    plain = to_plain(root)
    expected_result, found = merge(plain, operations)
    if found:
        raise PatchConflictError(found)
    for operation in operations:
        if operation.path == "":
            root = to_node(operation.value)
            plain = to_plain(root)
            continue
        actual = resolve(plain, operation.path)
        target = ABSENT if operation.op == "remove" else operation.value
        tokens = split(operation.path)
        insertion = operation.op == "add" and (
            tokens[-1].isdigit() or tokens[-1] == "-"
        )
        if not insertion and actual == target and type(actual) is type(target):
            continue
        parent, token = _node_parent(root, operation.path)
        if isinstance(parent, list):
            index = len(parent) if token == "-" else int(token)
            if insertion:
                parent.insert(index, to_node(operation.value))
            elif operation.op == "replace":
                parent[index] = to_node(operation.value)
            else:
                del parent[index]
        elif operation.op == "remove":
            del parent[token]
        else:
            parent[token] = to_node(operation.value)
        plain = to_plain(root)
    if plain != expected_result:
        raise AssertionError("round-trip patch diverged from planned result")
    return root, plain
