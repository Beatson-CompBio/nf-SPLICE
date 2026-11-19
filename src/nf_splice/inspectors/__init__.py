"""Read-only repository inspectors."""

from nf_splice.inspectors.identity import inspect_pipeline_identity
from nf_splice.inspectors.repository import inspect_repository
from nf_splice.inspectors.splice_tree import inspect_splice_tree

__all__ = [
    "inspect_pipeline_identity",
    "inspect_repository",
    "inspect_splice_tree",
]
