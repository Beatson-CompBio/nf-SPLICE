"""Helpers shared by step views."""

from __future__ import annotations

from pathlib import Path

from nf_splice.services.lifecycle import validate_layer


def issue_lines(repository: Path, layer: str) -> str:
    """Readable per-field issues of one layer (or a ready message)."""
    validation = validate_layer(repository, layer)
    if not validation.issues:
        return "No issues: this layer is ready to promote."
    return "\n".join(
        f"{item.severity.value.upper()} {item.pointer or '/'} "
        f"[{item.code}] {item.message}"
        for item in validation.issues
    )
