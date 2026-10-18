"""Deterministic tool fixes from the round-5 offline context evaluation.

Each test pins one finding an evaluator recorded verbatim: a patch replayed
onto a draft that already holds the values was a silent success (the stale
base was swallowed); ``read_source`` capped long files with no word on how
to continue; route analysis harvested pipelines from ``tests/``; and an
offline evaluator deliberating a turn could only watch the 1800-second
budget burn an attempt.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from multi_route import author_all, copy_fixture
from nf_splice.agents.permissions import ExecutionPolicy
from nf_splice.agents.state import Usage
from nf_splice.agents.toolbox import SessionToolbox, ToolMode
from nf_splice.domain import Actor, ChangeOrigin
from nf_splice.drafts.patch import PatchConflict, PatchOp, merge, replay_note
from nf_splice.layers import ChangeContext

_DECOY = """\
nextflow.enable.dsl = 2
workflow DECOY_ROUTE {
    main:
    DECOY_PUB()
    publish:
    path "decoy-out/*.txt"
}
process DECOY_PUB {
    output:
    path "*.txt"
    script:
    echo hi > decoy-out.txt
}
"""


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


def test_a_replayed_base_mismatch_is_collected_not_silently_right() -> None:
    document = {"a": 1}
    replayed: list[PatchConflict] = []
    merged, conflicts = merge(
        document, [PatchOp("replace", "/a", 1, expected=9)], replayed=replayed
    )
    assert merged == document and conflicts == []  # the replay stays tolerated
    assert [(c.path, c.expected, c.actual) for c in replayed] == [("/a", 9, 1)]
    # A matching or omitted base leaves nothing to explain.
    assert replay_note(document, [PatchOp("replace", "/a", 1, expected=1)]) is None
    assert replay_note(document, [PatchOp("replace", "/a", 1)]) is None
    note = replay_note(document, [PatchOp("replace", "/a", 1, expected=9)])
    assert note is not None
    assert note.startswith("no text change")
    assert "/a" in note and "expected 9" in note and "found 1" in note


def test_a_stale_base_replay_explains_itself_through_the_tool(
    tmp_path: Path,
) -> None:
    root = copy_fixture(tmp_path)
    author_all(root)
    tools = _toolbox(root, {"patch_draft"})
    value = "https://example.invalid/support"
    first = tools.call(
        "patch_draft",
        {
            "layer": "bundle",
            "operations": [
                {"op": "replace", "path": "/pipeline/repository_url", "value": value}
            ],
        },
    )
    assert first["success"] and first["wrote"] and "note" not in first
    replayed = tools.call(
        "patch_draft",
        {
            "layer": "bundle",
            "operations": [
                {
                    "op": "replace",
                    "path": "/pipeline/repository_url",
                    "value": value,
                    "expected": "WRONG-SENTINEL",
                }
            ],
        },
    )
    assert replayed["success"] is True and replayed["wrote"] is False
    note = replayed.get("note", "")
    assert "already as planned" in note and "WRONG-SENTINEL" in note, replayed
    # A wrong base where the value differs is still a loud conflict.
    clash = tools.call(
        "patch_draft",
        {
            "layer": "bundle",
            "operations": [
                {
                    "op": "replace",
                    "path": "/pipeline/repository_url",
                    "value": "https://other.invalid/x",
                    "expected": "WRONG-SENTINEL",
                }
            ],
        },
    )
    assert clash["success"] is False
    dumped = json.dumps(clash)
    assert "WRONG-SENTINEL" in dumped and "/pipeline/repository_url" in dumped


def test_read_source_tells_the_reader_how_to_continue(tmp_path: Path) -> None:
    (tmp_path / "long.nf").write_text(
        "\n".join(f"// line {number}" for number in range(1, 451)) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "short.nf").write_text("// only line\n", encoding="utf-8")
    tools = _toolbox(tmp_path, {"read_source"})
    paged = tools.call("read_source", {"path": "long.nf"})["data"]
    assert paged["lines"] == [1, 400] and paged["total_lines"] == 450
    assert paged["next_start_line"] == 401
    assert "start_line=401" in paged["note"]
    whole = tools.call("read_source", {"path": "short.nf"})["data"]
    assert "note" not in whole and "next_start_line" not in whole


def test_route_analysis_never_harvests_workflows_from_tests(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path)
    decoy = root / "tests" / "fixtures" / "other"
    decoy.mkdir(parents=True)
    (decoy / "main.nf").write_text(_DECOY, encoding="utf-8")
    tools = _toolbox(root, {"analyse_routes"})
    routes = tools.call("analyse_routes", {})
    assert routes["success"]
    dumped = json.dumps(routes)
    assert "DECOY" not in dumped  # no row, note or entry choice mentions it
    assert "tests/" not in dumped


def test_status_and_plan_call_a_fresh_publication_current(tmp_path: Path) -> None:
    from layer_fixtures import edit_draft_file
    from nf_splice.services.lifecycle import list_artifacts, plan_promotion

    root = copy_fixture(tmp_path)
    author_all(root)
    built = _toolbox(root, {"build_bundle"}).call("build_bundle", {})
    assert built["success"], built
    states = {f.path: f.state for a in list_artifacts(root) for f in a.finals}
    assert states["bundle.json"] == "current"
    kinds = {c.path: c.kind for c in plan_promotion(root).changes}
    assert kinds["bundle.json"] == "unchanged"
    # A genuine edit after the build is still outdated for both.
    edit_draft_file(
        root, "bundle", lambda data: data["pipeline"].update({"description": "edited"})
    )
    states = {f.path: f.state for a in list_artifacts(root) for f in a.finals}
    assert states["bundle.json"] == "outdated"


def test_the_bridge_can_extend_the_provider_turn_budget() -> None:
    import importlib.util
    import sys

    path = Path(__file__).resolve().parents[1] / "scripts" / "context_bridge.py"
    spec = importlib.util.spec_from_file_location("context_bridge_r5", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["context_bridge_r5"] = module
    spec.loader.exec_module(module)
    assert module.policy_for([]).budgets.turn_timeout_seconds == 1800.0
    assert module.policy_for([], 3600.0).budgets.turn_timeout_seconds == 3600.0
    with pytest.raises(ValidationError):
        module.policy_for([], 99_999.0)  # the engine's own maximum still applies
