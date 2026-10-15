"""Read-only discovery of workflow modules from ``modules.json`` and meta files."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]


class ModuleDiscoveryError(ValueError):
    """Raised when module evidence is missing or invalid."""


_SEMVER = re.compile(r"^v?(\d+(?:\.\d+)+(?:[-+][A-Za-z0-9_.-]+)?)")


def module_items(root: Path) -> tuple[dict[str, Any], ...]:
    path = root / "modules.json"
    if not path.is_file():
        raise ModuleDiscoveryError("modules.json is required for component discovery")
    try:
        loaded: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ModuleDiscoveryError(f"invalid modules.json: {error}") from error
    if not isinstance(loaded, dict) or not isinstance(loaded.get("items"), list):
        raise ModuleDiscoveryError("modules.json must contain an items array")
    return tuple(
        item
        for item in loaded["items"]
        if isinstance(item, dict) and item.get("kind") == "module"
    )


def module_metadata(path: Path) -> dict[str, Any]:
    for name in ("meta.yml", "meta.yaml"):
        candidate = path / name
        if not candidate.is_file():
            continue
        try:
            loaded: object = yaml.safe_load(candidate.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError):
            return {}
        return loaded if isinstance(loaded, dict) else {}
    return {}


def tool_name(metadata: dict[str, Any], item: dict[str, Any], path: str) -> str:
    tools = metadata.get("tools")
    if isinstance(tools, list):
        for tool in tools:
            if isinstance(tool, dict) and tool:
                return str(next(iter(tool)))
    detected = item.get("tool")
    if isinstance(detected, str) and detected:
        return detected
    return Path(path).name


def conda_packages(path: Path) -> tuple[str, ...]:
    environment = path / "environment.yml"
    if not environment.is_file():
        return ()
    try:
        loaded: object = yaml.safe_load(environment.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError):
        return ()
    if not isinstance(loaded, dict) or not isinstance(loaded.get("dependencies"), list):
        return ()
    return tuple(
        sorted(item for item in loaded["dependencies"] if isinstance(item, str))
    )


def detected_versions(
    item: dict[str, Any], path: str, uris: tuple[str, ...]
) -> tuple[str, ...]:
    values: set[str] = set()
    detected = item.get("tool_version")
    if isinstance(detected, str) and detected:
        values.add(detected)
    path_version = _SEMVER.match(Path(path).name)
    if path_version:
        values.add(path_version.group(1))
    for uri in uris:
        basename = uri.rsplit("/", 1)[-1]
        if ":" not in basename:
            continue
        match = _SEMVER.match(basename.split(":", 1)[1])
        if match:
            values.add(match.group(1))
    return tuple(sorted(values))
