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
#: A Bioconda/BioContainers image tag is ``<tool version>--<build string>``,
#: for example ``0.12.1--hdfd78af_0``; the build string is not a tool version.
_IMAGE_BUILD = re.compile(r"--[A-Za-z0-9_.]+$")


def module_items(root: Path) -> tuple[dict[str, Any], ...]:
    """Modules listed in ``modules.json``.

    Two layouts are read: nf-core's own (``repos`` → repository → ``modules``
    → install directory → module name), plus local modules found under
    ``modules/local/``, which nf-core does not list; and a flat ``items`` array
    of ``{"kind": "module", "path": ...}`` entries.
    """
    path = root / "modules.json"
    if not path.is_file():
        raise ModuleDiscoveryError("modules.json is required for component discovery")
    try:
        loaded: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ModuleDiscoveryError(f"invalid modules.json: {error}") from error
    if isinstance(loaded, dict) and isinstance(loaded.get("items"), list):
        return tuple(
            item
            for item in loaded["items"]
            if isinstance(item, dict) and item.get("kind") == "module"
        )
    if isinstance(loaded, dict) and isinstance(loaded.get("repos"), dict):
        return _nf_core_items(root, loaded["repos"])
    raise ModuleDiscoveryError(
        "modules.json must contain nf-core's repos map or an items array"
    )


def _nf_core_items(root: Path, repos: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    found: dict[str, dict[str, Any]] = {}
    for repository, entry in sorted(repos.items()):
        modules = entry.get("modules") if isinstance(entry, dict) else None
        if not isinstance(modules, dict):
            continue
        for install_directory, listed in sorted(modules.items()):
            if not isinstance(listed, dict):
                continue
            for name, details in sorted(listed.items()):
                relative = f"modules/{install_directory}/{name}"
                if not (root / relative / "main.nf").is_file():
                    continue
                found[relative] = {
                    "kind": "module",
                    "path": relative,
                    "namespace": install_directory,
                    "name": name.rsplit("/", 1)[-1],
                    "source_repository": repository,
                    "git_sha": details.get("git_sha")
                    if isinstance(details, dict)
                    else None,
                }
    local = root / "modules" / "local"
    if local.is_dir():
        for main_nf in sorted(local.rglob("main.nf")):
            relative = main_nf.parent.relative_to(root).as_posix()
            found.setdefault(
                relative,
                {
                    "kind": "module",
                    "path": relative,
                    "namespace": "local",
                    "name": main_nf.parent.name,
                },
            )
    return tuple(found[key] for key in sorted(found))


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
        tag = _IMAGE_BUILD.sub("", basename.split(":", 1)[1])
        match = _SEMVER.match(tag)
        if match:
            values.add(match.group(1))
    return _consistent(values)


def _consistent(values: set[str]) -> tuple[str, ...]:
    """Drop build suffixes and versions another, more precise one extends.

    ``9.4--cfg-5bee`` is version 9.4 with an image build; ``2.7.11`` is how
    a version pattern reads ``2.7.11b``, and an image tagged ``5.26`` is the
    series of ``5.26.2``. Genuinely different versions are all kept, so a
    real conflict stays visible.
    """
    cleaned = {re.sub(r"--.*$", "", value) for value in values if value}
    kept = set()
    for value in cleaned:
        if not any(
            other != value
            and other.startswith(value)
            and not other[len(value)].isdigit()
            for other in cleaned
        ):
            kept.add(value)
    return tuple(sorted(kept))
