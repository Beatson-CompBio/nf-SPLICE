"""Pipeline identity helpers shared by every detached contract."""

from __future__ import annotations

import re


class PipelineIdError(ValueError):
    """Raised when a pipeline name cannot form a stable bundle identifier."""


def derive_pipeline_id(name: str) -> str:
    """Derive the stable, collision-safe slug used as the pipeline ``id``.

    The identifier is derived once from the reviewed name; later display-name
    changes must not silently re-identify an existing bundle.
    """
    identifier = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not identifier:
        raise PipelineIdError("pipeline name cannot form a stable bundle id")
    return identifier
