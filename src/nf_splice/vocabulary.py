"""SPLICE-owned public nomenclature and reserved-word checks.

``manifest`` is reserved for a different SPLICE platform concept. nf-splice
never uses it for the workflow bundle, its index, the contract registry or
any emitted key, identifier or label. The only permitted occurrence is the
literal upstream Nextflow configuration syntax parsed as input evidence in
``nf_splice.inspectors.identity``.
"""

from __future__ import annotations

import re

RESERVED_TERMS = ("manifest",)
_RESERVED = re.compile(r"manifest", re.IGNORECASE)

#: Precise meanings of the platform units used throughout nf-splice.
GLOSSARY = {
    "bundle": "The static SPLICE integration published below splice/.",
    "bundle file index": "The files map of bundle.json naming every final artefact.",
    "contract registry": "The packaged mapping of nf-splice releases to the five "
    "workflow-bundle contract family revisions.",
    "job": "One submitted workflow invocation/execution with its combined inputs "
    "and job-wide outputs.",
    "sample": "One biological or experimental sample; sample-scoped outputs "
    "aggregate that sample's data.",
    "run": "One SPLICE platform file-level or acquisition-level unit belonging to "
    "a sample; never a workflow-engine execution.",
    "engine execution metadata": "Engine-native session, task or execution "
    "identifiers of a job, explicitly qualified by engine.",
}


def reserved_terms_in(text: str) -> tuple[str, ...]:
    """Return every reserved term occurring in SPLICE-owned text."""
    return tuple(match.group(0) for match in _RESERVED.finditer(text))
