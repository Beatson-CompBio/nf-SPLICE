"""Assess, decide on and check the pipeline's RO-Crate (ADR-0065).

The same services back the command line and the agents:

- :func:`assess_crate` reads the repository's own crate and the authored
  draft graph and says, with reasons, whether to keep the authored graph,
  adopt the root crate, correct a copy of it, or regenerate one, and whether
  nf-core's generator is installed and applicable. It runs nothing.
- :func:`check_crate` checks the draft graph as it would be published:
  nf-splice's own structural checks always, and the Workflow RO-Crate
  standards profile with ``rocrate-validator`` only when that is installed
  and permitted. The two results are reported separately, so a structural
  pass is never presented as a standards pass.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Collection
from pathlib import Path
from typing import Any

from nf_splice.layers import provenance as provenance_layer
from nf_splice.layers.base import read_layer, strip_marker
from nf_splice.services.checks import (
    EXTERNAL_TOOLS,
    CheckResult,
    CheckStatus,
    Runner,
    is_nf_core_pipeline,
    rocrate_validation,
)

KEEP = "keep"
ADOPT = "adopt"
CORRECT = "correct"
REGENERATE = "regenerate"

#: Strategy names the agents and the CLI accept, mapped to the layer's
#: operations; the earlier names of the same unreleased contract are kept.
STRATEGIES = {
    ADOPT: ADOPT,
    "include": ADOPT,
    CORRECT: CORRECT,
    "enriched": CORRECT,
    REGENERATE: REGENERATE,
    "generated": REGENERATE,
}


#: Findings about disagreement with the reviewed identity, which a corrected
#: copy fixes; any other blocking finding is structural.
_IDENTITY_CODES = frozenset({"missing_value", "stale_value", "missing_author"})


def _draft(root: Path) -> tuple[dict[str, Any] | None, str | None]:
    state = read_layer(root, provenance_layer.LAYER)
    if state.draft is None or not isinstance(state.draft.data, dict):
        return None, None
    data = strip_marker(state.draft.data)
    crate = data.get("crate")
    origin = data.get("origin") or data.get("strategy")
    return (crate if isinstance(crate, dict) else None), (
        str(origin) if origin else None
    )


def _generator(root: Path, executable: str) -> dict[str, Any]:
    installed = shutil.which(executable)
    nf_core, why = is_nf_core_pipeline(root)
    has_schema = (root / "nextflow_schema.json").is_file()
    applicable = (root / "nextflow.config").is_file() and (nf_core or has_schema)
    reason = (
        why
        if nf_core
        else "the layout nf-core's generator accepts (nextflow.config and "
        "nextflow_schema.json)"
        if applicable
        else "nf-core's generator is inapplicable: it expects nextflow.config "
        "and nextflow_schema.json; author the crate in the draft instead"
    )
    return {
        "tool": "nf-core pipelines rocrate",
        "installed": installed is not None,
        "applicable": applicable,
        "reason": reason,
        "permissions": [EXTERNAL_TOOLS, "network"],
    }


def assess_crate(
    repository_root: str | Path, *, nf_core_executable: str = "nf-core"
) -> dict[str, Any]:
    """The root crate, the authored graph and what to do next (read-only)."""
    root = Path(repository_root).resolve()
    analysis = provenance_layer.analyse_ro_crate(root)
    crate, origin = _draft(root)
    validation = provenance_layer.validate_provenance_draft(root)
    draft_errors = [
        f"{item.pointer or '/'} [{item.code}] {item.message}"
        for item in validation.issues
        if item.severity.value == "error"
    ]
    draft_warnings = [
        f"{item.pointer or '/'} [{item.code}] {item.message}"
        for item in validation.issues
        if item.severity.value == "warning"
    ]
    reasons: list[str] = []
    if crate is not None and not draft_errors:
        action = KEEP
        reasons.append(
            f"the authored graph (origin: {origin or 'unknown'}) validates; review "
            "its content and correct it in the draft where needed"
        )
    elif not analysis.present:
        action = REGENERATE
        reasons.append("the repository has no ro-crate-metadata.json of its own")
    elif any(item.code == "json" for item in analysis.findings):
        action = REGENERATE
        reasons.append("the repository's RO-Crate is not valid JSON")
    elif analysis.blocking:
        structural = [
            item for item in analysis.blocking if item.code not in _IDENTITY_CODES
        ]
        action = REGENERATE if structural else CORRECT
        reasons.extend(item.message for item in analysis.blocking[:5])
    else:
        action = ADOPT
        reasons.append("the repository's RO-Crate agrees with the reviewed identity")
    # Key order matters to callers: interfaces clip oversized results, so the
    # actionable part (what to do, what the draft says) must come first and
    # the potentially long root-crate findings come last.
    return {
        "recommendation": {"action": action, "reasons": reasons},
        "draft": {
            "present": crate is not None,
            "origin": origin,
            "errors": draft_errors,
            "warnings": draft_warnings,
        },
        "root_crate": {
            "present": analysis.present,
            "sha256": analysis.sha256,
            "findings": [item.to_json() for item in analysis.findings],
        },
        "generator": _generator(root, nf_core_executable),
        "validator": {
            "tool": "rocrate-validator",
            "installed": shutil.which("rocrate-validator") is not None,
        },
    }


def check_crate(
    repository_root: str | Path,
    *,
    permitted: Collection[str] = (),
    runner: Runner = subprocess.run,
) -> dict[str, Any]:
    """Structural and standards checks of the graph as it would be published."""
    root = Path(repository_root).resolve()
    crate, _origin = _draft(root)
    validation = provenance_layer.validate_provenance_draft(root)
    structural_errors = [
        f"{item.pointer or '/'} [{item.code}] {item.message}"
        for item in validation.issues
        if item.severity.value == "error"
    ]
    structural_status = "failed" if structural_errors or crate is None else "passed"
    structural: dict[str, Any] = {
        "scope": "nf-splice structural and identity checks of the draft graph",
        "status": structural_status,
        "errors": structural_errors,
        "warnings": [
            f"{item.pointer or '/'} [{item.code}] {item.message}"
            for item in validation.issues
            if item.severity.value == "warning"
        ],
    }
    compiled = validation.files.get(provenance_layer.SOURCE)
    if compiled is None:
        standards = CheckResult(
            "RO-Crate workflow-ro-crate-1.0",
            CheckStatus.NOT_APPLICABLE,
            "the draft graph does not pass nf-splice's structural checks yet",
            "rocrate-validator",
        )
    else:
        standards = rocrate_validation(
            root,
            permitted=permitted,
            runner=runner,
            crate=json.loads(compiled),
        )
    return {
        "structural": structural,
        "standards": standards.to_json(),
        "statement": _statement(structural_status, standards),
    }


def _statement(structural: str, standards: CheckResult) -> str:
    status = standards.status.value
    if status == CheckStatus.PASSED.value:
        return (
            "The graph passes nf-splice's structural checks and the Workflow "
            "RO-Crate 1.0 profile (rocrate-validator)."
        )
    if status == CheckStatus.FAILED.value:
        return (
            f"Structural checks {structural}; the Workflow RO-Crate 1.0 profile "
            "failed (rocrate-validator)."
        )
    return (
        f"Structural checks {structural}; Workflow RO-Crate standards validation "
        f"{status.replace('_', ' ')} ({standards.reason}). Only the structural "
        "checks are established."
    )
