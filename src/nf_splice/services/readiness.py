"""Ingestion readiness as independent dimensions, never one 'passed' bit.

A structurally valid bundle is not automatically a correct scientific
catalogue, a runnable configuration or a classified pipeline. Each dimension
is assessed separately from the published bundle (so a consumer without the
private drafts gets the same answer); only genuinely required conditions
block. Optional metadata, unreviewed heuristic hints and checks that were
never authorised do not.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nf_splice.layout import PUBLISHED_DIR

READY = "ready"
BLOCKED = "blocked"
NOT_ASSESSED = "not_assessed"
DIMENSIONS = (
    "contracts",
    "scientific_classification",
    "runtime_parameters",
    "deployment",
    "provenance",
    "publication",
)


@dataclass(slots=True)
class Dimension:
    """One readiness dimension: its status and what it found."""

    name: str
    status: str = READY
    blockers: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def block(self, message: str) -> None:
        self.status = BLOCKED
        self.blockers.append(message)

    def to_json(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "blockers": list(self.blockers),
            "notes": list(self.notes),
        }


@dataclass(frozen=True, slots=True)
class Readiness:
    """Every dimension, and ingestion readiness as all of them together."""

    dimensions: dict[str, Dimension]

    @property
    def ingestion_ready(self) -> bool:
        return all(item.status != BLOCKED for item in self.dimensions.values()) and (
            self.dimensions["contracts"].status == READY
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "ingestion_ready": self.ingestion_ready,
            "dimensions": {
                name: self.dimensions[name].to_json() for name in DIMENSIONS
            },
        }


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None


def _config_assigns(text: str, name: str) -> bool:
    """Whether a config sets params.<name> (in a params block or directly)."""
    from nf_splice.layers.execution import section_parameters

    if re.search(rf"\bparams\.{re.escape(name)}\s*=(?!=)", text):
        return True
    if any(
        item == name
        for values in section_parameters(text).values()
        for item, _ in values
    ):
        return True
    return bool(
        re.search(
            rf"params\s*\{{[^}}]*?^\s*{re.escape(name)}\s*=(?!=)",
            text,
            re.M | re.S,
        )
    )


def indispensable_parameters(schema: dict[str, Any]) -> list[tuple[str, str]]:
    """(parameter, why) for values a job cannot run without.

    Listed in a ``required`` array, or a sample sheet, with no default.
    """
    from nf_splice.layers.inputs import iter_parameters

    required: set[str] = set(schema.get("required") or [])
    for group in (schema.get("$defs") or {}).values():
        if isinstance(group, dict):
            required.update(group.get("required") or [])
    found = []
    for item in iter_parameters(schema):
        if "default" in item.schema:
            continue
        data = item.schema.get("x-splice-data") or {}
        if item.name in required:
            found.append((item.name, "required by the input contract"))
        elif isinstance(data, dict) and data.get("samplesheet"):
            found.append((item.name, "the sample sheet a job runs on"))
    return found


def _runtime(splice: Path, dimension: Dimension) -> None:
    from nf_splice.layers.inputs import iter_parameters

    schema = _load(splice / "inputs.schema.json")
    profiles = _load(splice / "execution-profiles.json")
    if not isinstance(schema, dict):
        dimension.status = NOT_ASSESSED
        dimension.notes.append("no published input contract")
        return
    default_text = ""
    if isinstance(profiles, dict):
        default = next(
            (
                item
                for item in profiles.get("profiles") or []
                if isinstance(item, dict) and item.get("default")
            ),
            None,
        )
        if default and (splice / str(default.get("config"))).is_file():
            default_text = (splice / str(default["config"])).read_text(
                encoding="utf-8", errors="replace"
            )
    policies = {item.name: item for item in iter_parameters(schema)}
    for name, why in indispensable_parameters(schema):
        parameter = policies[name]
        if parameter.editable_by:
            continue
        if default_text and _config_assigns(default_text, name):
            continue
        dimension.block(
            f"{name} ({why}) has no default, nobody may supply it "
            "(editable_by: []) and the default profile's config does not set it"
        )
    agents = sorted(
        name for name, item in policies.items() if "agent" in (item.editable_by or ())
    )
    if agents:
        dimension.notes.append(
            f"the runtime 'agent' principal may change: {', '.join(agents)}"
        )


def _deployment(splice: Path, dimension: Dimension) -> None:
    components = _load(splice / "components.json")
    profiles = _load(splice / "execution-profiles.json")
    if not isinstance(components, dict):
        dimension.status = NOT_ASSESSED
        dimension.notes.append("no published components")
        return
    containers = {
        str(item.get("id")): item
        for item in components.get("containers") or []
        if isinstance(item, dict)
    }
    if components.get("require_downloadable_images") is True:
        missing = sorted(
            identifier
            for identifier, item in containers.items()
            if not item.get("distribution")
        )
        if missing:
            dimension.block(
                f"{len(missing)} container(s) need a verified downloadable image: "
                + ", ".join(missing[:10])
            )
    unlinked = [
        str(item.get("id"))
        for item in components.get("components") or []
        if isinstance(item, dict) and not item.get("container_id")
    ]
    if unlinked:
        dimension.notes.append(
            f"{len(unlinked)} component(s) name no container: "
            + ", ".join(unlinked[:10])
        )
    default = None
    if isinstance(profiles, dict):
        default = next(
            (
                item
                for item in profiles.get("profiles") or []
                if isinstance(item, dict) and item.get("default")
            ),
            None,
        )
    if default is None:
        dimension.block("no default execution profile is published")
        return
    engine = str(default.get("container_engine"))
    runtime = "docker" if engine in {"docker", "podman"} else engine
    if engine in {"singularity", "apptainer", "docker", "podman"}:
        lacking = sorted(
            identifier
            for identifier, item in containers.items()
            if runtime not in (item.get("source_images") or {})
            and not (
                runtime in {"singularity", "apptainer"} and item.get("distribution")
            )
            and "docker" not in (item.get("source_images") or {})
        )
        if lacking:
            dimension.block(
                f"the default profile uses {engine}, but {len(lacking)} container(s) "
                f"have no {runtime} or OCI source: " + ", ".join(lacking[:10])
            )


def _provenance(splice: Path, dimension: Dimension) -> None:
    from nf_splice.layers.provenance import structural_findings

    crate = _load(splice / "ro-crate-metadata.json")
    bundle = _load(splice / "bundle.json")
    if not isinstance(crate, dict):
        dimension.block("no readable splice/ro-crate-metadata.json")
        return
    for finding in structural_findings(crate):
        if finding.severity.value == "error" or finding.code == "root_property":
            dimension.block(f"RO-Crate: {finding.message}")
    pipeline = (bundle or {}).get("pipeline") or {}
    root = next(
        (
            item
            for item in crate.get("@graph") or []
            if isinstance(item, dict) and item.get("@id") == "./"
        ),
        {},
    )
    if pipeline.get("version") and root.get("version") not in (
        None,
        pipeline.get("version"),
    ):
        dimension.block(
            f"RO-Crate version {root.get('version')!r} differs from the bundle's "
            f"{pipeline.get('version')!r}"
        )
    dimension.notes.append(
        "standards-profile validation (rocrate-validator) runs only as an opt-in check"
    )


def assess_readiness(repository_root: str | Path) -> Readiness:
    """Assess every dimension of the published bundle."""
    from nf_splice.services.lifecycle import CLASSIFICATION_RULES, validate_bundle

    root = Path(repository_root).resolve()
    splice = root / PUBLISHED_DIR
    dimensions = {name: Dimension(name) for name in DIMENSIONS}
    if not (splice / "bundle.json").is_file():
        for item in dimensions.values():
            item.status = NOT_ASSESSED
            item.notes.append("nothing is published yet")
        dimensions["contracts"].block("splice/bundle.json is not published")
        return Readiness(dimensions)
    report = validate_bundle(root)
    for issue in report.issues:
        if issue.severity.value != "error":
            continue
        target = (
            dimensions["scientific_classification"]
            if issue.rule in CLASSIFICATION_RULES
            else dimensions["publication"]
            if issue.rule
            in {"lock", "files", "projection", "draft_marker", "interrupted"}
            else dimensions["contracts"]
        )
        target.block(f"{issue.path}: {issue.message}")
    _runtime(splice, dimensions["runtime_parameters"])
    _deployment(splice, dimensions["deployment"])
    _provenance(splice, dimensions["provenance"])
    catalogue = _load(splice / "outputs.schema.json")
    output_types = (
        ((catalogue or {}).get("x-output-catalog") or {}).get("output_types") or []
        if isinstance(catalogue, dict)
        else []
    )
    if not output_types:
        dimensions["scientific_classification"].block("the output catalogue is empty")
    return Readiness(dimensions)
