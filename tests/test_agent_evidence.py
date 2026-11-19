"""Evidence boundaries of agent operations: explicit decisions, no circularity."""

from __future__ import annotations

from pathlib import Path

import pytest

from layer_fixtures import ADA
from multi_route import copy_fixture
from nf_splice.agents.operations import OPERATIONS, OperationContext
from nf_splice.agents.permissions import ExecutionPolicy
from nf_splice.agents.review_scope import own_output_citations
from nf_splice.layers.base import read_layer
from nf_splice.services.workspace import initialise


def _context(root: Path) -> OperationContext:
    return OperationContext(root=root, change=ADA, policy=ExecutionPolicy())


def _version(root: Path) -> object:
    state = read_layer(root, "outputs")
    assert state.draft is not None
    return state.draft.data["contract"]["schema_version"]


def test_a_contract_version_needs_its_basis_and_a_proposal_is_flagged(
    tmp_path: Path,
) -> None:
    root = copy_fixture(tmp_path)
    initialise(root, ADA)
    operation = OPERATIONS["set_output_contract_version"]
    assert set(operation.input_schema["required"]) == {"version", "basis", "rationale"}
    # Claiming a published version that does not exist is refused.
    with pytest.raises(ValueError, match=r"splice/outputs\.yaml"):
        operation.handler(
            _context(root),
            {"version": "1.0.0", "basis": "published_catalogue", "rationale": "x"},
        )
    assert _version(root) is None
    result = operation.handler(
        _context(root),
        {
            "version": "1.0.0",
            "basis": "proposed_initial",
            "rationale": "No analysis_output.json shape was versioned before.",
        },
    )
    assert _version(root) == "1.0.0"
    assert str(result["proposed_decision"]).startswith("Proposed decision: ")


def test_own_output_is_never_evidence_of_an_assay(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path)
    initialise(root, ADA)
    with pytest.raises(ValueError, match="not evidence"):
        OPERATIONS["add_assay_capability"].handler(
            _context(root),
            {
                "reference": "polya_rnaseq",
                "evidence": "documented",
                "rationale": "An earlier bundle declared it.",
                "sources": ["splice/bundle.json"],
            },
        )
    assert own_output_citations(
        [".splice-local/drafts/bundle.draft.yaml:3", "splice/outputs.yaml", "main.nf"]
    ) == [".splice-local/drafts/bundle.draft.yaml:3", "splice/outputs.yaml"]


def test_the_removed_inference_tools_are_gone() -> None:
    for name in ("assess_assays", "list_assay_candidates", "discover_outputs"):
        assert name not in OPERATIONS
    assert "list_vocabulary_assays" in OPERATIONS


def test_an_assay_question_does_not_stop_the_independent_stages(
    tmp_path: Path,
) -> None:
    """Only validation and publication wait for the person's assay answer."""
    import asyncio
    import shutil

    from nf_splice.agents import InteractionMode, SessionEngine
    from nf_splice.agents.protocol import ToolInvoker, TurnRequest
    from nf_splice.agents.providers.scripted import ScriptedProvider
    from nf_splice.agents.stages import Stage

    root = tmp_path / "ambiguous"
    shutil.copytree(
        Path(__file__).parent / "fixtures" / "ambiguous-reads-0.3.0" / "repository",
        root,
    )

    def agent(request: TurnRequest, tools: ToolInvoker) -> list[str]:
        if request.stage == "identity":
            tools.call(
                "record_blocker",
                {
                    "decision": "Which assay the pipeline processes",
                    "reason": "Nothing states the molecule or library sequenced.",
                    "pointer": "/pipeline/assay_capabilities",
                },
            )
        return ["Done for this stage."]

    engine = SessionEngine.create(
        root,
        mode=InteractionMode.AUTONOMOUS,
        provider=ScriptedProvider(agent),
        objective="integrate",
        policy=ExecutionPolicy(),
        actor=ADA.actor,
    )
    asyncio.run(engine.advance())
    stages = engine.state.stages
    assert stages[Stage.IDENTITY].status.value == "blocked"
    for stage in (Stage.INPUTS, Stage.OUTPUTS, Stage.COMPONENTS, Stage.PROVENANCE):
        assert stages[stage].attempts >= 1, stage
        assert "waiting on identity" not in stages[stage].notes, stage
    # A cascaded block names the stage it waits for and the decision there,
    # so the cascade is never a mystery (round-5 histology finding).
    assert any(
        "waiting on identity" in note and "Which assay" in note
        for note in stages[Stage.VALIDATE].notes
    )


def test_files_can_be_listed_and_searched_by_path_glob(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path)
    initialise(root, ADA)
    context = _context(root)
    listed = OPERATIONS["list_files"].handler(context, {"glob": "**/*.nf"})
    assert "main.nf" in listed["data"]["files"]
    assert not any(item.startswith(".splice-local") for item in listed["data"]["files"])
    found = OPERATIONS["search_source"].handler(
        context, {"pattern": "publishDir", "glob": "modules/**/main.nf"}
    )
    assert found["data"]["matches"] and all(
        item.startswith("modules/") for item in found["data"]["matches"]
    )
    everything = OPERATIONS["search_source"].handler(
        context, {"pattern": "publishDir", "glob": "**/*"}
    )
    assert everything["data"]["matches"]
