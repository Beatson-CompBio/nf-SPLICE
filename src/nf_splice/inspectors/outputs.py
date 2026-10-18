"""Read a previously published output catalogue as evidence.

nf-splice does not guess outputs (ADR-0068): the catalogue is authored. The
only outputs read from a repository are those people already published in
``splice/outputs.yaml``, mapped key by documented key into the draft shape.
Published routes are analysed separately (:mod:`nf_splice.inspectors.routes`)
as evidence to browse, never turned into entries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml  # type: ignore[import-untyped]

_KEY = re.compile(r"[^a-z0-9]+")
#: A format identifier as the contract defines it (any lower-case name).
_FORMAT = re.compile(r"^[a-z0-9][a-z0-9._+-]*$")


def _safe_key(value: str) -> str:
    key = _KEY.sub("_", value.lower()).strip("_")
    if not key:
        key = "output"
    if not key[0].isalpha():
        key = f"output_{key}"
    return key


#: Scopes of earlier, pre-0.3.0 catalogues mapped to 0.3.0 scopes. A
#: ``cohort`` output there belonged to one whole job (ADR-0027).
_LEGACY_SCOPES = {"cohort": "job", "job": "job", "sample": "sample", "run": "run"}


@dataclass(frozen=True, slots=True)
class PublishedCatalogue:
    """A previously published ``splice/outputs.yaml``, read as evidence.

    ``outputs`` are in the shape of ``outputs.draft.yaml`` entries; values the
    0.3.0 contract cannot hold (an unknown format or scope) are dropped and
    listed in ``notes`` rather than guessed.
    """

    location: str
    format: str
    outputs: tuple[dict[str, object], ...]
    categories: dict[str, dict[str, str]]
    notes: tuple[str, ...]
    #: The published ``analysis_output_schema_version`` (X.Y.Z), if any.
    schema_version: str | None = None


def _listed(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    return [str(value)] if value is not None else []


def published_catalogue(root: Path) -> PublishedCatalogue | None:
    """The catalogue of a SPLICE bundle published in this repository.

    It is earlier authoring state to import and edit, never evidence of what
    the pipeline scientifically does (ADR-0068).
    """
    path = root / "splice" / "outputs.yaml"
    if not path.is_file() or path.is_symlink():
        return None
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError):
        return None
    if not isinstance(loaded, dict) or not isinstance(loaded.get("outputs"), list):
        return None
    layout = "0.3.0" if "catalogue_format_version" in loaded else "earlier (pre-0.3.0)"
    location = path.relative_to(root).as_posix()
    notes: list[str] = []
    outputs: list[dict[str, object]] = []
    for index, output in enumerate(loaded["outputs"]):
        if not isinstance(output, dict) or not output.get("key"):
            continue
        where = f"{location} outputs[{index}]"
        formats = [item for item in _listed(output.get("format")) if item]
        dropped = [item for item in formats if not _FORMAT.fullmatch(item)]
        if dropped:
            notes.append(f"{where}: format(s) {dropped} are not format identifiers")
        scopes = []
        for item in _listed(output.get("scope")):
            mapped = _LEGACY_SCOPES.get(item)
            if mapped is None:
                notes.append(f"{where}: scope {item!r} has no 0.3.0 equivalent")
            elif mapped not in scopes:
                scopes.append(mapped)
        labels = output.get("labels")
        entry: dict[str, object] = {
            "key": _safe_key(str(output["key"])),
            "title": output.get("title"),
            "description": output.get("description"),
            "category": output.get("category"),
            "formats": [item for item in formats if _FORMAT.fullmatch(item)],
            "scopes": scopes,
            "entity_types": [
                item
                for item in _listed(output.get("entity_type")) or ["file"]
                if item in {"file", "directory"}
            ],
            "path_patterns": _listed(output.get("path_patterns")),
        }
        if output.get("stage"):
            entry["stage"] = str(output["stage"])
        label_items = (
            [{"name": str(k), "value": str(v)} for k, v in sorted(labels.items())]
            if isinstance(labels, dict)
            else []
        )
        if output.get("aligner") and not any(
            item["name"] == "aligner" for item in label_items
        ):
            label_items.append({"name": "aligner", "value": str(output["aligner"])})
        if label_items:
            entry["labels"] = label_items
        outputs.append(entry)
    categories: dict[str, dict[str, str]] = {}
    raw_categories = loaded.get("categories")
    items: list[tuple[object, object]] = []
    if isinstance(raw_categories, dict):
        items = list(raw_categories.items())
    elif isinstance(raw_categories, list):
        items = [
            (item.get("key"), item) for item in raw_categories if isinstance(item, dict)
        ]
    for key, details in items:
        if isinstance(key, str) and isinstance(details, dict):
            categories[key] = {
                name: str(details[name])
                for name in ("title", "description")
                if details.get(name)
            }
    version = loaded.get("analysis_output_schema_version")
    return PublishedCatalogue(
        location,
        layout,
        tuple(outputs),
        categories,
        tuple(notes),
        str(version)
        if isinstance(version, str) and re.fullmatch(r"\d+\.\d+\.\d+", version)
        else None,
    )
