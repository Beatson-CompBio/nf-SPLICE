"""Shared builders for file-first layer tests."""

from __future__ import annotations

from pathlib import Path

from nf_splice.domain import Actor
from nf_splice.layers import ChangeContext
from nf_splice.layers.bundle import seed_bundle_draft, validate_bundle_draft

ADA = ChangeContext(actor=Actor(label="Ada"))
IDENTITY = {
    "id": "rnaquant",
    "name": "rnaquant",
    "version": "1.2.0",
    "repository_url": "https://github.com/org/rnaquant",
    "description": "Quantifies RNA-seq reads.",
}


def ready_identity(root: Path) -> None:
    """Create an explicitly authored, ready bundle.draft.yaml."""
    seed_bundle_draft(root, explicit=IDENTITY)
    validation = validate_bundle_draft(root)
    assert validation.ready, validation.issues
