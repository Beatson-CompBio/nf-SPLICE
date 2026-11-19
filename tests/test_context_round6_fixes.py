"""Deterministic fixes from the round-5 offline context evaluation.

Each test reproduces one documented finding against the real services: the
escaped output placeholder that validated silently, the container expression
truncated where acceptance could not use it, the refused review that burned
the stage-attempt budget, the dependency cascade that blocked stages without
naming its reason, the scaffold profile that only raw patching could
describe, and the image-policy blocker that named no way forward.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from pydantic import ValidationError

import nf_splice.layers.execution as execution_layer
from agent_scripts import RouteAgent
from layer_fixtures import ADA, STAGE_ANALYSIS, follow_scope, review_arguments
from multi_route import ACCESS, copy_fixture
from nf_splice.agents import (
    ExecutionPolicy,
    InteractionMode,
    Permission,
    SessionEngine,
)
from nf_splice.agents.operations import OPERATIONS
from nf_splice.agents.protocol import ToolInvoker, TurnRequest
from nf_splice.agents.providers.scripted import ScriptedProvider
from nf_splice.agents.stages import Stage, StageSpec, StageStatus, spec
from nf_splice.domain import Actor
from nf_splice.domain.components import ReferenceKind
from nf_splice.domain.outputs import (
    OutputEntityType,
    OutputScope,
    ReviewedOutput,
    expand_output_path_pattern,
)
from nf_splice.inspectors.containers import sources_in_text
from nf_splice.layers import LayerError
from nf_splice.layers.base import read_layer
from nf_splice.layers.components import (
    discover_components,
    set_image_policy,
    validate_components_draft,
)
from nf_splice.layers.execution import discover_execution


def test_escaped_placeholder_is_named_instead_of_silently_neutral() -> None:
    """Round 5 (rnaseq): ``\\{sample\\}`` validated and captured nothing."""
    with pytest.raises(ValueError, match="captures nothing"):
        expand_output_path_pattern(r"^foo_\{sample\}\.txt$")
    with pytest.raises(ValueError, match=r"write \{sample\}"):
        expand_output_path_pattern(r"^foo_\{sample}.txt$")
    # The plain capture still works, and a deliberate literal stays legal.
    assert "(?P<sample_id>" in expand_output_path_pattern(r"^foo_{sample}\.txt$")
    assert expand_output_path_pattern(r"^foo_[{]sample[}]\.txt$")


def test_escaped_placeholder_fails_output_review_construction() -> None:
    """The silent shape the evaluator hit: job-scoped, so nothing else cared."""
    with pytest.raises(ValidationError, match="captures nothing"):
        ReviewedOutput(
            key="reads",
            title="Reads",
            description="Per-sample FASTQ copies.",
            category="reads",
            formats=("fastq",),
            scopes=(OutputScope.JOB,),
            entity_types=(OutputEntityType.FILE,),
            path_patterns=(r"^.*\{sample\}.*\.fastq\.gz$",),
        )


LONG_IMAGE = "quay.io/biocontainers/" + "p" * 300 + "-padded:1.0--py310_0"
SNIPPET = f"""
process PADDED {{
    container params.custom_base_image ?
        "${{params.custom_base_image}}:b38-decoy" :
        '{LONG_IMAGE}' :
        'quay.io/tail:2'
    script:
        true
}}
"""


def test_multi_line_container_expression_stays_whole_and_selectable() -> None:
    """Round 5: the 300-char cut left an unresolved raw nobody could accept."""
    found = sources_in_text(SNIPPET, "modules/padded/main.nf")
    expression = [
        item
        for item in found
        if item.kind is ReferenceKind.UNRESOLVED_EXPRESSION and item.confidence == 0.3
    ]
    assert len(expression) == 1
    # The whole normalised expression survives: longer than the old cap and
    # still ending where the source ends.
    assert len(expression[0].raw) > 300
    assert expression[0].raw.endswith("'quay.io/tail:2'")
    # The concrete references inside it are detected too, so acceptance has
    # something real to select (accept_component matches detected raws).
    raws = {item.raw for item in found}
    assert LONG_IMAGE in raws
    assert "quay.io/tail:2" in raws


def _refusal_count(engine: SessionEngine) -> int:
    return sum(
        1
        for item in engine.state.conversation
        if item.kind == "denied" and "never_read.md" in item.text
    )


def test_refused_review_does_not_consume_the_attempt_budget(
    tmp_path: Path,
) -> None:
    """Round 5 (histology): refusals exhausted inputs and cascade-blocked.

    The scripted stand-in has two reviews refused (citing a file the stage
    never read) and completes on its third turn. With three attempts as the
    budget, charging every turn would block the stage before the third one;
    refunding a refused review keeps the no-progress rule as the only brake.
    """
    root = copy_fixture(tmp_path)

    state = {"turns": 0}

    def refused(request: TurnRequest, tools: ToolInvoker) -> list[str]:
        from agent_scripts import inputs as author_inputs

        tools.call("workspace_status", {})
        author_inputs(tools)
        follow_scope(tools)
        state["turns"] += 1
        parameter = sorted(ACCESS)[0]
        tools.call(
            "set_parameter_access",
            {
                "parameters": [parameter],
                "editable_by": ["user"] if state["turns"] % 2 else [],
            },
        )
        if state["turns"] <= 2:
            tools.call(
                "complete_review",
                review_arguments(
                    "inputs",
                    evidence=[STAGE_ANALYSIS["inputs"], "docs/never_read.md:1"],
                ),
            )
            return ["The review was refused."]
        result = tools.call("complete_review", review_arguments("inputs"))
        assert result["success"], result
        return ["Inputs reviewed."]

    agent = RouteAgent(overrides={"execute:inputs": refused})
    engine = SessionEngine.create(
        root,
        mode=InteractionMode.AUTONOMOUS,
        provider=ScriptedProvider(agent),
        objective="Integrate the pipeline with SPLICE.",
        policy=ExecutionPolicy(grants=[Permission.READ, Permission.DRAFT_EDIT]),
        actor=Actor(label="Ada"),
    )
    asyncio.run(engine.advance())
    assert state["turns"] == 3
    assert _refusal_count(engine) == 2
    record = engine.state.stages[Stage.INPUTS]
    assert record.status is StageStatus.COMPLETED, record.notes
    # Two refused turns refunded: the stage charged only the authoring work.
    assert record.attempts <= 2, record.attempts


def test_update_profile_completes_the_seeded_scaffold(tmp_path: Path) -> None:
    """Round 5: review_profile refused the scaffold default; only raw
    patching remained. update_profile is now an agent operation."""
    root = copy_fixture(tmp_path)
    discover_execution(root)
    with pytest.raises(LayerError, match="update_profile"):
        execution_layer.review_profile(
            root,
            "default",
            ADA,
            profile_type="development",
            description="Local default.",
            executor="local",
        )
    config = execution_layer.config_file_path("default")
    before = (root / config).read_bytes()
    result = execution_layer.update_profile(
        root,
        "default",
        {"description": "Local default runs.", "type": "development"},
        ADA,
    )
    assert result.wrote
    assert (root / config).read_bytes() == before  # the config is untouched
    draft = read_layer(root, "execution-profiles").draft
    assert draft is not None and isinstance(draft.data, dict)
    profile = next(
        item for item in draft.data["profiles"] if item.get("id") == "default"
    )
    assert profile["description"] == "Local default runs."
    assert profile["type"] == "development"


def test_update_profile_is_an_operation_of_the_profiles_stage() -> None:
    stage: StageSpec = spec(Stage.PROFILES)
    assert "update_profile" in stage.operations
    operation = OPERATIONS["update_profile"]
    assert operation.kind == "draft"


def test_image_policy_blocker_names_the_person_handoff(
    tmp_path: Path,
) -> None:
    """Round 5 (twice): needs_materialisation named no way forward."""
    root = copy_fixture(tmp_path)
    discover_components(root)
    set_image_policy(root, True, ADA)
    blocked = validate_components_draft(root)
    flagged = [item for item in blocked.errors if item.code == "needs_materialisation"]
    assert flagged
    for item in flagged:
        assert "containers deliver" in item.message
        assert "outside what an agent may do" in item.message
