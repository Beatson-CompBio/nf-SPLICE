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


def _git_state(root: Path, state: SessionState) -> dict[str, Any]:
    from nf_splice.services import gitops

    current = gitops.status(root)
    return {
        "repository": current.repository,
        "branch": current.branch,
        "head": current.head,
        "uncommitted_bundle_changes": current.owned,
        "committed_in_session": bool(state.commit and state.commit.get("committed")),
    }


def _readiness(root: Path) -> dict[str, Any]:
    """Structurally valid, scientifically classified and ingestion-ready, apart."""
    from nf_splice.layers.bundle import declared_capabilities, rejected_assays
    from nf_splice.services.assay_discovery import assess_assays
    from nf_splice.services.lifecycle import validate_bundle

    published = (root / "splice" / "bundle.json").is_file()
    report = validate_bundle(root) if published else None
    declared = [
        str(item.get("registered_code") or f"entity:{item.get('entity_id')}")
        for item in declared_capabilities(root)
    ]
    questions: list[str] = []
    if not declared:
        questions = list(assess_assays(root, rejected=rejected_assays(root)).questions)
    return {
        "bundle_published": published,
        "structurally_valid": bool(report and report.structurally_valid),
        "scientifically_classified": bool(report and report.classified and declared),
        "ingestion_ready": bool(report and report.valid and declared),
        "assay_capabilities": declared,
        "open_assay_questions": questions,
    }


def build_report(
    root: Path,
    store: SessionStore,
    state: SessionState,
    assessment: dict[str, Any] | None,
) -> dict[str, Any]:
    """A truthful report: never "complete" unless the bundle is built and valid."""
    built = gate(Stage.BUILD, root)
    readiness = _readiness(root)
    all_stages = all(
        state.stages[stage].status in {StageStatus.COMPLETED, StageStatus.SKIPPED}
        for stage in ORDER
        if stage is not Stage.REPORT
    )
    contract_valid = bool(
        assessment and assessment.get("contract_validity", {}).get("status") == "valid"
    )
    observed_status = (
        (assessment or {}).get("observed_output_compatibility", {}).get("status")
    )
    incompatible = observed_status == "incompatible"
    complete = (
        all_stages
        and built.passed
        and contract_valid
        and not incompatible
        and readiness["ingestion_ready"]
    )
    blockers = [
        item.model_dump(mode="json") for item in state.blockers if not item.resolved
    ]
    limitations: list[str] = []
    if assessment:
        coverage = assessment.get("coverage_assessment", {})
        if coverage.get("statement"):
            limitations.append(coverage["statement"])
        observed = assessment.get("observed_output_compatibility", {})
        if incompatible:
            limitations.append(
                "Supplied example output is not compatible with the catalogue "
                "(unclassified, ambiguous or unidentified files); the integration is "
                "not complete until the catalogue or the example is corrected."
            )
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
        + (
            "the pipeline's assays are not classified, so it is not ready for "
            "ingestion. "
            if not readiness["scientifically_classified"]
            else ""
        )
        + ("supplied example output is incompatible. " if incompatible else "")
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
        "archive": state.export,
        "readiness": readiness,
        "git": _git_state(root, state),
        "remote": "not pushed: nf-splice never pushes automatically; use "
        "`nf-splice git push --remote NAME --yes`",
        "provider_verification": (
            "offline scripted provider: no live model was used"
            if state.provider.name == "scripted"
            else f"live provider {state.provider.name}"
            + (f" ({state.provider.model})" if state.provider.model else "")
            + f"; inference {state.provider.inference}; billing "
            f"{state.provider.billing}"
        ),
        "providers_used": [
            {"provider": name, **values}
            for name, values in sorted(state.usage.by_provider.items())
        ],
        "provider_history": list(state.provider_history),
        "outstanding_questions": [state.pending.summary] if state.pending else [],
        "approvals": [item.model_dump(mode="json") for item in state.approvals],
        "applied_operations": origins,
        "evidence": [item.model_dump(mode="json") for item in state.evidence[-50:]],
        "audit": {
            "session_directory": str(store.session_directory(state.id)),
            "event_log": str(store.session_directory(state.id) / "events.jsonl"),
            "checkpoints": [item.id for item in state.checkpoints],
            "tool_calls": state.usage.tool_calls,
            "provider_turns": state.usage.provider_turns,
            "cost_usd": (
                round(state.usage.cost_usd, 4)
                if state.usage.cost_reported
                else "not_reported"
            ),
        },
        "limitations": limitations,
    }


def report_text(report: dict[str, Any]) -> str:
    """The report as plain text."""
    lines = [
        f"Session {report['session']} ({report['mode']}): {report['completion']}",
        report["statement"],
        "",
    ]
    readiness = report.get("readiness") or {}
    if readiness:
        lines += [
            "Structurally valid bundle: "
            + ("yes" if readiness["structurally_valid"] else "no"),
            "Scientifically classified pipeline: "
            + ("yes" if readiness["scientifically_classified"] else "no")
            + (
                f" ({', '.join(readiness['assay_capabilities'])})"
                if readiness["assay_capabilities"]
                else ""
            ),
            "Ingestion-ready SPLICE bundle: "
            + ("yes" if readiness["ingestion_ready"] else "no"),
        ]
        lines += [
            f"  Open question: {item}" for item in readiness["open_assay_questions"]
        ]
        lines.append("")
    lines += ["Stages:"]
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
    archive = report.get("archive")
    if archive:
        lines += [
            "",
            f"Archive: {archive['path']} ({archive['size']} bytes, SHA-256 "
            f"{archive['sha256']}), verified: {archive['verified']}",
        ]
    git_state = report.get("git") or {}
    if git_state.get("repository"):
        lines.append(
            f"Git: branch {git_state.get('branch')}, "
            + (
                "bundle committed in this session"
                if git_state.get("committed_in_session")
                else f"{len(git_state.get('uncommitted_bundle_changes', []))} "
                "uncommitted bundle change(s)"
            )
        )
    lines.append(f"Remote: {report.get('remote')}")
    lines.append(f"Provider: {report.get('provider_verification')}")
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
        f"provider turn(s); log {audit['event_log']}",
    ]
    return "\n".join(lines)
