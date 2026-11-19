"""Build permission for autonomous runs and for the offline evaluation bridge.

The offline context evaluation (``scripts/context_bridge.py``) runs the real
engine with a deliberately narrow policy; granting ``build`` lets a session
exercise the whole authoring lifecycle — publication into ``splice/`` is a
deterministic service call, never pipeline execution. Export, commit, and the
never-grantable permissions keep their boundaries either way.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from agent_scripts import RouteAgent
from layer_fixtures import edit_draft_file
from multi_route import EXAMPLE, author_all, copy_fixture
from nf_splice.agents import (
    ExecutionPolicy,
    InteractionMode,
    Permission,
    SessionEngine,
)
from nf_splice.agents.permissions import PolicyViolation
from nf_splice.agents.providers.scripted import ScriptedProvider
from nf_splice.agents.state import Usage
from nf_splice.agents.toolbox import SessionToolbox, ToolMode
from nf_splice.domain import Actor, ChangeOrigin
from nf_splice.layers import ChangeContext
from nf_splice.services.lifecycle import validate_bundle

AUTHORING = [Permission.READ, Permission.DRAFT_EDIT, Permission.BUILD]
NARROW = [Permission.READ, Permission.DRAFT_EDIT]


def _bridge() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "scripts" / "context_bridge.py"
    spec = importlib.util.spec_from_file_location("context_bridge", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # The script defines dataclasses, whose decorator resolves names through
    # sys.modules, so the module must be registered before it executes.
    sys.modules["context_bridge"] = module
    spec.loader.exec_module(module)
    return module


def test_the_bridge_policy_is_narrow_plus_explicit_grants() -> None:
    bridge = _bridge()
    grants = set(bridge.policy_for(["build"]).grants)
    assert {Permission.READ, Permission.DRAFT_EDIT, Permission.BUILD} <= grants
    # Adding build never smuggles in export, commit or the optional checks.
    for never in (
        Permission.EXPORT,
        Permission.GIT_COMMIT,
        Permission.EXTERNAL_TOOLS,
        Permission.RUN_NEXTFLOW,
        Permission.NETWORK,
    ):
        assert never not in grants


def test_the_bridge_refuses_never_grantable_and_unknown_names() -> None:
    bridge = _bridge()
    with pytest.raises(PolicyViolation):
        bridge.policy_for(["credentials"])
    with pytest.raises(PolicyViolation):
        bridge.policy_for(["install"])
    with pytest.raises(PolicyViolation):
        bridge.policy_for(["publish_external"])
    with pytest.raises(PolicyViolation):
        bridge.policy_for(["buld"])


def _autonomous(root: Path, grants: list[Permission]) -> SessionEngine:
    policy = ExecutionPolicy(grants=grants)
    policy.examples = [str(EXAMPLE)]
    return SessionEngine.create(
        root,
        mode=InteractionMode.AUTONOMOUS,
        provider=ScriptedProvider(RouteAgent()),
        objective="Integrate the pipeline with SPLICE.",
        policy=policy,
        actor=Actor(label="Ada"),
    )


def test_autonomous_without_build_stops_at_a_named_blocker(
    tmp_path: Path,
) -> None:
    root = copy_fixture(tmp_path)
    engine = _autonomous(root, list(NARROW))
    asyncio.run(engine.advance())
    assert not (root / "splice" / "bundle.json").exists()
    dumped = json.dumps(
        [item.model_dump(mode="json") for item in engine.state.blockers]
    )
    assert "build permission" in dumped
    assert engine.report()["completion"] != "complete"


def test_autonomous_with_build_publishes_without_exporting(
    tmp_path: Path,
) -> None:
    root = copy_fixture(tmp_path)
    engine = _autonomous(root, list(AUTHORING))
    asyncio.run(engine.advance())
    assert (root / "splice" / "bundle.json").exists()
    assert validate_bundle(root).valid
    # Publication is the lifecycle's end; the archives and the commit are
    # separate permissions and nothing is written outside the repository.
    assert not list(root.rglob("*.zip"))
    assert not (root / ".git").exists()


def test_build_reports_expected_failures_without_publishing(
    tmp_path: Path,
) -> None:
    root = copy_fixture(tmp_path)
    author_all(root)
    edit_draft_file(
        root,
        "outputs",
        lambda data: data.update({"outputs": "not a list"}),
    )
    toolbox = SessionToolbox(
        root=root,
        policy=ExecutionPolicy(grants=list(AUTHORING)),
        mode=ToolMode.EXECUTE,
        operations={"build_bundle", "read_draft"},
        controls=set(),
        change=ChangeContext(
            actor=Actor(label="agent"), origin=ChangeOrigin.AGENT_AUTONOMOUS
        ),
        usage=Usage(),
        stage_layer=None,
    )
    result = toolbox.call("build_bundle", {})
    assert result["success"] is False, result
    assert not (root / "splice" / "bundle.json").exists()
