"""Deterministic tool fixes from the round-2 offline context evaluation.

Each test pins one deficiency an evaluator hit for real: patch staleness
against redacted reads, the ``/`` section, unbounded inventories, clipped
crate advice, citation vocabulary, and clip hints naming arguments the
tool does not offer.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from multi_route import EXAMPLE, author_all, copy_fixture
from nf_splice.agents.permissions import ExecutionPolicy
from nf_splice.agents.review_scope import (
    own_output_citations,
    unsupported_citations,
)
from nf_splice.agents.state import Usage
from nf_splice.agents.toolbox import SessionToolbox, ToolMode, _clip
from nf_splice.domain import Actor, ChangeOrigin
from nf_splice.drafts.patch import (
    PatchConflictError,
    PatchOp,
    apply,
    merge,
)
from nf_splice.layers import ChangeContext
from nf_splice.services.audit import redact
from nf_splice.services.crate_review import assess_crate


def _toolbox(root: Path, operations: set[str]) -> SessionToolbox:
    return SessionToolbox(
        root=root,
        policy=ExecutionPolicy(),
        mode=ToolMode.EXECUTE,
        operations=operations,
        controls=set(),
        change=ChangeContext(
            actor=Actor(label="agent"), origin=ChangeOrigin.AGENT_AUTONOMOUS
        ),
        usage=Usage(),
        stage_layer=None,
    )


def test_replace_and_remove_without_a_base_accept_the_current_value() -> None:
    document = {"a": {"b": 1}, "items": [1, 2]}
    merged, conflicts = merge(document, [PatchOp("replace", "/a/b", 2)])
    assert conflicts == [] and merged["a"]["b"] == 2
    merged, conflicts = merge(document, [PatchOp("remove", "/items/0")])
    assert conflicts == [] and merged["items"] == [2]
    # A supplied base still guards against a concurrent change.
    _, conflicts = merge(document, [PatchOp("replace", "/a/b", 2, expected=100)])
    assert [item.path for item in conflicts] == ["/a/b"]
    # add without a base still means a free location.
    _, conflicts = merge({"a": 1}, [PatchOp("add", "/a", 2)])
    assert [item.path for item in conflicts] == ["/a"]


def test_a_base_copied_from_a_redacted_read_still_matches() -> None:
    document = {"settings": {"key": "password=verysecretvalue", "n": 1}}
    secret = document["settings"]["key"]
    assert isinstance(secret, str)
    shown = redact(secret)
    assert shown != secret
    merged, conflicts = merge(
        document,
        [PatchOp("replace", "/settings/key", "password=othersecret", expected=shown)],
    )
    assert conflicts == []
    assert merged["settings"]["key"] == "password=othersecret"


def test_a_conflict_names_the_path_and_both_values() -> None:
    with pytest.raises(PatchConflictError) as error:
        apply({"a": 1}, [PatchOp("replace", "/a", 2, expected=100)])
    message = str(error.value)
    assert "/a" in message
    assert "expected 100" in message and "found 1" in message
    assert "re-read" in message


def test_a_draft_path_citation_needs_its_read_and_is_never_its_own_support() -> None:
    trace = ["read_draft(layer=outputs)", "read_source main.nf:1-40"]
    citations = [
        ".splice-local/drafts/outputs.draft.yaml",
        "drafts/outputs.draft.yaml",
    ]
    supported, unsupported = unsupported_citations(citations, trace)
    assert supported == citations and unsupported == []
    supported, unsupported = unsupported_citations(
        ["drafts/outputs.draft.yaml"], ["read_draft(layer=bundle)"]
    )
    assert supported == [] and unsupported == ["drafts/outputs.draft.yaml"]
    # Reading it makes it citable; it still proves nothing on its own.
    assert own_output_citations(citations) == citations


def test_the_root_section_reads_the_whole_draft(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path)
    author_all(root)
    tools = _toolbox(root, {"read_draft"})
    whole = tools.call("read_draft", {"layer": "outputs"})
    explicit = tools.call("read_draft", {"layer": "outputs", "section": "/"})
    assert whole["success"] and explicit["success"]
    assert explicit["data"] == whole["data"]


def test_component_inventory_leads_with_a_summary_and_pages_rows(
    tmp_path: Path,
) -> None:
    root = copy_fixture(tmp_path)
    tools = _toolbox(root, {"component_inventory"})
    first = tools.call("component_inventory", {"limit": 2})
    assert first["success"] and first["count"] >= 3
    assert first["summary"]["count"] == first["count"]
    assert len(first["summary"]["modules"]) == first["count"]
    assert len(first["items"]) == 2 and first["next_offset"] == 2
    second = tools.call(
        "component_inventory", {"limit": 2, "offset": first["next_offset"]}
    )
    assert second["items"] and second["items"][0]["id"] != first["items"][0]["id"]
    name = str(first["items"][0]["name"])
    filtered = tools.call("component_inventory", {"name": name})
    assert filtered["count"] >= 1
    assert all(name.casefold() in item["name"].casefold() for item in filtered["items"])


def test_crate_advice_precedes_the_findings_it_explains(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path)
    assessment = assess_crate(root)
    keys = list(assessment)
    assert keys[0] == "recommendation"
    assert keys.index("draft") < keys.index("root_crate")


@pytest.mark.parametrize(
    ("tool", "expected", "absent"),
    [
        ("component_inventory", "offset", "start_line"),
        ("read_source", "start_line", "offset"),
    ],
)
def test_the_clip_hint_names_only_arguments_the_tool_offers(
    tool: str, expected: str, absent: str
) -> None:
    clipped: dict[str, Any] = _clip({"data": "x" * 30_000}, tool)
    assert clipped["truncated"]
    assert expected in clipped["hint"] and absent not in clipped["hint"]


def _write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_a_null_comparison_guards_task_memory(tmp_path: Path) -> None:
    """The RNA-seq FASTQC module's shape, which round 2 called unguarded."""
    from nf_splice.services.execution_review import memory_uses

    root = tmp_path / "pipeline"
    _write(
        root,
        "modules/nf-core/fastqc/main.nf",
        "process FASTQC {\n"
        "    label 'process_medium'\n"
        "    memory {\n"
        "        task.memory == null ? check_max(20.GB, max_memory, task.attempt)\n"
        "            : check_max(task.memory * 2, max_memory, task.attempt)\n"
        "    }\n"
        "}\n",
    )
    _write(
        root,
        "modules/unguarded/main.nf",
        "process UNGUARDED {\n    script:\n    def over = task.memory.giga * 2\n}\n",
    )
    uses = {item.process: item for item in memory_uses(root)}
    assert uses["FASTQC"].guarded
    assert not uses["UNGUARDED"].guarded


def test_a_null_comparison_on_an_earlier_line_still_guards(tmp_path: Path) -> None:
    """The split ternary: the test on one line, the use on the next."""
    from nf_splice.services.execution_review import memory_uses

    root = tmp_path / "pipeline"
    _write(
        root,
        "modules/split/main.nf",
        "process SPLIT {\n"
        "    memory {\n"
        "        def fallback = 8.GB\n"
        "        task.memory == null ?\n"
        "            fallback :\n"
        "            task.memory * 1.5\n"
        "    }\n"
        "}\n",
    )
    uses = [item for item in memory_uses(root) if item.process == "SPLIT"]
    assert uses and all(item.guarded for item in uses)


def test_profiles_from_every_block_and_quoted_names_are_discovered(
    tmp_path: Path,
) -> None:
    from nf_splice.inspectors.profiles import discover_profiles

    _write(
        tmp_path,
        "nextflow.config",
        "profiles {\n"
        "    local { process { executor = 'local' } }\n"
        "}\n"
        "// a second block, as plugins and site files add\n"
        "profiles {\n"
        "    \"test_full_azure\" { process { executor = 'azure-batch' } }\n"
        "    test_dnase { process { executor = 'slurm' } }\n"
        "}\n",
    )
    names = {candidate.source_profile for candidate, _ in discover_profiles(tmp_path)}
    assert {"local", "test_full_azure", "test_dnase"} <= names


def test_route_rows_keep_the_declared_path_and_name_their_basis(
    tmp_path: Path,
) -> None:
    root = copy_fixture(tmp_path)
    author_all(root)
    tools = _toolbox(root, {"analyse_routes", "route_coverage"})
    routes = tools.call("analyse_routes", {})
    assert routes["success"]
    assert "basis" in routes["data"]
    items = routes["data"]["published"]["items"]
    assert items and all("declared_path" in item for item in items)
    coverage = tools.call("route_coverage", {})
    assert coverage["success"] and "basis" in coverage["data"]


def test_a_covered_scope_class_shows_no_missing_and_no_nameless_count() -> None:
    from nf_splice.agents.review_scope import ClassCoverage, EvidenceClass

    item = EvidenceClass("docs", "docs", True, targets=("README.md", "usage.md"))
    report = ClassCoverage(item, "covered", ("README.md",), ("usage.md",))
    assert report.to_json()["missing"] == []


def test_hidden_scope_files_are_named_not_counted(tmp_path: Path) -> None:
    from nf_splice.agents.review_scope import review_scope

    (tmp_path / "workflows").mkdir()
    _write(tmp_path, "main.nf", "// entry\n")
    for index in range(26):
        _write(tmp_path, f"workflows/p{index:02}.nf", "// route\n")
    classes = review_scope(tmp_path, "inputs")
    code = next(item for item in classes if item.id == "workflow_code")
    assert len(code.targets) == 25 and len(code.more) == 2
    assert all(name.startswith("workflows/") for name in code.more)


def test_a_completed_review_keeps_the_stage_blocked_behind_a_blocker(
    tmp_path: Path,
) -> None:
    """The methylation round-2 behaviour, pinned as intended.

    A finished review does not outvote a recorded human decision: the
    review is kept and shown, the stage stays blocked, and nothing is
    published past it.
    """
    import asyncio

    from agent_scripts import RouteAgent, outputs
    from layer_fixtures import follow_scope, review_arguments
    from nf_splice.agents import InteractionMode, SessionEngine, SessionStatus
    from nf_splice.agents.protocol import ToolInvoker, TurnRequest
    from nf_splice.agents.providers.scripted import ScriptedProvider
    from nf_splice.agents.stages import Stage

    def reviewed_then_stuck(request: TurnRequest, tools: ToolInvoker) -> list[str]:
        outputs(tools)
        follow_scope(tools)
        reviewed = tools.call(
            "complete_review",
            review_arguments(
                "outputs", summary="Reviewed; one decision is a person's."
            ),
        )
        assert reviewed.get("success"), reviewed
        tools.call(
            "record_blocker",
            {
                "decision": "Whether the multiqc figures are platform outputs",
                "artefact": ".splice-local/drafts/outputs.draft.yaml",
                "attempted_checks": ["analyse_routes", "route_coverage"],
                "suggested_resolution": "A person decides which figures users need.",
            },
        )
        return ["Reviewed the catalogue; one decision remains open."]

    root = copy_fixture(tmp_path)
    policy = ExecutionPolicy()
    policy.examples = [str(EXAMPLE)]
    engine = SessionEngine.create(
        root,
        mode=InteractionMode.AUTONOMOUS,
        provider=ScriptedProvider(
            RouteAgent(overrides={"execute:outputs": reviewed_then_stuck})
        ),
        objective="Integrate the pipeline with SPLICE.",
        policy=policy,
        actor=Actor(label="Ada"),
    )
    asyncio.run(engine.advance())
    assert engine.state.status is SessionStatus.BLOCKED
    record = engine.state.stages[Stage.OUTPUTS]
    assert record.review is not None
    assert record.review.outcome.startswith("blocked")
    assert any(not item.resolved for item in engine.state.blockers)
    assert not (root / "splice" / "bundle.json").exists()


def test_ask_context_carries_the_pages_draft_state(tmp_path: Path) -> None:
    from nf_splice.agents.help import page_context

    root = copy_fixture(tmp_path)
    found = page_context(root, {"page": "outputs"})
    assert found["draft"]["layer"] == "outputs"
    assert isinstance(found["draft"]["ready"], bool)
    assert found["draft"]["issues"] == [] or all(
        isinstance(line, str) for line in found["draft"]["issues"]
    )
    assert "draft" not in page_context(root, {"page": "welcome"})
    given = {"page": "outputs", "draft": {"layer": "outputs", "ready": True}}
    assert page_context(root, given)["draft"] == given["draft"]


def test_session_summaries_end_at_words_not_inside_them() -> None:
    from nf_splice.agents.engine import _ellipsise

    text = "The date cannot be establi" + "shed because nothing states it. " * 40
    summary = _ellipsise(text, 120)
    assert len(summary) <= 120
    assert not summary.endswith("shed.")  # stops at a sentence, not mid-word
    assert summary.endswith(".") or summary.endswith("…")
    assert _ellipsise("x" * 200, 120).endswith("…")
    assert _ellipsise("short note", 400) == "short note"


def test_scanned_components_cite_only_files_that_exist(tmp_path: Path) -> None:
    from nf_splice.layers.components import discovered_modules

    _write(
        tmp_path,
        "modules/local/demo/1.2/main.nf",
        'process DEMO {\n    container "quay.io/demo/demo:1.2"\n'
        "    script: 'demo --version'\n}\n",
    )
    rows = discovered_modules(tmp_path)
    assert rows
    for row in rows:
        assert "modules.json" not in row["evidence"]
        for cited in row["evidence"]:
            # Citations may carry a :line suffix; the file itself must exist.
            path = re.sub(r":\d+(?:-\d+)?$", "", cited)
            assert (tmp_path / path).exists(), cited
