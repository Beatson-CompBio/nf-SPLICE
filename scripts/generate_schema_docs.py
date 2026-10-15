"""Generate docs/schemas/<family>/README.md field references.

python scripts/generate_schema_docs.py          # write
python scripts/generate_schema_docs.py --check  # fail if stale/undocumented
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from nf_splice.contracts import families, meta_schema, release

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs" / "schemas"

#: Plain-language names for the patterns the definitions use.
_PATTERNS = {
    r"^[a-z0-9][a-z0-9-]*$": "lower-case letters, digits and `-`",
    r"^[a-z][a-z0-9_-]*$": "lower-case letter, then letters, digits, `_` or `-`",
    r"^[a-z][a-z0-9_]*$": "lower-case letter, then letters, digits or `_`",
    r"^[0-9]+\.[0-9]+\.[0-9]+$": "version `X.Y.Z`",
    r"^(?!/)(?!.*(?:^|/)\.\.(?:/|$))[A-Za-z0-9._/-]+$": (
        "relative path inside the bundle (no leading `/`, no `..`)"
    ),
    r"^https?://": "http or https URL",
    r"^https://": "https URL",
    r"^[0-9a-f]{64}$": "64 lower-case hexadecimal characters",
    r"^sha256:[0-9a-f]{64}$": "`sha256:` followed by 64 hexadecimal characters",
    r"^container-[0-9a-f]{12}$": "`container-` followed by 12 hexadecimal characters",
    r"^configs/[a-z][a-z0-9_-]*\.config$": "`configs/<profile id>.config`",
    r"^10\.[0-9]{4,9}/\S+$": "DOI such as `10.5281/zenodo.123`",
    r"^\^.*\$$": "regular expression anchored with `^` and `$`",
    r"^https://orcid\.org/[0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9]{3}[0-9X]$": (
        "`https://orcid.org/` followed by an ORCID iD"
    ),
}
_FORMATS = {
    "uri": "URL",
    "date-time": "date-time (RFC 3339)",
    "email": "e-mail address",
}
_PARAMETER = re.compile(r"^(?:\$defs\.\*\.properties|properties)\.\*\.")


def _resolve(schema: dict[str, Any], root: dict[str, Any]) -> dict[str, Any]:
    if "$ref" in schema:
        return dict(root["$defs"][schema["$ref"].rsplit("/", 1)[-1]])
    return schema


Row = tuple[str, dict[str, Any], bool]


def rows(schema: dict[str, Any], root: dict[str, Any], prefix: str = "") -> list[Row]:
    found = []
    schema = _resolve(schema, root)
    required = set(schema.get("required", []))
    for name, child in (schema.get("properties") or {}).items():
        path = f"{prefix}.{name}" if prefix else name
        if child is False:
            found.append((path, {"forbidden": True}, False))
            continue
        target = _resolve(child, root)
        found.append((path, target, name in required))
        if target.get("type") == "array" and isinstance(target.get("items"), dict):
            found.extend(rows(target["items"], root, f"{path}[]"))
        elif isinstance(target.get("additionalProperties"), dict):
            found.extend(rows(target["additionalProperties"], root, f"{path}.*"))
        else:
            found.extend(rows(target, root, path))
    return found


def _string(schema: dict[str, Any]) -> str:
    pattern = schema.get("pattern")
    if pattern is not None:
        return _PATTERNS.get(pattern, f"string matching `{pattern}`")
    if schema.get("format") in _FORMATS:
        return _FORMATS[schema["format"]]
    return "non-empty string" if schema.get("minLength") else "string"


def kind(schema: dict[str, Any], root: dict[str, Any] | None = None) -> str:
    """Describe a definition's type in words."""
    if schema.get("forbidden"):
        return "must not appear"
    if "const" in schema:
        return f"always `{json.dumps(schema['const'])}`"
    if "enum" in schema:
        return "one of " + ", ".join(f"`{item}`" for item in schema["enum"])
    value = schema.get("type")
    if value == "string":
        return _string(schema)
    if value == "integer":
        minimum = schema.get("minimum")
        return f"integer ≥ {minimum}" if minimum is not None else "integer"
    if value == "boolean":
        return "boolean"
    if value == "array":
        items = schema.get("items")
        item = (
            _resolve(items, root or {})
            if isinstance(items, dict) and root is not None
            else items
        )
        if isinstance(item, dict) and item.get("type") == "object":
            text = "array of objects"
        elif isinstance(item, dict) and ("enum" in item or "const" in item):
            values = item.get("enum", [item.get("const")])
            text = "array of " + ", ".join(f"`{value}`" for value in values)
        elif isinstance(item, dict) and item.get("type") == "string":
            base = _string(item)
            text = {
                "string": "array of strings",
                "non-empty string": "array of non-empty strings",
            }.get(base, f"array of strings: {base}")
        elif isinstance(item, dict) and item:
            text = f"array of {kind(item, root)}"
        else:
            text = "array"
        extras = []
        if schema.get("minItems"):
            extras.append(f"at least {schema['minItems']}")
        if schema.get("uniqueItems"):
            extras.append("no duplicates")
        return text + (f" ({', '.join(extras)})" if extras else "")
    if value == "object":
        if isinstance(schema.get("additionalProperties"), dict):
            return "object keyed by name"
        if schema.get("minProperties"):
            return f"object (at least {schema['minProperties']} key)"
        return "object"
    return "any JSON value"


def _normalise(key: str, path: str) -> str:
    return _PARAMETER.sub("<parameter>.", path) if key == "inputs" else path


def _note(notes: dict[str, Any], key: str, path: str) -> dict[str, str] | None:
    for source in (notes.get(key, {}), notes["common"]):
        if path in source:
            value = source[path]
            return {"description": value} if isinstance(value, str) else dict(value)
    return None


def _parent(path: str) -> str:
    return path.rsplit(".", 1)[0] if "." in path else ""


def _leaf(path: str) -> str:
    return path.rsplit(".", 1)[-1]


def _heading(path: str) -> str:
    if not path:
        return "Top-level keys"
    if path.endswith("[]"):
        return f"`{path}` (each item)"
    if path.endswith(".*"):
        return f"`{path}` (each entry)"
    return f"`{path}`"


def render(key: str, notes: dict[str, Any]) -> tuple[str, list[str]]:
    item = next(value for value in families() if value.key == key)
    schema = meta_schema(item.id)
    version = dict(release().contracts)[item.id]
    family = notes.get(key, {})
    missing: list[str] = []
    sections: dict[str, list[str]] = {}
    closed: dict[str, bool] = {"": schema.get("additionalProperties") is False}
    seen: set[str] = set()
    for raw, child, required in rows(schema, schema):
        path = _normalise(key, raw)
        if path in seen:
            continue
        seen.add(path)
        note = _note(notes, key, path)
        if note is None:
            missing.append(path)
            note = {"description": ""}
        description = note["description"]
        if note.get("privacy"):
            description = f"**{note['privacy']}** {description}"
        sections.setdefault(_parent(path), []).append(
            f"| `{_leaf(path)}` | {kind(child, schema)} | "
            f"{'yes' if required else 'no'} | {description} |"
        )
        target = child
        if child.get("type") == "array" and isinstance(child.get("items"), dict):
            target, path = _resolve(child["items"], schema), f"{path}[]"
        elif isinstance(child.get("additionalProperties"), dict):
            target, path = child["additionalProperties"], f"{path}.*"
        closed[path] = target.get("additionalProperties") is False
    example = DOCS / key / f"v{version}" / "example.json"
    lines = [
        f"# `{item.path}`",
        "",
        f"{item.title}.",
        "",
        "| | |",
        "| --- | --- |",
        f"| Contract family | `{item.id}` |",
        f"| Revision | `{version}` |",
        f"| Formal schema | [`v{version}/schema.json`](v{version}/schema.json) |",
        f"| Example | [`v{version}/example.json`](v{version}/example.json) |",
        "",
        family.get("_about", "").strip(),
        "",
        "## Fields",
        "",
        "A key marked required must be present whenever the object that",
        "contains it is present. A section whose object accepts no other",
        "keys says so.",
        "",
    ]
    intros = family.get("_sections", {})
    for parent, table in sections.items():
        lines += [f"### {_heading(parent)}", ""]
        intro = intros.get(parent, intros.get(parent.removesuffix(".*")))
        if intro is None and parent:
            note = _note(notes, key, parent.removesuffix("[]").removesuffix(".*"))
            intro = note["description"] if note else None
        text = intro or ""
        if closed.get(parent):
            scope = "top-level keys" if not parent else "keys"
            text = f"{text} No other {scope} are allowed.".strip()
        if text:
            lines += [text, ""]
        lines += [
            "| Key | Type | Required | Description |",
            "| --- | --- | --- | --- |",
            *table,
            "",
        ]
    lines += [
        "## Example",
        "",
        "<details>",
        f"<summary>Complete <code>{item.path}</code></summary>",
        "",
        "```json",
        example.read_text(encoding="utf-8").rstrip("\n"),
        "```",
        "",
        "</details>",
        "",
        "---",
        "",
        "Generated by `scripts/generate_schema_docs.py` from the packaged",
        "definition and `docs/schemas/fields.yaml`. Edit those, not this page.",
        "",
    ]
    return "\n".join(lines), missing


def main(argv: list[str]) -> int:
    notes = yaml.safe_load((DOCS / "fields.yaml").read_text(encoding="utf-8"))
    check = "--check" in argv
    problems = []
    for item in families():
        text, missing = render(item.key, notes)
        problems.extend(f"{item.key}: undocumented {path}" for path in missing)
        target = DOCS / item.key / "README.md"
        if check:
            if not target.is_file() or target.read_text(encoding="utf-8") != text:
                problems.append(f"{target.relative_to(ROOT)} is stale")
        else:
            target.write_text(text, encoding="utf-8")
    for problem in problems:
        print(problem, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
