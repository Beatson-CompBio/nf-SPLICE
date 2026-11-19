"""Detect breaking changes between two revisions of a contract definition."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class CompatibilityFinding:
    """One schema change that requires a new revision and a migration."""

    json_pointer: str
    kind: str
    message: str


def _types(schema: Mapping[str, Any]) -> set[str] | None:
    value = schema.get("type")
    if value is None:
        return None
    return {value} if isinstance(value, str) else {str(item) for item in value}


def _walk(
    old: Mapping[str, Any],
    new: Mapping[str, Any],
    pointer: str,
    findings: list[CompatibilityFinding],
) -> None:
    old_types, new_types = _types(old), _types(new)
    if old_types is not None and (new_types is None or not old_types <= new_types):
        if new_types is not None:
            findings.append(
                CompatibilityFinding(
                    pointer,
                    "type_narrowed",
                    f"type changed from {sorted(old_types)} to {sorted(new_types)}",
                )
            )
    if "enum" in old and "enum" in new:
        removed = [item for item in old["enum"] if item not in new["enum"]]
        if removed:
            findings.append(
                CompatibilityFinding(
                    pointer, "enum_narrowed", f"values removed: {removed}"
                )
            )
    if "const" in old and old.get("const") != new.get("const"):
        findings.append(
            CompatibilityFinding(
                pointer, "const_changed", f"{old['const']!r} -> {new.get('const')!r}"
            )
        )
    old_required = set(old.get("required", []))
    added_required = sorted(set(new.get("required", [])) - old_required)
    if added_required:
        findings.append(
            CompatibilityFinding(
                pointer, "required_added", f"newly required: {added_required}"
            )
        )
    old_properties = old.get("properties", {})
    new_properties = new.get("properties", {})
    if isinstance(old_properties, Mapping) and isinstance(new_properties, Mapping):
        for name, old_child in old_properties.items():
            child_pointer = f"{pointer}/properties/{name}"
            if name not in new_properties:
                if new.get("additionalProperties") is False:
                    findings.append(
                        CompatibilityFinding(
                            child_pointer, "property_removed", f"{name!r} was removed"
                        )
                    )
                continue
            if isinstance(old_child, Mapping) and isinstance(
                new_properties[name], Mapping
            ):
                _walk(old_child, new_properties[name], child_pointer, findings)
    if (
        old.get("additionalProperties") is not False
        and new.get("additionalProperties") is False
    ):
        findings.append(
            CompatibilityFinding(
                pointer, "closed", "additional properties are no longer accepted"
            )
        )
    for keyword in ("items", "additionalProperties"):
        if isinstance(old.get(keyword), Mapping) and isinstance(
            new.get(keyword), Mapping
        ):
            _walk(old[keyword], new[keyword], f"{pointer}/{keyword}", findings)
    old_defs, new_defs = old.get("$defs", {}), new.get("$defs", {})
    if isinstance(old_defs, Mapping) and isinstance(new_defs, Mapping):
        for name, old_child in old_defs.items():
            child_pointer = f"{pointer}/$defs/{name}"
            if name not in new_defs:
                findings.append(
                    CompatibilityFinding(
                        child_pointer, "definition_removed", f"{name!r} was removed"
                    )
                )
            elif isinstance(old_child, Mapping) and isinstance(new_defs[name], Mapping):
                _walk(old_child, new_defs[name], child_pointer, findings)


def breaking_changes(
    old: Mapping[str, Any], new: Mapping[str, Any]
) -> tuple[CompatibilityFinding, ...]:
    """Return changes that an existing producer/consumer pair would notice.

    Removals, type or enum narrowing, changed constants, closed objects and new
    requiredness are breaking. Additive optional fields are not reported.
    """
    findings: list[CompatibilityFinding] = []
    _walk(old, new, "", findings)
    return tuple(findings)
