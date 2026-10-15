"""Final session reports: verified artefacts, results, blockers and audit."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from nf_splice.agents.stages import ORDER, Stage, StageStatus, gate, spec
from nf_splice.agents.state import SessionState, SessionStore


def _published(root: Path) -> list[dict[str, str]]:
    splice = root / "splice"
    files: list[dict[str, str]] = []
    if not splice.is_dir():
        return files
    for path in sorted(splice.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if (
            not path.is_file()
            or path.is_symlink()
            or "/drafts/" in f"/{relative}/"
            or relative.startswith("splice/drafts/")
            or path.name.startswith(".nf-splice")
        ):
            continue
        files.append(
            {
                "path": relative,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return files


def build_report(
    root: Path,
    store: SessionStore,
    state: SessionState,
    assessment: dict[str, Any] | None,
) -> dict[str, Any]:
    """A truthful report: never "complete" unless the bundle is built and valid."""
    built = gate(Stage.BUILD, root)
    all_stages = all(
        state.stages[stage].status is StageStatus.COMPLETED
        for stage in ORDER
        if stage is not Stage.REPORT
    )
    contract_valid = bool(
        assessment and assessment.get("contract_validity", {}).get("status") == "valid"
    )
    complete = all_stages and built.passed and contract_valid
    blockers = [
        item.model_dump(mode="json") for item in state.blockers if not item.resolved
    ]
    limitations: list[str] = []
    if assessment:
        coverage = assessment.get("coverage_assessment", {})
        if coverage.get("statement"):
            limitations.append(coverage["statement"])
        observed = assessment.get("observed_output_compatibility", {})
        if observed.get("status") == "not_assessed":
            limitations.append(
                "No example output was supplied, so no run's outputs were classified "
                "against the catalogue."
            )
        for example in observed.get("examples", []):
            limitations.extend(example["reconciliation"].get("limitations", []))
    origins: dict[str, int] = {}
    for record in store.tool_log(state.id):
        if record.get("mode") == "execute" and record.get("outcome") == "ok":
            key = f"{record.get('session_mode', state.mode.value)}"
            origins[key] = origins.get(key, 0) + 1
    statement = (
        "Complete: every stage passed its deterministic checks and the published "
        "bundle is valid."
        if complete
        else "Partial: "
        + (f"{len(blockers)} unresolved blocker(s); " if blockers else "")
        + ("the bundle is not built and valid. " if not built.passed else "")
        + "See the stages and blockers below."
    )
    return {
        "session": state.id,
        "mode": state.mode.value,
        "objective": state.objective,
        "provider": state.provider.name,
        "completion": "complete" if complete else "partial",
        "statement": statement,
        "stages": [
            {
                "stage": stage.value,
                "title": spec(stage).title,
                "status": state.stages[stage].status.value,
                "attempts": state.stages[stage].attempts,
                "summary": state.stages[stage].summary,
                "issues": state.stages[stage].issues[:10],
            }
            for stage in ORDER
        ],
        "verified_artefacts": _published(root) if built.passed else [],
        "results": assessment or {},
        "blockers": blockers,
        "outstanding_questions": [state.pending.summary] if state.pending else [],
        "approvals": [item.model_dump(mode="json") for item in state.approvals],
        "applied_operations": origins,
        "evidence": [item.model_dump(mode="json") for item in state.evidence[-50:]],
        "audit": {
            "session_directory": str(store.session_directory(state.id)),
            "tool_log": str(store.session_directory(state.id) / "tools.jsonl"),
            "checkpoints": [item.id for item in state.checkpoints],
            "tool_calls": state.usage.tool_calls,
            "provider_turns": state.usage.provider_turns,
            "cost_usd": round(state.usage.cost_usd, 4),
        },
        "limitations": limitations,
    }


def report_text(report: dict[str, Any]) -> str:
    """The report as plain text."""
    lines = [
        f"Session {report['session']} ({report['mode']}): {report['completion']}",
        report["statement"],
        "",
        "Stages:",
    ]
    for item in report["stages"]:
        lines.append(
            f"  {item['title']}: {item['status']}"
            + (f" - {item['summary']}" if item["summary"] else "")
        )
    if report["verified_artefacts"]:
        lines += ["", "Verified artefacts:"]
        lines += [f"  {item['path']}" for item in report["verified_artefacts"]]
    results = report.get("results") or {}
    if results:
        lines += [
            "",
            "Contract validity: "
            + str(results.get("contract_validity", {}).get("status")),
            "Observed-output compatibility: "
            + str(results.get("observed_output_compatibility", {}).get("status")),
            "Coverage: "
            + str(results.get("coverage_assessment", {}).get("statement", "")),
        ]
        for check in results.get("optional_checks", []):
            lines.append(
                f"Optional check {check['name']}: {check['status']} ({check['reason']})"
            )
    if report["blockers"]:
        lines += ["", "Blockers:"]
        for item in report["blockers"]:
            lines.append(f"  [{item['stage']}] {item['decision']}")
            if item.get("artefact"):
                lines.append(f"    affects: {item['artefact']}")
            for issue in item.get("issues", [])[:5]:
                lines.append(f"    issue: {issue}")
            if item.get("suggested_resolution"):
                lines.append(f"    suggestion: {item['suggested_resolution']}")
    if report["outstanding_questions"]:
        lines += [
            "",
            "Waiting for you:",
            *[f"  {item}" for item in report["outstanding_questions"]],
        ]
    if report["limitations"]:
        lines += ["", "Limitations:", *[f"  {item}" for item in report["limitations"]]]
    audit = report["audit"]
    lines += [
        "",
        f"Audit: {audit['tool_calls']} tool call(s), {audit['provider_turns']} "
        f"provider turn(s); log {audit['tool_log']}",
    ]
    return "\n".join(lines)
