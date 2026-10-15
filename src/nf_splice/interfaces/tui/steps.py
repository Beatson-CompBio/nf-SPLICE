"""Declarative, interface-independent wizard step graph.

Each step declares its prerequisites and derives completion from a
service-computed :class:`~nf_splice.interfaces.tui.state.WizardSnapshot`;
navigation never hard-codes routes between screens.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from nf_splice.interfaces.tui.state import WizardSnapshot


class StepStatus(str, Enum):
    """Progress state shown in the rail."""

    LOCKED = "locked"
    TODO = "todo"
    BLOCKED = "blocked"
    DEFERRED = "deferred"
    COMPLETE = "complete"


@dataclass(frozen=True, slots=True)
class Step:
    """One focused wizard task."""

    id: str
    title: str
    layer: str | None
    prerequisites: tuple[str, ...]
    complete: Callable[[WizardSnapshot], bool]
    help: str


def _layer_ready(layer: str) -> Callable[[WizardSnapshot], bool]:
    return lambda snapshot: snapshot.layer_state(layer) == "ready"


STEPS: tuple[Step, ...] = (
    Step(
        "welcome",
        "Welcome",
        None,
        (),
        lambda snapshot: True,
        "Choose to create a new bundle, resume an existing one or only inspect.",
    ),
    Step(
        "repository",
        "Repository",
        None,
        ("welcome",),
        lambda snapshot: True,
        "Review detected pipeline evidence and the state of splice/.",
    ),
    Step(
        "migration",
        "Migration",
        None,
        ("repository",),
        lambda snapshot: not snapshot.legacy_state or snapshot.has_drafts,
        "Migrate 0.1.0 authoring state into editable drafts (preview first).",
    ),
    Step(
        "identity",
        "Identity",
        "bundle",
        ("repository",),
        _layer_ready("bundle"),
        "Confirm or edit pipeline identity, authors, funders and citation.",
    ),
    Step(
        "inputs",
        "Inputs",
        "inputs",
        ("identity",),
        _layer_ready("inputs"),
        "Give every parameter one access policy (user, platform, agent).",
    ),
    Step(
        "outputs",
        "Outputs",
        "outputs",
        ("identity",),
        _layer_ready("outputs"),
        "Accept, reject, merge or split output candidates; job/sample/run scopes.",
    ),
    Step(
        "components",
        "Components",
        "components",
        ("identity",),
        _layer_ready("components"),
        "Review container sources and downloadable image distributions.",
    ),
    Step(
        "profiles",
        "Execution profiles",
        "execution-profiles",
        ("identity",),
        _layer_ready("execution-profiles"),
        "Adopt or generate configs and choose the single default profile.",
    ),
    Step(
        "provenance",
        "Provenance",
        "provenance",
        ("identity",),
        _layer_ready("provenance"),
        "Include, enrich or generate the RO-Crate; the root file is never edited.",
    ),
    Step(
        "drafts",
        "Drafts",
        None,
        ("identity",),
        lambda snapshot: not snapshot.malformed_drafts,
        "See every draft, external edits and per-field issues.",
    ),
    Step(
        "review",
        "Readiness",
        None,
        ("drafts",),
        lambda snapshot: snapshot.publish_ready,
        "Resolve the remaining blockers before publishing.",
    ),
    Step(
        "build",
        "Build",
        None,
        ("review",),
        lambda snapshot: snapshot.bundle_valid,
        "Review the plan diff and publish the bundle explicitly.",
    ),
    Step(
        "done",
        "Done",
        None,
        ("build",),
        lambda snapshot: snapshot.bundle_valid,
        "Validation report and equivalent CLI commands.",
    ),
)
STEP_IDS = tuple(item.id for item in STEPS)


def step(step_id: str) -> Step:
    """Return a step by ID."""
    for item in STEPS:
        if item.id == step_id:
            return item
    raise KeyError(step_id)


def status(
    item: Step,
    snapshot: WizardSnapshot,
    *,
    visited: frozenset[str] = frozenset(),
    deferred: frozenset[str] = frozenset(),
) -> StepStatus:
    """Derive one step's status; locked steps are unreachable."""
    if not unlocked(item, snapshot, visited=visited):
        return StepStatus.LOCKED
    if item.id in {"welcome", "repository"} and item.id not in visited:
        return StepStatus.TODO
    if item.complete(snapshot):
        return StepStatus.COMPLETE
    if item.id in deferred:
        return StepStatus.DEFERRED
    if item.layer is not None and snapshot.layer_state(item.layer) in {
        "incomplete",
        "malformed",
    }:
        return StepStatus.BLOCKED
    return StepStatus.TODO


def unlocked(
    item: Step, snapshot: WizardSnapshot, *, visited: frozenset[str] = frozenset()
) -> bool:
    """Whether every prerequisite was visited or is complete.

    Visiting a step is enough to unlock its dependants, so an unresolved
    step can be deferred; only publication requires every layer to be ready.
    """
    if item.id == "build":
        return snapshot.publish_ready or snapshot.bundle_valid
    if item.id == "done":
        return snapshot.bundle_valid
    return all(
        requirement in visited or step(requirement).complete(snapshot)
        for requirement in item.prerequisites
    )


def next_step(
    current: str, snapshot: WizardSnapshot, *, visited: frozenset[str]
) -> str:
    """The next unlocked step after ``current``; ready steps are skipped on resume."""
    index = STEP_IDS.index(current)
    for item in STEPS[index + 1 :]:
        if unlocked(item, snapshot, visited=visited | {current}):
            return item.id
    return current


def previous_step(current: str) -> str:
    """The step before ``current`` (Back)."""
    index = STEP_IDS.index(current)
    return STEP_IDS[max(index - 1, 0)]


def resume_step(snapshot: WizardSnapshot, *, visited: frozenset[str]) -> str:
    """First incomplete, unlocked authoring step when resuming."""
    for item in STEPS[2:]:
        reachable = unlocked(
            item, snapshot, visited=visited | {"welcome", "repository"}
        )
        if reachable and not item.complete(snapshot):
            return item.id
    return "done" if snapshot.bundle_valid else "review"
