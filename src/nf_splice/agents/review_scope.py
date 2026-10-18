"""What a layer review must look at, and what it actually looked at (ADR-0063).

A review is complete when the evidence that bears on its layer was
inspected, not when some number of tool calls was made. For each layer
stage, :func:`review_scope` derives from the repository itself the evidence
classes that apply to *this* pipeline (its workflow files, the configs that
publish outputs, the modules whose containers could not be resolved, the
profiles' configs, the root RO-Crate, ...). A class is required or
advisory; a class whose evidence does not exist in the repository is not
applicable rather than missing. :func:`coverage` compares the classes with
the investigation trace nf-splice recorded from the model's own read calls.

Nothing here judges the model's conclusions: that is what the person, or
the deterministic gates, do. It only makes sure a review cannot be finished
without looking at what matters, and records the gaps it leaves.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from nf_splice.layers.base import read_layer
from nf_splice.layout import PRIVATE_DIR, PUBLISHED_DIR

COVERED = "covered"
PARTIAL = "partial"
GAP = "gap"

#: Directories never treated as pipeline evidence.
_IGNORED = {
    ".git",
    PRIVATE_DIR,
    ".nf-splice-local",
    "work",
    ".nextflow",
    "node_modules",
}
#: At most this many file targets per class are listed; a class over the
#: limit needs only these (sorted) files, and says how many more exist.
_TARGET_LIMIT = 25
_DOCUMENTATION = (
    "README.md",
    "README.rst",
    "README",
    "docs/README.md",
    "docs/usage.md",
    "docs/output.md",
    "CITATION.cff",
)


@dataclass(frozen=True, slots=True)
class EvidenceClass:
    """One kind of evidence a layer review must (or should) inspect."""

    id: str
    title: str
    required: bool
    #: Calls that satisfy the class, as recorded in the trace: a bare tool
    #: name (``analyse_routes``) or a call with its key argument
    #: (``read_draft(layer=outputs)``).
    tools: tuple[str, ...] = ()
    #: Repository files that satisfy the class when read.
    targets: tuple[str, ...] = ()
    #: Whether every target must be inspected (else any one).
    every: bool = False
    #: Files that exist beyond the listed targets (not required).
    more: int = 0

    def suggestions(self, missing: Sequence[str]) -> list[dict[str, Any]]:
        """Calls that would cover what is missing."""
        if self.tools:
            name, _, detail = self.tools[0].partition("(")
            arguments = dict(
                part.split("=", 1) for part in detail.rstrip(")").split(", ") if part
            )
            return [{"tool": name, "arguments": arguments}]
        calls = []
        for target in missing:
            if target.startswith(f"{PRIVATE_DIR}/drafts/configs/"):
                calls.append(
                    {
                        "tool": "read_config",
                        "arguments": {"name": PurePosixPath(target).name},
                    }
                )
            else:
                calls.append({"tool": "read_source", "arguments": {"path": target}})
        return calls if self.every else calls[:1]


@dataclass(frozen=True, slots=True)
class ClassCoverage:
    """How far one evidence class was inspected."""

    evidence: EvidenceClass
    status: str
    inspected: tuple[str, ...]
    missing: tuple[str, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.evidence.id,
            "title": self.evidence.title,
            "required": self.evidence.required,
            "status": self.status,
            "inspected": list(self.inspected),
            "missing": list(self.missing[:_TARGET_LIMIT]),
            "more_files": self.evidence.more,
            "suggested_calls": self.evidence.suggestions(self.missing)
            if self.status != COVERED
            else [],
        }


@dataclass(frozen=True, slots=True)
class Coverage:
    """Every class of a stage's scope against the investigation trace."""

    stage: str
    classes: tuple[ClassCoverage, ...] = field(default_factory=tuple)

    @property
    def required_gaps(self) -> list[ClassCoverage]:
        return [
            item
            for item in self.classes
            if item.evidence.required and item.status != COVERED
        ]

    @property
    def advisory_gaps(self) -> list[ClassCoverage]:
        return [
            item
            for item in self.classes
            if not item.evidence.required and item.status != COVERED
        ]

    @property
    def complete(self) -> bool:
        return not self.required_gaps

    def gap_lines(self) -> list[str]:
        lines = []
        for item in self.required_gaps + self.advisory_gaps:
            kind = "required" if item.evidence.required else "advisory"
            missing = (
                ": not yet inspected " + ", ".join(item.missing[:8])
                if item.missing
                else ": not yet inspected"
            )
            lines.append(f"{item.evidence.title} ({kind}){missing}")
        return lines

    def to_json(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "complete": self.complete,
            "classes": [item.to_json() for item in self.classes],
            "required_gaps": [item.evidence.id for item in self.required_gaps],
            "advisory_gaps": [item.evidence.id for item in self.advisory_gaps],
        }


# ------------------------------------------------------------ the scope


def _walk(root: Path, suffix: str) -> list[str]:
    found = []
    for path in sorted(root.rglob(f"*{suffix}")):
        relative = path.relative_to(root)
        parts = relative.parts
        if (
            path.is_symlink()
            or not path.is_file()
            or any(part in _IGNORED for part in parts)
            or parts[0] == PUBLISHED_DIR
            or "tests" in parts[:-1]
            or path.name.endswith(".nf.test")
        ):
            continue
        found.append(relative.as_posix())
    return found


def _existing(root: Path, names: Iterable[str]) -> tuple[str, ...]:
    return tuple(name for name in names if (root / name).is_file())


def _text(root: Path, relative: str) -> str:
    try:
        return (root / relative).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _limited(items: Sequence[str]) -> tuple[tuple[str, ...], int]:
    unique = sorted(dict.fromkeys(items))
    return tuple(unique[:_TARGET_LIMIT]), max(0, len(unique) - _TARGET_LIMIT)


def _files(
    identifier: str,
    title: str,
    required: bool,
    targets: Sequence[str],
    *,
    every: bool = False,
) -> EvidenceClass | None:
    if not targets:
        return None
    listed, more = _limited(targets)
    return EvidenceClass(
        identifier, title, required, targets=listed, every=every, more=more
    )


def _draft_class(layer: str) -> EvidenceClass:
    return EvidenceClass(
        "existing_draft",
        f"the current {layer} draft",
        True,
        tools=(f"read_draft(layer={layer})", f"inspect_draft(layer={layer})"),
    )


def _workflows(root: Path) -> list[str]:
    files = _existing(root, ["main.nf"])
    return [
        *files,
        *(item for item in _walk(root, ".nf") if item.startswith("workflows/")),
    ]


def _subworkflows(root: Path) -> list[str]:
    return [
        item
        for item in _walk(root, ".nf")
        if item.startswith("subworkflows/")
        and not item.startswith("subworkflows/nf-core/")
    ]


def _configs(root: Path) -> list[str]:
    return [
        item
        for item in _walk(root, ".config")
        if not PurePosixPath(item).name.startswith("nf-test")
    ]


def _identity_scope(root: Path) -> list[EvidenceClass | None]:
    return [
        _draft_class("bundle"),
        EvidenceClass(
            "assay_vocabulary",
            "assay evidence and the SPLICE vocabulary",
            True,
            tools=(
                "list_assay_candidates",
                "search_assay_catalogue",
                "show_assay",
            ),
        ),
        _files(
            "pipeline_metadata",
            "the pipeline's own metadata (nextflow.config, main.nf)",
            True,
            _existing(root, ["nextflow.config", "main.nf"]),
        ),
        _files(
            "documentation",
            "the pipeline's documentation (README, usage, CITATION.cff)",
            True,
            _existing(root, _DOCUMENTATION),
        ),
        EvidenceClass(
            "assay_routes",
            "alternative routes that may process other assays",
            False,
            tools=("analyse_routes",),
        ),
    ]


def _inputs_scope(root: Path) -> list[EvidenceClass | None]:
    bindings = [
        *_existing(root, ["nextflow.config"]),
        *_profile_configs(root),
    ]
    return [
        _draft_class("inputs"),
        EvidenceClass(
            "parameter_usage",
            "where the code reads each parameter",
            True,
            tools=("parameter_usage",),
        ),
        _files(
            "input_schema",
            "the pipeline's nextflow_schema.json",
            True,
            _existing(root, ["nextflow_schema.json"]),
        ),
        _files(
            "workflow_code",
            "workflow code that consumes the inputs",
            True,
            _workflows(root),
        ),
        _files(
            "runtime_bindings",
            "configs that set parameter values",
            True,
            bindings,
        ),
    ]


def _publishing_configs(root: Path) -> list[str]:
    return [item for item in _configs(root) if "publishDir" in _text(root, item)]


def _outputs_scope(root: Path, examples: bool) -> list[EvidenceClass | None]:
    return [
        _draft_class("outputs"),
        EvidenceClass(
            "publication_routes",
            "the traced publication routes, including conditional branches",
            True,
            tools=("analyse_routes",),
        ),
        _files(
            "workflow_sources",
            "the entry workflow and every workflow under workflows/",
            True,
            _workflows(root),
            every=True,
        ),
        _files(
            "publication_rules",
            "every config that declares publishDir",
            True,
            _publishing_configs(root),
            every=True,
        ),
        _files(
            "subworkflows",
            "local subworkflows",
            False,
            _subworkflows(root),
            every=True,
        ),
        EvidenceClass(
            "example_outputs",
            "the example results you supplied",
            True,
            tools=("list_example_outputs", "reconcile_example_outputs"),
        )
        if examples
        else None,
    ]


def _unresolved_modules(root: Path) -> list[str]:
    state = read_layer(root, "components")
    if state.draft is None or not isinstance(state.draft.data, dict):
        return []
    found = []
    for item in state.draft.data.get("components") or []:
        if isinstance(item, dict) and item.get("unresolved") and item.get("path"):
            # An inline process's code is its workflow file itself.
            main = (
                str(item["path"]) if item.get("process") else f"{item['path']}/main.nf"
            )
            if (root / main).is_file():
                found.append(main)
    return found


def _container_overrides(root: Path) -> list[str]:
    pattern = re.compile(r"withName[^{]*\{[^}]*\bcontainer\b", re.S)
    return [item for item in _configs(root) if pattern.search(_text(root, item))]


def _components_scope(root: Path) -> list[EvidenceClass | None]:
    return [
        _draft_class("components"),
        EvidenceClass(
            "module_inventory",
            "every module with its container references",
            True,
            tools=("component_inventory",),
        ),
        _files(
            "module_index",
            "modules.json",
            True,
            _existing(root, ["modules.json"]),
        ),
        _files(
            "unresolved_modules",
            "each module whose container or version is unresolved",
            True,
            _unresolved_modules(root),
            every=True,
        ),
        _files(
            "container_overrides",
            "configs that override containers with withName",
            False,
            _container_overrides(root),
            every=True,
        ),
    ]


def _profile_configs(root: Path) -> list[str]:
    from nf_splice.layers.execution import profile_config

    state = read_layer(root, "execution-profiles")
    if state.draft is None or not isinstance(state.draft.data, dict):
        return []
    found = []
    for profile in state.draft.data.get("profiles") or []:
        if not isinstance(profile, dict):
            continue
        _strategy, path, _problem = profile_config(root, profile)
        if path and (root / path).is_file():
            found.append(path)
    return found


def _memory_modules(root: Path) -> list[str]:
    from nf_splice.services.execution_review import memory_uses

    return [use.location.rsplit(":", 1)[0] for use in memory_uses(root)]


def _profiles_scope(root: Path) -> list[EvidenceClass | None]:
    return [
        _draft_class("execution-profiles"),
        EvidenceClass(
            "execution_analysis",
            "process selectors, resources and memory behaviour",
            True,
            tools=("analyse_execution",),
        ),
        _files(
            "profile_configs",
            "every profile's native configuration",
            True,
            _profile_configs(root),
            every=True,
        ),
        _files(
            "pipeline_resources",
            "the pipeline's own resource configuration",
            True,
            _existing(root, ["conf/base.config", "nextflow.config"]),
        ),
        _files(
            "task_memory",
            "modules whose scripts use task.memory",
            False,
            _memory_modules(root),
            every=True,
        ),
    ]


def _provenance_scope(root: Path) -> list[EvidenceClass | None]:
    return [
        _draft_class("provenance"),
        EvidenceClass(
            "crate_analysis",
            "the RO-Crate's structural and identity findings",
            True,
            tools=("analyse_ro_crate", "validate_ro_crate"),
        ),
        EvidenceClass(
            "reviewed_identity",
            "the reviewed identity the crate must agree with",
            True,
            tools=("read_draft(layer=bundle)", "inspect_draft(layer=bundle)"),
        ),
        _files(
            "root_crate",
            "the repository's own ro-crate-metadata.json",
            True,
            _existing(root, ["ro-crate-metadata.json"]),
        ),
        _files(
            "authorship",
            "authorship and citation sources",
            False,
            _existing(root, ["CITATION.cff", "nextflow.config"]),
        ),
        EvidenceClass(
            "standards_check",
            "Workflow RO-Crate standards validation",
            False,
            tools=("validate_ro_crate", "run_optional_checks"),
        ),
    ]


def review_scope(
    root: Path, stage: str, *, examples: bool = False
) -> tuple[EvidenceClass, ...]:
    """The evidence classes that apply to one layer stage of this pipeline."""
    builders = {
        "identity": lambda: _identity_scope(root),
        "inputs": lambda: _inputs_scope(root),
        "outputs": lambda: _outputs_scope(root, examples),
        "components": lambda: _components_scope(root),
        "profiles": lambda: _profiles_scope(root),
        "provenance": lambda: _provenance_scope(root),
    }
    build = builders.get(stage)
    if build is None:
        return ()
    return tuple(item for item in build() if item is not None)


# ------------------------------------------------------------ the trace


def _entry(entry: str) -> tuple[str, str]:
    """(tool, the call as recorded) of one trace entry."""
    name = entry.split(" ", 1)[0].split("(", 1)[0]
    return name, entry


def inspected_paths(trace: Iterable[str]) -> set[str]:
    """Repository files the trace shows were read (or matched by a search)."""
    from nf_splice.layers.execution import config_file_path

    paths: set[str] = set()
    for entry in trace:
        name, text = _entry(entry)
        if name == "read_source":
            match = re.match(r"read_source (.+):[^:]*$", text)
            if match:
                paths.add(match.group(1).removeprefix("./"))
        elif name == "search_source":
            match = re.match(r"search_source /.*/ in (.+) \((\d+) match", text)
            if match and int(match.group(2)) > 0 and match.group(1) != "*":
                paths.add(match.group(1).removeprefix("./"))
        elif name == "read_config":
            match = re.search(r"name=([^,)]+)", text)
            if match:
                try:
                    paths.add(config_file_path(match.group(1)))
                except ValueError:
                    continue
    return paths


def coverage(
    root: Path, stage: str, trace: Sequence[str], *, examples: bool = False
) -> Coverage:
    """Compare a stage's scope with what the trace inspected."""
    entries = list(trace)
    calls = {text for _name, text in map(_entry, entries)}
    names = {name for name, _text in map(_entry, entries)}
    paths = inspected_paths(entries)
    found = []
    for item in review_scope(root, stage, examples=examples):
        if item.tools:
            used = tuple(
                tool
                for tool in item.tools
                if (tool in calls if "(" in tool else tool in names)
            )
            status = COVERED if used else GAP
            found.append(ClassCoverage(item, status, used, ()))
            continue
        seen = tuple(target for target in item.targets if target in paths)
        missing = tuple(target for target in item.targets if target not in paths)
        if not missing or (seen and not item.every):
            status = COVERED
        elif seen:
            status = PARTIAL
        else:
            status = GAP
        found.append(ClassCoverage(item, status, seen, missing))
    return Coverage(stage, tuple(found))


_PATHLIKE = re.compile(r"^[\w./@+-]+\.[A-Za-z0-9]+(?::\d+(?:-\d+)?)?$")


def unsupported_citations(
    evidence: Sequence[str], trace: Sequence[str]
) -> tuple[list[str], list[str]]:
    """(supported, unsupported) citations of a review's evidence.

    A citation is a repository file (optionally ``path:line``) or a tool
    name. A file citation is supported only when the trace shows the file
    was read; a tool citation only when the tool was called. Free-text
    evidence that is neither is kept, but does not count as support.
    """
    paths = inspected_paths(trace)
    names = {_entry(item)[0] for item in trace}
    supported: list[str] = []
    unsupported: list[str] = []
    for item in evidence:
        text = str(item).strip()
        head = text.split()[0] if text else ""
        if _PATHLIKE.match(head):
            path = re.sub(r":\d+(?:-\d+)?$", "", head).removeprefix("./")
            (supported if path in paths else unsupported).append(text)
        elif head.split("(", 1)[0] in names:
            supported.append(text)
    return supported, unsupported


def summary_for_prompt(report: Coverage) -> str:
    """A compact statement of a stage's coverage, for the model."""
    if not report.classes:
        return ""
    lines = []
    for item in report.classes:
        kind = "required" if item.evidence.required else "advisory"
        lines.append(f"- {item.evidence.title} ({kind}): {item.status}")
    return "\n".join(lines)


def suggested_calls(
    report: Coverage, *, advisory: bool = False
) -> list[dict[str, Any]]:
    """Calls that would close the gaps (required first)."""
    gaps = report.required_gaps + (report.advisory_gaps if advisory else [])
    calls: list[dict[str, Any]] = []
    for item in gaps:
        for call in item.evidence.suggestions(item.missing):
            if call not in calls:
                calls.append(call)
    return calls


def coverage_json(report: Coverage) -> list[dict[str, Any]]:
    return [item.to_json() for item in report.classes]
