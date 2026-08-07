"""Deterministic rendering for reviewed execution environments."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from nf_splice.domain import AuthoringDocument, DecisionStatus, LayerStatus
from nf_splice.domain.execution import ReviewedExecutionProfile


class ExecutionProfileRenderError(ValueError):
    """Raised when reviewed execution state cannot be rendered."""


@dataclass(frozen=True, slots=True)
class RenderedExecution:
    """Byte-stable execution-profile index and config payloads."""

    profiles: str
    configs: tuple[tuple[str, str], ...]


def reviewed_execution_profiles(
    document: AuthoringDocument,
) -> tuple[ReviewedExecutionProfile, ...]:
    """Return explicitly supported profiles from a ready execution layer."""
    layer = next(
        (item for item in document.layers if item.name == "execution_profiles"),
        None,
    )
    if layer is None or layer.status is not LayerStatus.READY:
        raise ExecutionProfileRenderError(
            "execution profiles are not ready; review every detected environment"
        )
    decisions = {item.id: item for item in document.decisions}
    reviewed: list[ReviewedExecutionProfile] = []
    for decision_id in layer.decision_ids:
        decision = decisions[decision_id]
        if decision.status is DecisionStatus.REJECTED:
            continue
        if decision.status is not DecisionStatus.REVIEWED:
            raise ExecutionProfileRenderError(
                f"execution profile {decision_id!r} has not been reviewed"
            )
        try:
            reviewed.append(ReviewedExecutionProfile.model_validate(decision.value))
        except ValidationError as error:
            raise ExecutionProfileRenderError(
                f"execution profile {decision_id!r} is invalid: {error}"
            ) from error
    if not reviewed:
        raise ExecutionProfileRenderError(
            "select at least one officially supported execution profile"
        )
    profile_ids = [item.id for item in reviewed]
    if len(profile_ids) != len(set(profile_ids)):
        raise ExecutionProfileRenderError(
            "reviewed execution profile ids must be unique"
        )
    return tuple(sorted(reviewed, key=lambda item: item.id))


def _read_config(root: Path, relative: str) -> str:
    requested = root / relative
    if requested.is_symlink():
        raise ExecutionProfileRenderError(
            f"execution config source is not a regular file: {relative}"
        )
    path = requested.resolve()
    try:
        path.relative_to(root)
    except ValueError as error:
        raise ExecutionProfileRenderError(
            f"execution config source escapes the repository: {relative}"
        ) from error
    if not path.is_file():
        raise ExecutionProfileRenderError(
            f"execution config source is not a regular file: {relative}"
        )
    return path.read_text(encoding="utf-8").replace("\r\n", "\n").rstrip() + "\n"


def render_execution(
    document: AuthoringDocument, repository_root: str | Path
) -> RenderedExecution:
    """Render the selected profile index and approved config source text."""
    root = Path(repository_root).resolve()
    reviewed = reviewed_execution_profiles(document)
    profiles = {
        "schema_version": "1.0",
        "profiles": [
            {
                "id": item.id,
                "name": item.name,
                "description": item.description,
                "use": item.use.value,
                "engine": "nextflow",
                "executor": item.executor,
                "container_engine": item.container_engine,
                "config": item.config_path,
            }
            for item in reviewed
        ],
    }
    configs = []
    for item in reviewed:
        sections = []
        for source in item.config_sources:
            content = _read_config(root, source)
            if source == f"splice/{item.config_path}" and len(item.config_sources) == 1:
                sections.append(content)
            else:
                sections.append(f"// Source: {source}\n{content}")
        configs.append((item.config_path, "\n".join(sections)))
    return RenderedExecution(
        profiles=json.dumps(profiles, indent=2, ensure_ascii=False) + "\n",
        configs=tuple(configs),
    )
