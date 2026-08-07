"""Acceptance tests for reviewed software and container inventory."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nf_splice.domain import DecisionStatus
from nf_splice.services import (
    ApplicationService,
    ComponentReviewError,
    StaticChangeKind,
    unresolved_component_candidates,
)


def _module(
    root: Path,
    relative: str,
    *,
    name: str,
    tool: str,
    containers: tuple[str, ...],
) -> None:
    path = root / relative
    path.mkdir(parents=True)
    path.joinpath("meta.yml").write_text(
        f"name: {name}\ntools:\n  - {tool}:\n      description: Tool\n",
        encoding="utf-8",
    )
    expression = " :\n        ".join(f"'{item}'" for item in containers)
    path.joinpath("main.nf").write_text(
        f"process {name.upper()} {{\n    container {expression}\n\n    input:\n}}\n",
        encoding="utf-8",
    )
    path.joinpath("environment.yml").write_text(
        f"dependencies:\n  - {tool}=1.0\n", encoding="utf-8"
    )


def _repository(root: Path) -> ApplicationService:
    service = ApplicationService()
    service.initialise(
        root,
        name="pipeline",
        version="1.0.0",
        repository_url="https://github.com/org/pipeline",
    )
    items = [
        {
            "kind": "module",
            "path": "modules/local/alpha",
            "namespace": "local",
            "tool": "alpha",
            "name": "alpha",
        },
        {
            "kind": "module",
            "path": "modules/local/beta",
            "namespace": "local",
            "tool": "beta",
            "name": "beta",
        },
    ]
    (root / "modules.json").write_text(json.dumps({"items": items}), encoding="utf-8")
    _module(
        root,
        "modules/local/alpha",
        name="alpha",
        tool="alpha",
        containers=("quay.io/example/alpha:1.0",),
    )
    _module(
        root,
        "modules/local/beta",
        name="beta",
        tool="beta",
        containers=(
            "quay.io/example/beta:1.0",
            "quay.io/example/beta:2.0",
        ),
    )
    return service


def test_components_deduplicate_deterministically_and_block_conflicts(
    tmp_path: Path,
) -> None:
    service = _repository(tmp_path)
    document = service.discover_components(tmp_path)
    decisions = {item.id: item for item in document.decisions}

    assert (
        decisions["component:modules__local__alpha"].status is DecisionStatus.CANDIDATE
    )
    assert decisions["component:modules__local__beta"].status is DecisionStatus.CONFLICT
    document = service.accept_unambiguous_components(tmp_path)
    assert [item.name for item in unresolved_component_candidates(document)] == ["beta"]
    with pytest.raises(ComponentReviewError, match="conflicting versions"):
        service.review_component(tmp_path, "component:modules__local__beta")
    service.review_component(
        tmp_path,
        "component:modules__local__beta",
        version="2.0",
        container_uri="quay.io/example/beta:2.0",
    )

    service.build_static_layer(tmp_path, "components")
    repeated = service.plan_static_layer(tmp_path, "components")
    inventory = json.loads((tmp_path / "splice" / "components.json").read_text())

    assert repeated.change.kind is StaticChangeKind.UNCHANGED
    assert len(inventory["components"]) == 2
    assert len(inventory["containers"]) == 2
    assert all(item["evidence"] for item in inventory["components"])
    assert inventory["components"] == sorted(
        inventory["components"], key=lambda item: item["id"]
    )
