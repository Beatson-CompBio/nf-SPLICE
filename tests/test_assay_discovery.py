"""Scientific assay discovery and classification-gated ingestion readiness.

Scenarios A-H of the assay-discovery correction, against realistic Nextflow
fixtures: the multi-route RNA-seq pipeline (STAR or HISAT2, optional Salmon)
with and without documentation that names its library types, plus pipelines
built from real tool layouts for other domains. Agent scenarios run real
sessions; the scripted provider only stands in for the model's choices, and
every decision goes through nf-splice's deterministic services.
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from agent_scripts import RouteAgent, _call
from layer_fixtures import follow_scope
from multi_route import EXAMPLE, copy_fixture
from nf_splice.agents import ExecutionPolicy, InteractionMode, SessionEngine
from nf_splice.agents.protocol import ToolInvoker, TurnRequest
from nf_splice.agents.providers.scripted import ScriptedProvider
from nf_splice.agents.stages import Stage, StageStatus
from nf_splice.cli import app
from nf_splice.domain import Actor
from nf_splice.layers import ChangeContext
from nf_splice.layers.bundle import (
    add_assay_capability,
    declared_capabilities,
    validate_bundle_draft,
)
from nf_splice.services.assay_discovery import assess_assays
from nf_splice.services.lifecycle import validate_bundle

ROOT = Path(__file__).resolve().parents[1]
ADA = Actor(label="Ada")
PERSON = ChangeContext(actor=ADA)
runner = CliRunner()


def _unlabelled(tmp_path: Path) -> Path:
    """The RNA-seq pipeline with no document naming its library types."""
    root = copy_fixture(tmp_path)
    shutil.rmtree(root / "docs")
    return root


def _module(root: Path, name: str, container: str) -> None:
    folder = root / "modules" / "local" / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "main.nf").write_text(
        f"process {name.upper()} {{\n    container '{container}'\n"
        '    script:\n    """\n    true\n    """\n}\n',
        "utf-8",
    )


def _candidates(root: Path) -> dict[str, dict[str, Any]]:
    return {
        item["reference"]: item for item in assess_assays(root).to_json()["candidates"]
    }


def _session(root: Path, agent: Any, mode: InteractionMode) -> SessionEngine:
    return SessionEngine.create(
        root,
        mode=mode,
        provider=ScriptedProvider(agent),
        objective="Integrate the pipeline with SPLICE.",
        policy=ExecutionPolicy(examples=[str(EXAMPLE)]),
        actor=ADA,
    )


def _approve_until(engine: SessionEngine, stage: Stage) -> None:
    while engine.state.pending is not None and engine.state.pending.stage is not stage:
        asyncio.run(engine.approve(ADA))


# ------------------------------------------- A. explicit assay metadata


def test_a_documented_poly_a_is_discovered_and_proposed(tmp_path: Path) -> None:
    root = _unlabelled(tmp_path)
    (root / "docs").mkdir()
    (root / "docs" / "usage.md").write_text(
        "# Usage\n\nThe pipeline expects poly(A)-selected libraries "
        "(poly(A) RNA-seq).\n",
        "utf-8",
    )
    candidates = _candidates(root)
    polya = candidates["polya_rnaseq"]
    assert polya["status"] == "documented" and polya["confidence"] == "high"
    assert polya["entity"] == {
        "entity_id": 232,
        "entity_type": "ASSAY_METHOD",
        "label": "poly(A) RNA-seq",
    }
    assert any("docs/usage.md:3" in item["locations"] for item in polya["evidence"])
    assert polya["selectable_without_confirmation"] is True
    # Total RNA-seq stays a possibility, never confirmed by poly(A) evidence.
    assert candidates["total_rnaseq"]["status"] == "requires_verification"


# ------------------------------------------- B. assay terminology absent


def test_b_unlabelled_rna_seq_pipeline_still_gets_meaningful_candidates(
    tmp_path: Path,
) -> None:
    root = _unlabelled(tmp_path)
    text = "\n".join(
        path.read_text("utf-8", errors="replace")
        for path in root.rglob("*")
        if path.is_file()
    ).lower()
    assert "poly(a)" not in text and "total rna" not in text and "rna-seq" not in text
    assessment = assess_assays(root)
    assert [item.label for item in assessment.domains] == ["Transcriptomics"]
    assert [item.entity.entity_id for item in assessment.findings] == [255]
    candidates = _candidates(root)
    for code, method in (("polya_rnaseq", 232), ("total_rnaseq", 312)):
        item = candidates[code]
        assert item["entity"]["entity_id"] == method
        assert item["classification_level"] == "ASSAY_METHOD"
        assert item["status"] == "requires_verification"
        assert item["confidence"] == "low"
        assert item["selectable_without_confirmation"] is False
        assert "does not" in item["uncertainty"] or "not which" in item["uncertainty"]
        terms = {evidence["term"] for evidence in item["evidence"]}
        assert {"star", "hisat2", "salmon"} <= terms
    broader = candidates["entity:255"]
    assert broader["classification_level"] == "ASSAY_TYPE"
    assert broader["status"] == "supported"
    assert assessment.questions and "poly(A) RNA-seq" in assessment.questions[0]
    # Manual mode shows it without any AI provider.
    result = runner.invoke(app, ["catalogue", "recommend", "--repository", str(root)])
    assert result.exit_code == 0
    assert "Detected scientific domain: Transcriptomics [MODALITY]" in result.output
    assert "requires_verification" in result.output and "Question:" in result.output


def test_other_domains_are_classified_at_the_level_the_evidence_supports(
    tmp_path: Path,
) -> None:
    rna = _unlabelled(tmp_path / "rna")
    _module(rna, "sortmerna", "quay.io/biocontainers/sortmerna:4.3.6--h9ee0642_0")
    _module(rna, "kraken2", "quay.io/biocontainers/kraken2:2.1.3--pl5321hdcf5f25_0")
    _module(rna, "bracken", "quay.io/biocontainers/bracken:2.9--py39h1f90b4d_0")
    candidates = _candidates(rna)
    assert candidates["total_rnaseq"]["status"] == "suggested"  # rRNA removal
    assert candidates["polya_rnaseq"]["status"] == "requires_verification"
    discounted = assess_assays(rna).discounted
    assert [item["rule"] for item in discounted] == ["shotgun-metagenomics"]
    assert "sr_shotgun_mgx" not in candidates  # contamination screen only

    atac = tmp_path / "atac"
    for name, image in (
        ("bowtie2", "quay.io/biocontainers/bowtie2:2.5.4--h7071971_4"),
        ("macs2", "quay.io/biocontainers/macs2:2.2.9.1--py39hf95cd2a_0"),
        ("ataqv", "quay.io/biocontainers/ataqv:1.3.1--py310ha155cf9_1"),
    ):
        _module(atac, name, image)
    atac_candidates = _candidates(atac)
    assert set(atac_candidates) == {"atacseq"}
    assert atac_candidates["atacseq"]["classification_level"] == "ASSAY_TYPE"
    assert atac_candidates["atacseq"]["status"] == "supported"
    assert [item.label for item in assess_assays(atac).domains] == ["Epigenomics"]

    methylation = tmp_path / "methylation"
    _module(methylation, "bismark", "quay.io/biocontainers/bismark:0.24.2--hdfd78af_0")
    _module(
        methylation,
        "methyldackel",
        "quay.io/biocontainers/methyldackel:0.6.1--he4a0461_7",
    )
    statuses = {key: item["status"] for key, item in _candidates(methylation).items()}
    assert statuses == {
        "rrbs": "requires_verification",
        "wgbs": "requires_verification",
        "targeted_bsseq": "requires_verification",
    }
    # A dedicated RRBS mode names the assay: it is documented, the others not.
    (methylation / "nextflow.config").write_text("params.rrbs = false\n", "utf-8")
    statuses = {key: item["status"] for key, item in _candidates(methylation).items()}
    assert statuses["rrbs"] == "documented"
    assert statuses["wgbs"] == "requires_verification"


# ------------------------------------------- C. several supported assays


def test_c_both_documented_assays_are_published(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path)  # docs/usage.md names both library types
    candidates = _candidates(root)
    assert candidates["polya_rnaseq"]["status"] == "documented"
    assert candidates["total_rnaseq"]["status"] == "documented"
    engine = _session(root, RouteAgent(), InteractionMode.AUTONOMOUS)
    asyncio.run(engine.advance())
    assert engine.report()["completion"] == "complete"
    published = json.loads((root / "splice" / "bundle.json").read_text("utf-8"))
    codes = [
        item["registered_code"] for item in published["pipeline"]["assay_capabilities"]
    ]
    assert codes == ["polya_rnaseq", "total_rnaseq"]
    for item in published["pipeline"]["assay_capabilities"]:
        assert [entry["label"] for entry in item["modalities"]] == ["Transcriptomics"]
        assert item["assay"]["entity_type"] == "ASSAY_METHOD"
    readiness = engine.report()["readiness"]
    assert readiness["structurally_valid"] and readiness["ingestion_ready"]
    assert validate_bundle(root).valid


# ------------------------------------------- D. insufficient evidence


def _investigate_and_ask(request: TurnRequest, tools: ToolInvoker) -> list[str]:
    from multi_route import IDENTITY

    assessment = _call(tools, "assess_assays")["data"]
    if "The user's guidance:" in request.instruction:
        _call(tools, "set_identity", changes=dict(IDENTITY))
        answer = request.instruction.split("The user's guidance:", 1)[1]
        answer = answer.split("\n\nEarlier in this session", 1)[0]  # history follows
        for phrase in re.findall(r"poly\(A\)|total RNA", answer, re.IGNORECASE):
            hits = _call(tools, "search_assay_catalogue", text=phrase)
            registered = [
                hit["registered_codes"][0]
                for hit in hits["results"]
                if hit["registered_codes"]
            ]
            _call(
                tools,
                "add_assay_capability",
                reference=registered[0],
                evidence="confirmed",
                rationale=f"The developer said: {answer.strip()}",
                sources=["conversation: the developer's reply"],
            )
        follow_scope(tools)
        _call(
            tools,
            "submit_stage_proposal",
            summary="Identity with the assays the developer confirmed.",
            evidence=["assess_assays"],
            uncertainties=[],
        )
        return ["Declared the confirmed assays."]
    assert assessment["questions"], assessment
    _call(
        tools,
        "record_blocker",
        decision=assessment["questions"][0],
        artefact=".splice-local/drafts/bundle.draft.yaml",
        attempted_checks=["assess_assays", "search_source: no library type found"],
        suggested_resolution="Tell me which library types the pipeline supports.",
    )
    return [
        "I found that this pipeline processes RNA-seq FASTQ files and quantifies "
        "genes and transcripts, but its documentation does not say whether it "
        "supports poly(A)-selected libraries, total RNA libraries or both. Which "
        "does it support?"
    ]


def test_d_assisted_asks_then_resolves_the_answer(tmp_path: Path) -> None:
    root = _unlabelled(tmp_path)
    agent = RouteAgent(overrides={"plan:identity": _investigate_and_ask})
    engine = _session(root, agent, InteractionMode.ASSISTED)
    asyncio.run(engine.advance())
    _approve_until(engine, Stage.IDENTITY)
    assert engine.state.pending is None  # asked, did not invent
    assert engine.state.stages[Stage.IDENTITY].status is not StageStatus.COMPLETED
    asked = [item for item in engine.state.conversation if item.kind == "message"]
    assert "Which does it support?" in asked[-1].text
    assert declared_capabilities(root) == []

    asyncio.run(engine.reply("Both: we process poly(A) and total RNA libraries.", ADA))
    proposal = engine.state.pending
    assert proposal is not None and proposal.stage is Stage.IDENTITY
    assert "polya_rnaseq" in proposal.diff and "total_rnaseq" in proposal.diff
    assert declared_capabilities(root) == []  # nothing applied before approval
    asyncio.run(engine.approve(ADA))
    declared = declared_capabilities(root)
    assert [item["registered_code"] for item in declared] == [
        "polya_rnaseq",
        "total_rnaseq",
    ]
    assert {item["evidence"] for item in declared} == {"confirmed"}
    assert engine.state.stages[Stage.IDENTITY].status is StageStatus.COMPLETED


def _attempt_without_deciding(request: TurnRequest, tools: ToolInvoker) -> list[str]:
    from multi_route import IDENTITY

    _call(tools, "set_identity", changes=dict(IDENTITY))
    assessment = _call(tools, "assess_assays")["data"]
    chosen = [
        item for item in assessment["candidates"]
        if item["selectable_without_confirmation"]
        and item["classification_level"] == "ASSAY_METHOD"
    ]  # fmt: skip
    assert chosen == []  # nothing the evidence decides
    refused = tools.call(
        "add_assay_capability",
        {
            "reference": "polya_rnaseq",
            "evidence": "confirmed",
            "rationale": "Guessing.",
            "sources": ["none"],
        },
    )
    assert not refused["success"]  # an autonomous run cannot claim confirmation
    alternatives = [
        f"{item['entity']['label']} ({item['reference']})"
        for item in assessment["candidates"]
    ]
    _call(
        tools,
        "record_blocker",
        decision="Which assays does the pipeline support? Alternatives: "
        + "; ".join(alternatives),
        artefact=".splice-local/drafts/bundle.draft.yaml",
        attempted_checks=["assess_assays", "search_source"],
        suggested_resolution=assessment["questions"][0],
    )
    return ["Recorded the unresolved assay classification."]


def test_d_autonomous_records_an_actionable_blocker(tmp_path: Path) -> None:
    root = _unlabelled(tmp_path)
    agent = RouteAgent(overrides={"execute:identity": _attempt_without_deciding})
    engine = _session(root, agent, InteractionMode.AUTONOMOUS)
    asyncio.run(engine.advance())
    report = engine.report()
    assert report["completion"] == "partial"
    assert engine.state.stages[Stage.IDENTITY].status is StageStatus.BLOCKED
    blocker = next(item for item in engine.state.blockers if not item.resolved)
    assert "poly(A) RNA-seq (polya_rnaseq)" in blocker.decision
    assert "Total RNA-seq (total_rnaseq)" in blocker.decision
    assert not report["readiness"]["ingestion_ready"]
    assert declared_capabilities(root) == []


# ------------------------------------------- E. manual to assisted


def test_e_manual_work_then_assisted_detects_the_gap(tmp_path: Path) -> None:
    root = _unlabelled(tmp_path)
    from multi_route import IDENTITY
    from nf_splice.layers.bundle import set_identity_fields
    from nf_splice.services.workspace import initialise

    initialise(root, PERSON)
    set_identity_fields(root, dict(IDENTITY), PERSON)
    issues = {item.code for item in validate_bundle_draft(root).issues}
    assert "missing_assay_classification" in issues
    before = (root / ".splice-local" / "drafts" / "bundle.draft.yaml").read_text(
        "utf-8"
    )

    agent = RouteAgent(overrides={"plan:identity": _investigate_and_ask})
    engine = _session(root, agent, InteractionMode.ASSISTED)
    asyncio.run(engine.advance())
    assert ("plan", "identity") in agent.seen  # identity was not skipped
    instruction = next(
        item for item in engine.state.conversation if item.kind == "message"
    )
    assert instruction is not None
    after = (root / ".splice-local" / "drafts" / "bundle.draft.yaml").read_text("utf-8")
    assert after == before  # the manual identity is kept, not redone
    assert engine.state.pending is None and declared_capabilities(root) == []


# ------------------------------------------- F. autonomous to assisted


def test_f_autonomous_ambiguity_is_resolved_in_assisted_mode(tmp_path: Path) -> None:
    root = _unlabelled(tmp_path)
    agent = RouteAgent(
        overrides={
            "execute:identity": _attempt_without_deciding,
            "plan:identity": _investigate_and_ask,
        }
    )
    engine = _session(root, agent, InteractionMode.AUTONOMOUS)
    asyncio.run(engine.advance())
    assert engine.state.stages[Stage.IDENTITY].status is StageStatus.BLOCKED
    completed_before = {
        stage
        for stage, record in engine.state.stages.items()
        if record.status is StageStatus.COMPLETED
    }

    engine.switch_mode(InteractionMode.ASSISTED, ADA)
    asyncio.run(engine.advance())
    _approve_until(engine, Stage.IDENTITY)
    asyncio.run(engine.reply("Only poly(A)-selected libraries.", ADA))
    asyncio.run(engine.approve(ADA))
    for _ in range(20):
        if engine.state.pending is None:
            break
        asyncio.run(engine.approve(ADA))
    assert [item["registered_code"] for item in declared_capabilities(root)] == [
        "polya_rnaseq"
    ]
    assert engine.state.stages[Stage.IDENTITY].status is StageStatus.COMPLETED
    assert not [item for item in engine.state.blockers if not item.resolved]
    assert completed_before <= {
        stage
        for stage, record in engine.state.stages.items()
        if record.status is StageStatus.COMPLETED
    }
    report = engine.report()
    assert report["readiness"]["ingestion_ready"], report
    assert validate_bundle(root).valid


# ------------------------------------------- G. deterministic enforcement


def test_g_ingestion_readiness_requires_classification(tmp_path: Path) -> None:
    root = _unlabelled(tmp_path)
    from multi_route import author_all
    from nf_splice.layers.bundle import remove_assay_capability

    author_all(root)
    for code in ("polya_rnaseq", "total_rnaseq"):
        remove_assay_capability(root, code, PERSON)
    issue = next(
        item
        for item in validate_bundle_draft(root).issues
        if item.code == "missing_assay_classification"
    )
    assert "Short-read RNA-seq" not in issue.message or "polya_rnaseq" in issue.message
    assert "nf-splice configure identity --add-assay CODE" in issue.message
    built = runner.invoke(
        app, ["--actor", "Ada", "build", "all", "--repository", str(root)]
    )
    assert built.exit_code != 0  # an unclassified bundle is never published

    # A structurally valid bundle without classification is reported as such.
    add_assay_capability(
        root, "polya_rnaseq", PERSON, evidence="asserted", rationale="x"
    )
    runner.invoke(app, ["--actor", "Ada", "build", "all", "--repository", str(root)])
    path = root / "splice" / "bundle.json"
    bundle = json.loads(path.read_text("utf-8"))
    del bundle["pipeline"]["assay_capabilities"]
    del bundle["assay_vocabulary"]
    payload = (json.dumps(bundle, indent=2) + "\n").encode("utf-8")
    path.write_bytes(payload)
    # As if another tool had published it: the lock matches the edited file.
    import hashlib

    lock_path = root / "splice" / "nf-splice.lock.json"
    lock = json.loads(lock_path.read_text("utf-8"))
    lock["managed_files"]["bundle.json"]["sha256"] = hashlib.sha256(payload).hexdigest()
    lock_path.write_text(json.dumps(lock, indent=2) + "\n", "utf-8")
    report = validate_bundle(root)
    assert report.levels() == {
        "structurally_valid": True,
        "scientifically_classified": False,
    }
    result = runner.invoke(app, ["validate", "--repository", str(root)])
    assert result.exit_code == 2
    assert (
        "Structurally valid: yes; scientifically classified: no; ready for "
        "ingestion: no." in result.output
    )
    assert "missing_assay_classification" in result.output


# ------------------------------------------- H. repository hygiene


def test_h_no_platform_proposal_and_no_private_data_in_git_or_bundles(
    tmp_path: Path,
) -> None:
    assert not (ROOT / "docs" / "integration").exists()
    tracked = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files"],
        capture_output=True,
        text=True,
        check=True,
        env={"GIT_CEILING_DIRECTORIES": "", "PATH": "/usr/bin:/bin"},
    ).stdout.splitlines()
    assert not any("splice-platform-assay-capabilities" in path for path in tracked)
    assert not any(
        "/sessions/" in path or path.endswith("events.jsonl") for path in tracked
    )
    for path in tracked:
        if path.endswith(".md") and (ROOT / path).is_file():
            text = (ROOT / path).read_text("utf-8").lower()
            assert "platform team" not in text, path
    root = copy_fixture(tmp_path)
    from multi_route import author_all, build

    author_all(root)
    build(root)
    published = {
        path.relative_to(root / "splice").as_posix()
        for path in (root / "splice").rglob("*")
        if path.is_file()
    }
    assert not any(".splice-local" in path or "session" in path for path in published)


def test_manual_review_shows_rejects_and_selects_recommendations(
    tmp_path: Path,
) -> None:
    root = _unlabelled(tmp_path)
    runner.invoke(
        app, ["--actor", "Ada", "init", "--repository", str(root), "--accept-detected"]
    )
    rejected = runner.invoke(
        app,
        [
            "--actor",
            "Ada",
            "configure",
            "identity",
            "--repository",
            str(root),
            "--reject-assay",
            "total_rnaseq",
            "--assay-rationale",
            "Our protocol uses poly(A) selection only.",
        ],
    )
    # Nothing declared yet: the recommendations are shown, without any AI.
    assert "Detected scientific domain: Transcriptomics" in rejected.output
    assert "total_rnaseq" in rejected.output and "rejected" in rejected.output
    assert _candidates(root)["total_rnaseq"]["status"] == "rejected"
    accepted = runner.invoke(
        app,
        [
            "--actor",
            "Ada",
            "configure",
            "identity",
            "--repository",
            str(root),
            "--add-assay",
            "polya_rnaseq",
            "--assay-rationale",
            "The developer confirms poly(A)-selected libraries.",
        ],
    )
    assert "Detected scientific domain" not in accepted.output
    assert [item["registered_code"] for item in declared_capabilities(root)] == [
        "polya_rnaseq"
    ]
    assert not any(
        item.code == "missing_assay_classification"
        for item in validate_bundle_draft(root).issues
    )
