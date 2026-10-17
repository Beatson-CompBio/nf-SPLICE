"""Ingestion readiness as independent dimensions, never one 'passed' bit.

A structurally valid bundle is not automatically a correct scientific
catalogue, a runnable configuration or a classified pipeline. Each dimension
is assessed separately from the published bundle (so a consumer without the
private drafts gets the same answer); only genuinely required conditions
block. Optional metadata, unreviewed heuristic hints and checks that were
never authorised do not.

:func:`lifecycle` is the one statement every interface makes about where an
integration stands (ADR-0062): drafts valid, bundle published, scientifically
classified, ready for SPLICE ingestion. Each is a separate fact, and a
successful build is never reported as ingestion readiness.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from nf_splice.layout import PUBLISHED_DIR

if TYPE_CHECKING:
    from nf_splice.services.lifecycle import BundleReport

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
        """Every dimension assessed and ready; not assessed is not ready."""
        return all(item.status == READY for item in self.dimensions.values())

    def reasons(self) -> list[str]:
        """Why the bundle is not ready, one line per blocker, by dimension."""
        found: list[str] = []
        for name in DIMENSIONS:
            item = self.dimensions[name]
            label = name.replace("_", " ")
            found.extend(f"{label}: {text}" for text in item.blockers)
            if item.status == NOT_ASSESSED and not item.blockers:
                found.append(
                    f"{label}: not assessed"
                    + (f" ({item.notes[0]})" if item.notes else "")
                )
        return found

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
        # A null or empty default supplies nothing: nf-core schemas write
        # ``"default": null`` for values a person must give.
        if item.schema.get("default") not in (None, ""):
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
    lock = _load(splice / "nf-splice.lock.json")
    records = (lock or {}).get("distributions") if isinstance(lock, dict) else None
    historical = sorted(
        str(key)
        for key, value in (records or {}).items()
        if isinstance(value, dict) and value.get("verification") == "historical"
    )
    if historical:
        dimension.notes.append(
            f"{len(historical)} image file(s) rest on a historical verification; "
            "whether they are reachable now was not checked "
            "(`nf-splice containers reverify --approve-network`): "
            + ", ".join(historical[:10])
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
    _software(components, engine, dimension)
    if engine in CONTAINER_ENGINES:
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


#: Engines that run each process in a container image.
CONTAINER_ENGINES = frozenset({"singularity", "apptainer", "docker", "podman"})
#: Engines that build each process's environment from its Conda packages.
CONDA_ENGINES = frozenset({"conda", "mamba", "micromamba"})


def _software(components: dict[str, Any], engine: str, dimension: Dimension) -> None:
    """How each component gets its software under the default profile.

    A component with no container and no Conda packages declares nothing:
    it runs with what the execution host provides, which is a valid,
    deliberate choice (shell utilities, Groovy ``exec:`` blocks) and is
    noted. A component that declares only Conda packages cannot get them
    from a container engine: under one, it is a blocker.
    """
    container_free = []
    conda_only = []
    for item in components.get("components") or []:
        if not isinstance(item, dict) or item.get("container_id"):
            continue
        identifier = str(item.get("id"))
        if item.get("conda_packages"):
            conda_only.append(identifier)
        else:
            container_free.append(identifier)
    if container_free:
        dimension.notes.append(
            f"{len(container_free)} component(s) declare no container or Conda "
            "environment and use the execution host's software: "
            + ", ".join(container_free[:10])
        )
    if conda_only and engine in CONTAINER_ENGINES:
        dimension.block(
            f"the default profile uses {engine}, but {len(conda_only)} component(s) "
            "declare only Conda packages and no container, so their tools would "
            "have to be on the execution host: " + ", ".join(conda_only[:10])
        )
    elif conda_only:
        dimension.notes.append(
            f"{len(conda_only)} component(s) use only their Conda packages: "
            + ", ".join(conda_only[:10])
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
        "only nf-splice's structural RO-Crate checks ran; Workflow RO-Crate "
        "standards validation (rocrate-validator) is a separate opt-in check"
    )


def assess_readiness(
    repository_root: str | Path, report: BundleReport | None = None
) -> Readiness:
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
    report = report if report is not None else validate_bundle(root)
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


# ------------------------------------------------------------- lifecycle

DRAFTS_INVALID = "drafts_invalid"
NOT_PUBLISHED = "not_published"
PUBLISHED_NOT_READY = "published_not_ready"
INGESTION_READY = "ingestion_ready"

_HEADLINES = {
    DRAFTS_INVALID: "Drafts do not validate yet; nothing new can be published",
    NOT_PUBLISHED: "Drafts validate, but the bundle is not published",
    PUBLISHED_NOT_READY: "Published, but not ready for SPLICE ingestion",
    INGESTION_READY: "Published and ready for SPLICE ingestion",
}


@dataclass(frozen=True, slots=True)
class Lifecycle:
    """Where an integration stands, as separate facts (ADR-0062).

    ``drafts_valid`` is about the editable drafts; the other facts are about
    the published ``splice/`` bundle. A bundle can be published (for
    further review) while it is not ready for ingestion; it is never
    reported as ready only because it was built.
    """

    drafts_valid: bool | None
    published: bool
    publication_current: bool
    structurally_valid: bool
    scientifically_classified: bool
    readiness: Readiness

    @property
    def ingestion_ready(self) -> bool:
        return (
            self.published
            and self.structurally_valid
            and self.scientifically_classified
            and self.readiness.ingestion_ready
        )

    @property
    def state(self) -> str:
        if self.ingestion_ready:
            return INGESTION_READY
        if self.published:
            return PUBLISHED_NOT_READY
        if self.drafts_valid is False:
            return DRAFTS_INVALID
        return NOT_PUBLISHED

    @property
    def headline(self) -> str:
        text = _HEADLINES[self.state]
        if self.published and self.drafts_valid is False:
            text += "; the drafts have changed and no longer validate"
        elif self.published and not self.publication_current:
            text += "; the published files are not current"
        return text

    def reasons(self) -> list[str]:
        """Actionable reasons the integration is not ready for ingestion."""
        if self.ingestion_ready:
            return []
        if not self.published:
            found = ["publication: nothing is published; run `nf-splice build all`"]
            if self.drafts_valid is False:
                found.insert(
                    0,
                    "drafts: some drafts do not validate; run "
                    "`nf-splice draft validate`",
                )
            return found
        return self.readiness.reasons()

    def to_json(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "headline": self.headline,
            "drafts_valid": self.drafts_valid,
            "published": self.published,
            "publication_current": self.publication_current,
            "structurally_valid": self.structurally_valid,
            "scientifically_classified": self.scientifically_classified,
            "ingestion_ready": self.ingestion_ready,
            "reasons": self.reasons(),
            "dimensions": self.readiness.to_json()["dimensions"],
        }

    def lines(self, limit: int = 20) -> list[str]:
        """Human-readable summary: the headline, then each reason."""
        found = [f"{self.headline}."]
        reasons = self.reasons()
        found.extend(f"  - {item}" for item in reasons[:limit])
        if len(reasons) > limit:
            found.append(f"  - ... and {len(reasons) - limit} more")
        return found


def lifecycle(
    repository_root: str | Path, *, drafts_valid: bool | None = None
) -> Lifecycle:
    """The lifecycle statement for a repository (read-only, offline).

    ``drafts_valid`` may be passed by a caller that already validated the
    drafts; otherwise they are validated here.
    """
    from nf_splice.services.lifecycle import validate_bundle

    root = Path(repository_root).resolve()
    if drafts_valid is None:
        from nf_splice.services.workspace import workspace_status

        drafts_valid = workspace_status(root).ready
    published = (root / PUBLISHED_DIR / "bundle.json").is_file()
    report = validate_bundle(root) if published else None
    readiness = assess_readiness(root, report)
    return Lifecycle(
        drafts_valid=drafts_valid,
        published=published,
        publication_current=bool(
            published and readiness.dimensions["publication"].status == READY
        ),
        structurally_valid=bool(report and report.structurally_valid),
        scientifically_classified=bool(
            report
            and report.classified
            and readiness.dimensions["scientific_classification"].status == READY
        ),
        readiness=readiness,
    )
