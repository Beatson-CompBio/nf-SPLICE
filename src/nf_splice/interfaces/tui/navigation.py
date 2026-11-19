"""Task-oriented pages, their derived states and the one focus mapping.

Pages are the developer's tasks, not nf-splice's internal operations
(ADR-0067). Their states derive from the current files and validation only,
never from which screens were visited. :func:`target_for` is the single
mapping from an agent stage, a layer and a JSON pointer to the page and the
field a person should see; every jump (a Review "Fix" button, an agent's
intervention) goes through it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class StepState(str, Enum):
    """What the rail says about one page; never colour alone."""

    NOT_STARTED = "not_started"
    NEEDS_REVIEW = "needs_review"
    IN_PROGRESS = "in_progress"
    READY = "ready"
    BLOCKED = "blocked"
    PUBLISHED = "published"


GLYPHS = {
    StepState.NOT_STARTED: "○",
    StepState.NEEDS_REVIEW: "!",
    StepState.IN_PROGRESS: "◐",
    StepState.READY: "✓",
    StepState.BLOCKED: "✕",
    StepState.PUBLISHED: "●",
}
LABELS = {
    StepState.NOT_STARTED: "Not started",
    StepState.NEEDS_REVIEW: "Needs review",
    StepState.IN_PROGRESS: "In progress",
    StepState.READY: "Ready",
    StepState.BLOCKED: "Blocked",
    StepState.PUBLISHED: "Published",
}


@dataclass(frozen=True, slots=True)
class Page:
    """One task in the step rail."""

    id: str
    title: str
    group: str
    #: The draft layer the page edits (internal name), if any.
    layer: str | None
    #: The agent stage that authors it, if any.
    stage: str | None
    lead: str
    ask_example: str
    assist_label: str


GROUPS = ("GET STARTED", "CREATE YOUR INTEGRATION", "FINISH")

PAGES: tuple[Page, ...] = (
    Page(
        "welcome",
        "Welcome",
        "GET STARTED",
        None,
        None,
        "Prepare a SPLICE workflow bundle for this Nextflow pipeline, by hand, "
        "with AI help, or both.",
        "How does nf-SPLICE work?",
        "Assist with the first step",
    ),
    Page(
        "overview",
        "Pipeline overview",
        "GET STARTED",
        None,
        "discover",
        "What nf-SPLICE read from this repository, and where your drafts are.",
        "What is still missing?",
        "Review imported metadata",
    ),
    Page(
        "identity",
        "Identity",
        "CREATE YOUR INTEGRATION",
        "bundle",
        "identity",
        "What is this pipeline? Imported values can be changed.",
        "What does repository_url mean?",
        "Propose identity from source evidence",
    ),
    Page(
        "assays",
        "Supported assays",
        "CREATE YOUR INTEGRATION",
        "bundle",
        "identity",
        "Which assays can this pipeline process across its supported routes?",
        "Which assays does this pipeline support, and why?",
        "Investigate the pipeline and propose assays",
    ),
    Page(
        "parameters",
        "Parameters",
        "CREATE YOUR INTEGRATION",
        "inputs",
        "inputs",
        "Who may supply each parameter when a job is submitted? Visibility is "
        "not permission.",
        "Who should set --input?",
        "Propose access policies",
    ),
    Page(
        "outputs",
        "Outputs",
        "CREATE YOUR INTEGRATION",
        "outputs",
        "outputs",
        "Describe the results people should find in SPLICE after a run. Start "
        "with one meaningful output.",
        "What does this published file contain?",
        "Assist with Outputs",
    ),
    Page(
        "software",
        "Software & containers",
        "CREATE YOUR INTEGRATION",
        "components",
        "components",
        "Declared tools, versions and container references; resolve only real gaps.",
        "Where is this container declared?",
        "Resolve tools and containers",
    ),
    Page(
        "execution",
        "Execution",
        "CREATE YOUR INTEGRATION",
        "execution-profiles",
        "profiles",
        "Where should SPLICE run this pipeline? Configure profiles and choose "
        "the default.",
        "Which cluster profile is appropriate?",
        "Propose a profile or fix one",
    ),
    Page(
        "provenance",
        "Provenance",
        "CREATE YOUR INTEGRATION",
        "provenance",
        "provenance",
        "Include workflow authorship, software and source information with the bundle.",
        "What provenance should be included?",
        "Propose a safe RO-Crate correction",
    ),
    Page(
        "review",
        "Review",
        "FINISH",
        None,
        "validate",
        "What remains before publication, and what SPLICE ingestion still needs.",
        "Explain this blocker",
        "Propose a fix for the selected blocker",
    ),
    Page(
        "publish",
        "Publish",
        "FINISH",
        None,
        "build",
        "Review the exact files, then publish the bundle into splice/.",
        "What will this publish?",
        "Review the publication plan",
    ),
)
PAGE_IDS = tuple(item.id for item in PAGES)
PAGE_BY_ID = {item.id: item for item in PAGES}


def page(page_id: str) -> Page:
    return PAGE_BY_ID[page_id]


def next_page(page_id: str) -> str:
    index = PAGE_IDS.index(page_id)
    return PAGE_IDS[min(index + 1, len(PAGE_IDS) - 1)]


def previous_page(page_id: str) -> str:
    index = PAGE_IDS.index(page_id)
    return PAGE_IDS[max(index - 1, 0)]


# ------------------------------------------------------------ focus mapping


@dataclass(frozen=True, slots=True)
class Target:
    """Where a person should look: a page, and optionally one field or entry."""

    page: str
    #: A field name on the page (``repository_url``, ``scopes``, ``version``).
    field: str | None = None
    #: The entry's index in its list (an output, a component, a profile).
    index: int | None = None
    #: A stable name of the entry (a parameter name, an output key).
    entry: str | None = None


_LAYER_PAGE = {
    "bundle": "identity",
    "inputs": "parameters",
    "outputs": "outputs",
    "components": "software",
    "execution-profiles": "execution",
    "provenance": "provenance",
}
_STAGE_PAGE = {
    "discover": "overview",
    "identity": "identity",
    "inputs": "parameters",
    "outputs": "outputs",
    "components": "software",
    "profiles": "execution",
    "provenance": "provenance",
    "validate": "review",
    "build": "publish",
    "verify": "publish",
    "export": "publish",
    "commit": "publish",
    "report": "review",
}
_STAGE_LAYER = {
    "identity": "bundle",
    "inputs": "inputs",
    "outputs": "outputs",
    "components": "components",
    "profiles": "execution-profiles",
    "provenance": "provenance",
}


def _parts(pointer: str) -> list[str]:
    return [
        part.replace("~1", "/").replace("~0", "~")
        for part in pointer.strip().split("/")[1:]
        if part != ""
    ]


def target_for(
    layer: str | None = None, pointer: str | None = None, stage: str | None = None
) -> Target:
    """The page and field for an issue or an intervention.

    ``layer`` and ``pointer`` come from a validation issue; ``stage`` from the
    agent. Falls back to the stage's page, then to Review.
    """
    if layer is None and stage is not None:
        layer = _STAGE_LAYER.get(stage)
    parts = _parts(pointer or "")
    if layer == "bundle":
        if parts[:2] == ["pipeline", "assay_capabilities"] or parts[:1] == [
            "assay_capabilities"
        ]:
            index = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
            return Target("assays", index=index)
        if parts[:1] == ["pipeline"] and len(parts) > 1:
            index = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
            return Target("identity", field=parts[1], index=index)
        if parts[:1] in (["maintainers"], ["maintainers_publication_approved"]):
            return Target("identity", field="maintainers")
        return Target("identity")
    if layer == "inputs":
        name = None
        if "properties" in parts:
            position = parts.index("properties")
            if position + 1 < len(parts):
                name = parts[position + 1]
        return Target("parameters", entry=name)
    if layer == "outputs":
        if parts[:1] == ["outputs"] and len(parts) > 1 and parts[1].isdigit():
            return Target(
                "outputs",
                field=parts[2] if len(parts) > 2 else None,
                index=int(parts[1]),
            )
        if parts[:1] == ["contract"]:
            return Target("outputs", field="schema_version")
        if parts[:1] == ["excluded_routes"]:
            return Target("outputs", field="coverage")
        return Target("outputs")
    if layer == "components":
        if parts[:1] in (["components"], ["containers"]) and len(parts) > 1:
            index = int(parts[1]) if parts[1].isdigit() else None
            return Target("software", field=parts[0], index=index)
        return Target("software")
    if layer == "execution-profiles":
        if parts[:1] == ["profiles"] and len(parts) > 1 and parts[1].isdigit():
            return Target(
                "execution",
                field=parts[2] if len(parts) > 2 else None,
                index=int(parts[1]),
            )
        return Target("execution")
    if layer == "provenance":
        return Target("provenance")
    if stage is not None:
        return Target(_STAGE_PAGE.get(stage, "review"))
    return Target("review")


def page_for_layer(layer: str) -> str:
    return _LAYER_PAGE.get(layer, "review")


def stage_for_page(page_id: str) -> str | None:
    return PAGE_BY_ID[page_id].stage


#: Readable labels for draft fields shown in grouped Review items.
FIELD_LABELS = {
    "id": "pipeline ID",
    "name": "pipeline name",
    "version": "version",
    "engine": "engine",
    "repository_url": "repository URL",
    "description": "description",
    "authors": "authors",
    "licence": "licence",
    "citation": "citation",
    "assay_capabilities": "supported assays",
    "schema_version": "analysis-output data version",
    "path_patterns": "published path",
    "scopes": "applies to",
    "entity_types": "represents",
    "formats": "format",
    "category": "category",
    "title": "title",
    "key": "stable key",
}


def field_label(pointer: str) -> str:
    """A short human label for the last meaningful pointer part."""
    for part in reversed(_parts(pointer)):
        if not part.isdigit():
            return FIELD_LABELS.get(part, re.sub(r"[_-]+", " ", part))
    return "draft"
