"""JSON-pointer patches whose operations carry the value they expect to replace.

Every operation records the value it observed (``expected``) when it was
planned. Applying it to the *current* document succeeds only where that value
is still present, so independent concurrent edits are preserved and
overlapping edits are reported as conflicts. This is a three-way merge whose
base is carried by the patch itself rather than by a stored copy of the file.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

JsonValue = Any


class _Absent:
    """Sentinel for a location that does not exist."""

    _instance: _Absent | None = None

    def __new__(cls) -> _Absent:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "ABSENT"


ABSENT = _Absent()
PatchKind = Literal["add", "replace", "remove"]


class PatchError(ValueError):
    """Raised for a malformed pointer or an impossible operation."""


@dataclass(frozen=True, slots=True)
class PatchConflict:
    """A location whose current value differs from the planned base value."""

    path: str
    expected: JsonValue
    actual: JsonValue


class PatchConflictError(PatchError):
    """Raised when a patch overlaps a change made after it was planned."""

    def __init__(self, conflicts: Sequence[PatchConflict]) -> None:
        self.conflicts = tuple(conflicts)
        paths = ", ".join(item.path or "/" for item in self.conflicts)
        super().__init__(f"conflicting concurrent change at {paths}")


@dataclass(frozen=True, slots=True)
class PatchOp:
    """One field-level change with the value it was planned against."""

    op: PatchKind
    path: str
    value: JsonValue = None
    expected: JsonValue = ABSENT

    def to_json(self) -> dict[str, JsonValue]:
        """Return a JSON-compatible representation (ABSENT is omitted)."""
        document: dict[str, JsonValue] = {"op": self.op, "path": self.path}
        if self.op != "remove":
            document["value"] = copy.deepcopy(self.value)
        if self.expected is not ABSENT:
            document["expected"] = copy.deepcopy(self.expected)
        return document

    @classmethod
    def from_json(cls, document: Mapping[str, JsonValue]) -> PatchOp:
        """Load a serialised operation, validating its shape."""
        kind = document.get("op")
        path = document.get("path")
        if kind not in {"add", "replace", "remove"} or not isinstance(path, str):
            raise PatchError(f"invalid patch operation {dict(document)!r}")
        if path and not path.startswith("/"):
            raise PatchError(f"patch path must be a JSON pointer: {path!r}")
        return cls(
            op=kind,
            path=path,
            value=copy.deepcopy(document.get("value")),
            expected=copy.deepcopy(document["expected"])
            if "expected" in document
            else ABSENT,
        )


def escape(token: str) -> str:
    """Escape one JSON-pointer reference token."""
    return token.replace("~", "~0").replace("/", "~1")


def pointer(*tokens: str | int) -> str:
    """Build a JSON pointer from raw tokens."""
    return "".join(f"/{escape(str(item))}" for item in tokens)


def split(path: str) -> list[str]:
    """Split a JSON pointer into unescaped reference tokens."""
    if path == "":
        return []
    if not path.startswith("/"):
        raise PatchError(f"invalid JSON pointer {path!r}")
    return [item.replace("~1", "/").replace("~0", "~") for item in path[1:].split("/")]


def resolve(document: JsonValue, path: str) -> JsonValue:
    """Return the value at ``path`` or ``ABSENT``."""
    current = document
    for token in split(path):
        if isinstance(current, Mapping):
            if token not in current:
                return ABSENT
            current = current[token]
        elif isinstance(current, list):
            if not token.isdigit() or int(token) >= len(current):
                return ABSENT
            current = current[int(token)]
        else:
            return ABSENT
    return current


def _parent(document: JsonValue, path: str) -> tuple[Any, str]:
    tokens = split(path)
    if not tokens:
        raise PatchError("the document root cannot be added or removed")
    parent = resolve(document, "".join(f"/{escape(item)}" for item in tokens[:-1]))
    if parent is ABSENT or not isinstance(parent, Mapping | list):
        raise PatchError(f"parent of {path!r} does not exist")
    return parent, tokens[-1]


def apply_one(document: JsonValue, operation: PatchOp) -> JsonValue:
    """Apply a single operation to a JSON-compatible tree (mutating containers)."""
    if operation.path == "":
        if operation.op != "replace":
            raise PatchError("only replace may target the document root")
        return copy.deepcopy(operation.value)
    parent, token = _parent(document, operation.path)
    if isinstance(parent, list):
        if token == "-":
            index = len(parent)
        elif token.isdigit():
            index = int(token)
        else:
            raise PatchError(f"invalid list index in {operation.path!r}")
        if operation.op == "add":
            if index > len(parent):
                raise PatchError(f"list index out of range in {operation.path!r}")
            parent.insert(index, copy.deepcopy(operation.value))
        elif index >= len(parent):
            raise PatchError(f"list index out of range in {operation.path!r}")
        elif operation.op == "replace":
            parent[index] = copy.deepcopy(operation.value)
        else:
            del parent[index]
        return document
    if operation.op == "remove":
        if token not in parent:
            raise PatchError(f"cannot remove absent {operation.path!r}")
        del parent[token]
    else:
        parent[token] = copy.deepcopy(operation.value)
    return document


def _is_insertion(operation: PatchOp) -> bool:
    tokens = split(operation.path)
    return (
        operation.op == "add"
        and bool(tokens)
        and (tokens[-1].isdigit() or tokens[-1] == "-")
    )


def merge(
    document: JsonValue, operations: Sequence[PatchOp]
) -> tuple[JsonValue, list[PatchConflict]]:
    """Apply operations to a copy and report every overlapping change.

    Operations are evaluated sequentially. For each mapping or replacement
    location the current value must equal the planned base (``expected``);
    a location already holding the planned new value is treated as applied.
    List insertions are positional and need only an existing parent.
    """
    working = copy.deepcopy(document)
    found: list[PatchConflict] = []
    for operation in operations:
        if _is_insertion(operation):
            try:
                working = apply_one(working, operation)
            except PatchError:
                found.append(
                    PatchConflict(
                        operation.path, ABSENT, resolve(working, operation.path)
                    )
                )
            continue
        actual = resolve(working, operation.path)
        target = ABSENT if operation.op == "remove" else operation.value
        if actual == target and type(actual) is type(target):
            continue
        if actual != operation.expected:
            found.append(PatchConflict(operation.path, operation.expected, actual))
            continue
        try:
            working = apply_one(working, operation)
        except PatchError:
            found.append(PatchConflict(operation.path, operation.expected, actual))
    return working, found


def conflicts(
    document: JsonValue, operations: Sequence[PatchOp]
) -> list[PatchConflict]:
    """Return the conflicts ``operations`` would meet on ``document``."""
    return merge(document, operations)[1]


def apply(document: JsonValue, operations: Sequence[PatchOp]) -> JsonValue:
    """Return a patched deep copy, or raise ``PatchConflictError``."""
    result, found = merge(document, operations)
    if found:
        raise PatchConflictError(found)
    return result


def diff(old: JsonValue, new: JsonValue, path: str = "") -> list[PatchOp]:
    """Return minimal field-level operations turning ``old`` into ``new``.

    Mappings are compared key by key. Lists of equal length are compared
    element by element; an appended tail becomes ``add`` operations; any other
    list change replaces the whole list (with the old list as its base).
    """
    if old == new and type(old) is type(new):
        return []
    if isinstance(old, Mapping) and isinstance(new, Mapping):
        operations: list[PatchOp] = []
        for key in old:
            child = f"{path}/{escape(str(key))}"
            if key not in new:
                operations.append(
                    PatchOp("remove", child, expected=copy.deepcopy(old[key]))
                )
            else:
                operations.extend(diff(old[key], new[key], child))
        for key in new:
            if key not in old:
                operations.append(
                    PatchOp(
                        "add", f"{path}/{escape(str(key))}", copy.deepcopy(new[key])
                    )
                )
        return operations
    if isinstance(old, list) and isinstance(new, list):
        if len(old) == len(new):
            operations = []
            for index, (before, after) in enumerate(zip(old, new, strict=True)):
                operations.extend(diff(before, after, f"{path}/{index}"))
            return operations
        if len(new) > len(old) and new[: len(old)] == old:
            return [
                PatchOp("add", f"{path}/{index}", copy.deepcopy(new[index]))
                for index in range(len(old), len(new))
            ]
    return [PatchOp("replace", path, copy.deepcopy(new), expected=copy.deepcopy(old))]
