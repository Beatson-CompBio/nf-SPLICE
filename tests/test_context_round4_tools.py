"""Deterministic tool fixes from the round-2 offline context evaluation.

Each test pins one deficiency an evaluator hit for real: patch staleness
against redacted reads, the ``/`` section, unbounded inventories, clipped
crate advice, citation vocabulary, and clip hints naming arguments the
tool does not offer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from multi_route import author_all, copy_fixture
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
