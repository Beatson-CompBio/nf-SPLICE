"""Typed, multi-assay pipeline capabilities from the SPLICE vocabulary.

Each test names the scenario of the assay and modality task it covers. All of
them run offline through the real catalogue, draft services, bundle compiler
and validators; the agent tests drive real sessions with the scripted
provider.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from agent_scripts import RouteAgent, _call
from layer_fixtures import ADA, write_pipeline
from multi_route import EXAMPLE, copy_fixture
from nf_splice.agents import ExecutionPolicy, InteractionMode, SessionEngine
from nf_splice.agents.protocol import ToolInvoker, TurnRequest
from nf_splice.agents.providers.scripted import ScriptedProvider
from nf_splice.agents.stages import Stage
from nf_splice.catalogue import (
    ApiVocabularySource,
    Catalogue,
    CatalogueError,
    EntityType,
    Relationship,
    compare,
    default_catalogue,
    load_live,
    packaged_snapshot,
)
from nf_splice.catalogue.model import content_document
from nf_splice.cli import app
from nf_splice.domain import Actor
from nf_splice.domain.audit import ActorKind, ChangeOrigin
from nf_splice.inspectors.assays import detect_assay_candidates
from nf_splice.layers import ChangeContext, LayerError
from nf_splice.layers.bundle import (
    add_assay_capability,
    declared_capabilities,
    validate_bundle_draft,
)
from nf_splice.services.lifecycle import validate_bundle

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "tests" / "fixtures" / "example-0.3.0" / "repository"
runner = CliRunner()


def _types(items: list[dict[str, Any]]) -> list[tuple[int, str]]:
    return [(item["entity_id"], item["label"]) for item in items]


# --------------------------------------------------- 1. offline snapshot


def test_snapshot_loads_offline_with_exact_counts_and_provenance() -> None:
    snapshot = packaged_snapshot()
    assert len(snapshot.entities) == 34
    assert len(snapshot.relationships) == 34
    assert len(snapshot.registrations) == 14
    catalogue = Catalogue(snapshot)  # validates edges, cycles, reachability
    assert catalogue.entity(316).label == "Transcriptomics"
    assert catalogue.entity(316).entity_type is EntityType.MODALITY
    assert catalogue.entity(232).entity_type is EntityType.ASSAY_METHOD
    assert catalogue.entity(71).entity_type is EntityType.ROOT
    registered = {
        item.code: (item.modality_id, item.entity_id)
        for item in catalogue.registrations()
    }
    assert registered == {
        "polya_rnaseq": (9, 232),
        "total_rnaseq": (11, 312),
        "scrna_10x_3p": (3, 1),
        "scrna_10x_5p": (15, 2),
        "smartseq": (16, 272),
        "xenium_rna": (8, 11),
        "cosmx_rna": (23, 37),
        "he_wsi": (40, 123),
        "atacseq": (41, 38),
        "wgbs": (42, 335),
        "rrbs": (43, 238),
        "targeted_bsseq": (44, 343),
        "sr_shotgun_mgx": (45, 345),
        "video_cage_mon": (46, 327),
    }
    provenance = snapshot.provenance
    assert provenance.snapshot_id == "splice-sprint-2026-10-14"
    assert provenance.digest.startswith("sha256:")
    assert set(provenance.source_files) == {
        "modality_entities.csv",
        "modality_relationships.csv",
        "Modalities.csv",
    }
    # No accession is invented anywhere in the packaged snapshot.
    assert all(item.accession_id is None for item in snapshot.registrations)
    assert "accession" not in json.dumps(content_document(snapshot))


def test_snapshot_loads_without_the_repository_or_a_network() -> None:
    code = (
        "import socket\n"
        "def refuse(*a, **k): raise OSError('network used')\n"
        "socket.socket.connect = refuse\n"
        "from nf_splice.catalogue import default_catalogue\n"
        "c = default_catalogue()\n"
        "assert len(c.entities()) == 34, len(c.entities())\n"
        "print(c.resolve_code('polya_rnaseq').assay.label)\n"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", code],
        capture_output=True,
        text=True,
        check=True,
        cwd="/",
    )
    assert result.stdout.strip() == "poly(A) RNA-seq"


# ------------------------------------------------- 2-4. classification


def test_poly_a_and_total_rna_are_assay_methods_under_transcriptomics() -> None:
    catalogue = default_catalogue()
    for code, method in (("polya_rnaseq", 232), ("total_rnaseq", 312)):
        document = catalogue.resolve_code(code).to_json()
        assert document["kind"] == "registered_assay"
        assert document["registered_code"] == code
        assert document["assay"]["entity_id"] == method
        assert document["assay"]["entity_type"] == "ASSAY_METHOD"
        assert _types(document["assay_types"]) == [(255, "Short-read RNA-seq")]
        assert _types(document["modality_subtypes"]) == [(39, "Bulk RNA-seq")]
        assert _types(document["modalities"]) == [(316, "Transcriptomics")]
        assert document["paths"] == [[method, 255, 39, 316]]
    # poly(A) is never a modality, whatever the platform calls its row.
    assert not any(
        item.entity_id == 232 for item in catalogue.entities(EntityType.MODALITY)
    )


def test_atac_seq_stops_at_assay_type_without_an_invented_method() -> None:
    document = default_catalogue().resolve_code("atacseq").to_json()
    assert document["assay"] == {
        "entity_id": 38,
        "entity_type": "ASSAY_TYPE",
        "label": "ATAC-seq",
    }
    assert document["assay_types"] == []
    assert _types(document["modality_subtypes"]) == [(52, "Chromatin accessibility")]
    assert _types(document["modalities"]) == [(100, "Epigenomics")]
    assert document["paths"] == [[38, 52, 100]]


@pytest.mark.parametrize(("code", "method"), [("xenium_rna", 11), ("cosmx_rna", 37)])
def test_spatial_assays_keep_both_modality_paths(code: str, method: int) -> None:
    document = default_catalogue().resolve_code(code).to_json()
    assert _types(document["modalities"]) == [
        (136, "Imaging"),
        (316, "Transcriptomics"),
    ]
    assert document["paths"] == [[method, 138, 278, 136], [method, 138, 280, 316]]
    assert _types(document["assay_types"]) == [
        (138, "Imaging-based spatial transcriptomics")
    ]


# ------------------------------------------------- 5. round trip and build


def _repository(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    shutil.copytree(REFERENCE, root)
    return root


def test_two_capabilities_round_trip_to_a_valid_deterministic_bundle(
    tmp_path: Path,
) -> None:
    root = _repository(tmp_path)
    for code in ("polya_rnaseq", "total_rnaseq"):
        add_assay_capability(
            root,
            code,
            ADA,
            evidence="asserted",
            rationale="The pipeline supports both library types.",
        )
    assert validate_bundle_draft(root).ready
    result = runner.invoke(
        app,
        [
            "--actor",
            "Ada",
            "build",
            "all",
            "--repository",
            str(root),
            "--replace-existing",
        ],
    )
    assert result.exit_code == 0, result.output
    report = validate_bundle(root)
    assert report.valid, [item.to_json() for item in report.issues]
    bundle_path = root / "splice" / "bundle.json"
    published = json.loads(bundle_path.read_text("utf-8"))
    capabilities = published["pipeline"]["assay_capabilities"]
    assert [item["registered_code"] for item in capabilities] == [
        "polya_rnaseq",
        "total_rnaseq",
    ]
    assert all(
        _types(item["modalities"]) == [(316, "Transcriptomics")]
        for item in capabilities
    )
    assert published["assay_vocabulary"] == default_catalogue().provenance.reference()
    first = bundle_path.read_bytes()
    runner.invoke(
        app,
        [
            "--actor",
            "Ada",
            "build",
            "all",
            "--repository",
            str(root),
            "--replace-existing",
        ],
    )
    assert bundle_path.read_bytes() == first
    # The bundle archive carries no drafts and no vocabulary source files.
    archive = tmp_path / "bundle.zip"
    result = runner.invoke(
        app,
        ["export", "--repository", str(root), "--archive-output", str(archive)],
    )
    assert result.exit_code == 0, result.output
    import zipfile

    names = zipfile.ZipFile(archive).namelist()
    assert not any(".splice-local" in name or name.endswith(".csv") for name in names)


def test_a_hand_edited_published_capability_fails_validation(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    add_assay_capability(root, "polya_rnaseq", ADA, evidence="asserted", rationale="x")
    runner.invoke(
        app,
        [
            "--actor",
            "Ada",
            "build",
            "all",
            "--repository",
            str(root),
            "--replace-existing",
        ],
    )
    path = root / "splice" / "bundle.json"
    bundle = json.loads(path.read_text("utf-8"))
    bundle["pipeline"]["assay_capabilities"][0]["modalities"] = [
        {"entity_id": 232, "label": "poly(A) RNA-seq"}
    ]
    path.write_text(json.dumps(bundle, indent=2) + "\n", "utf-8")
    rules = {item.rule for item in validate_bundle(root).issues}
    assert "assay_capability" in rules


# ------------------------------------------------- 6. rejected selections


def _broken(**changes: Any) -> Any:
    snapshot = packaged_snapshot()
    return replace(snapshot, **changes)


def test_selection_errors_have_stable_codes() -> None:
    catalogue = default_catalogue()
    cases: list[tuple[str | dict[str, Any], str]] = [
        ("made_up_assay", "unknown_code"),
        ({"registered_code": "polya_rnaseq", "label": "Total RNA-seq"}, "mismatch"),
        ({"registered_code": "polya_rnaseq", "entity_type": "MODALITY"}, "mismatch"),
        ({"entity_id": 316}, "not_an_assay"),
        ("entity:39", "not_an_assay"),
        ({"registered_code": "polya_rnaseq", "accession_id": "SPL-MOD-9"},
         "accession_not_accepted"),
        ({"registered_code": "polya_rnaseq", "entity_id": 232}, "mismatch"),
    ]  # fmt: skip
    for reference, code in cases:
        with pytest.raises(CatalogueError) as caught:
            catalogue.resolve_reference(reference)
        assert caught.value.code == code, (reference, caught.value)
    with pytest.raises(CatalogueError) as caught:
        catalogue.resolve_selection(
            ["polya_rnaseq", {"registered_code": "polya_rnaseq"}]
        )
    assert caught.value.code == "duplicate"


def test_broken_vocabularies_are_refused() -> None:
    snapshot = packaged_snapshot()
    dangling = (*snapshot.relationships, Relationship(999, 232, 9999, "modality_tree"))
    with pytest.raises(CatalogueError) as caught:
        Catalogue(replace(snapshot, relationships=dangling))
    assert caught.value.code == "broken_edge"
    looped = (*snapshot.relationships, Relationship(998, 316, 232, "modality_tree"))
    with pytest.raises(CatalogueError) as caught:
        Catalogue(replace(snapshot, relationships=looped))
    assert caught.value.code == "cycle"


def test_an_ambiguous_alias_is_held_for_review() -> None:
    snapshot = packaged_snapshot()
    entities = tuple(
        replace(item, aliases=(*item.aliases, "RNA libraries"))
        if item.entity_id in (232, 312)
        else item
        for item in snapshot.entities
    )
    catalogue = Catalogue(replace(snapshot, entities=entities))
    with pytest.raises(CatalogueError) as caught:
        catalogue.by_name("RNA libraries")
    assert caught.value.code == "ambiguous"
    assert "232" in str(caught.value) and "312" in str(caught.value)


def test_draft_problems_are_reported_per_entry(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    draft = root / ".splice-local" / "drafts" / "bundle.draft.yaml"
    text = draft.read_text("utf-8").replace(
        "  assay_capabilities: []\n",
        "  assay_capabilities:\n"
        "    - registered_code: polya_rnaseq\n"
        "      label: Transcriptomics\n"
        "      evidence: asserted\n"
        "      rationale: wrong label\n"
        "    - registered_code: total_rnaseq\n"
        "      evidence: asserted\n"
        "      rationale: ok\n"
        "    - registered_code: total_rnaseq\n"
        "      evidence: asserted\n"
        "      rationale: again\n"
        "    - registered_code: wgbs\n"
        "      evidence: documented\n"
        "      rationale: no sources given\n",
    )
    draft.write_text(text, "utf-8")
    issues = {(item.pointer, item.code) for item in validate_bundle_draft(root).issues}
    assert ("/pipeline/assay_capabilities/0", "mismatch") in issues
    assert ("/pipeline/assay_capabilities/2", "duplicate") in issues
    assert ("/pipeline/assay_capabilities/3/sources", "missing_required") in issues
    assert not validate_bundle_draft(root).ready


# ------------------------------------------------- 7. deployment support


def test_current_false_registrations_remain_declarable() -> None:
    catalogue = default_catalogue()
    current = {item.code for item in catalogue.registrations() if item.current}
    assert current == {"polya_rnaseq", "total_rnaseq"}
    assert len(catalogue.assays()) == 14  # every registration, current or not
    # current is not part of the scientific classification or the bundle.
    assert "current" not in json.dumps(catalogue.resolve_code("wgbs").to_json())


# ------------------------------------------------- 8. legacy free text


def test_legacy_free_text_modality_is_never_upgraded(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    draft = root / ".splice-local" / "drafts" / "bundle.draft.yaml"
    draft.write_text(
        draft.read_text("utf-8").replace(
            "  assay_capabilities: []\n", "  modality: RNA-seq\n"
        ),
        "utf-8",
    )
    validation = validate_bundle_draft(root)
    codes = {item.code for item in validation.issues}
    assert "legacy_modality" in codes and not validation.ready
    assert declared_capabilities(root) == []
    # A published bundle with the old key is reported, not reinterpreted.
    path = root / "splice" / "bundle.json"
    bundle = json.loads(path.read_text("utf-8"))
    bundle["pipeline"]["modality"] = "Transcriptomics"
    path.write_text(json.dumps(bundle, indent=2) + "\n", "utf-8")
    rules = {item.rule for item in validate_bundle(root).issues}
    assert "legacy_modality" in rules


# ------------------------------------------------- 9. three modes


README = (
    "# Multiroute\n\n"
    "Supports poly(A) RNA-seq and Total RNA-seq libraries "
    "(see `--library_type`).\n"
)


def _declare(request: TurnRequest, tools: ToolInvoker) -> list[str]:
    from multi_route import IDENTITY

    _call(tools, "set_identity", changes=dict(IDENTITY))
    candidates = _call(tools, "list_assay_candidates")["data"]["candidates"]
    for item in candidates:
        _call(
            tools,
            "add_assay_capability",
            reference=item["reference"],
            evidence="documented",
            rationale="The README documents this library type.",
            sources=item["locations"],
        )
    if request.purpose == "plan":
        _call(
            tools,
            "submit_stage_proposal",
            summary="Identity with the documented assays.",
            evidence=["README.md"],
            uncertainties=[],
        )
    return ["Declared the documented assays."]


def _withdraw_total(request: TurnRequest, tools: ToolInvoker) -> list[str]:
    _call(
        tools,
        "assess_objection",
        assessment="supported",
        explanation="main.nf has no total RNA route; only poly(A) is implemented.",
        evidence=["main.nf"],
    )
    # A revision is staged afresh: restate the identity and the one assay.
    from multi_route import IDENTITY

    _call(tools, "set_identity", changes=dict(IDENTITY))
    _call(
        tools,
        "add_assay_capability",
        reference="polya_rnaseq",
        evidence="documented",
        rationale="The README documents this library type.",
        sources=["README.md:3"],
    )
    _call(
        tools,
        "submit_stage_proposal",
        summary="Identity with poly(A) RNA-seq only.",
        evidence=["main.nf"],
        uncertainties=[],
    )
    return ["Revised."]


def _session(root: Path, agent: Any, mode: InteractionMode) -> SessionEngine:
    return SessionEngine.create(
        root,
        mode=mode,
        provider=ScriptedProvider(agent),
        objective="Integrate the pipeline with SPLICE.",
        policy=ExecutionPolicy(examples=[str(EXAMPLE)]),
        actor=Actor(label="Ada"),
    )


def test_assisted_assays_are_proposed_objected_revised_and_approved(
    tmp_path: Path,
) -> None:
    root = copy_fixture(tmp_path)
    (root / "README.md").write_text(README, "utf-8")
    agent = RouteAgent(
        overrides={"plan:identity": _declare, "objection:identity": _withdraw_total}
    )
    engine = _session(root, agent, InteractionMode.ASSISTED)
    asyncio.run(engine.advance())
    while engine.state.pending and engine.state.pending.stage is not Stage.IDENTITY:
        asyncio.run(engine.approve(Actor(label="Ada")))
    proposal = engine.state.pending
    assert proposal is not None and "polya_rnaseq" in proposal.diff
    assert "total_rnaseq" in proposal.diff
    assert declared_capabilities(root) == []  # nothing applied before approval

    asyncio.run(
        engine.object("Only the poly(A) route is implemented.", Actor(label="Ada"))
    )
    revised = engine.state.pending
    assert revised is not None and revised.revision == 2
    assert declared_capabilities(root) == []
    asyncio.run(engine.approve(Actor(label="Ada")))
    declared = declared_capabilities(root)
    assert [item["registered_code"] for item in declared] == ["polya_rnaseq"]
    assert declared[0]["evidence"] == "documented"
    assert declared[0]["sources"] == ["README.md:3"]


def _assert_without_evidence(request: TurnRequest, tools: ToolInvoker) -> list[str]:
    from multi_route import IDENTITY

    _call(tools, "set_identity", changes=dict(IDENTITY))
    refused = tools.call(
        "patch_draft",
        {
            "layer": "bundle",
            "operations": [
                {
                    "op": "replace",
                    "path": "/pipeline/assay_capabilities",
                    "value": [{"registered_code": "polya_rnaseq"}],
                }
            ],
        },
    )
    assert not refused["success"]
    _call(
        tools,
        "record_blocker",
        decision="Which assays does the pipeline support?",
        artefact=".splice-local/drafts/bundle.draft.yaml",
        attempted_checks=["list_assay_candidates: no assay is named"],
        suggested_resolution="Ask the developer to declare the library types.",
    )
    return ["Recorded a blocker."]


def test_autonomous_runs_never_assert_assays_and_record_blockers(
    tmp_path: Path,
) -> None:
    root = copy_fixture(tmp_path)
    agent = RouteAgent(overrides={"execute:identity": _assert_without_evidence})
    engine = _session(root, agent, InteractionMode.AUTONOMOUS)
    asyncio.run(engine.advance())
    assert declared_capabilities(root) == []
    blockers = [item for item in engine.state.blockers if not item.resolved]
    assert any("assays" in item.decision.lower() for item in blockers), blockers
    assert engine.state.stages[Stage.IDENTITY].status.value == "blocked"
    assert engine.report()["completion"] == "partial"

    # The person resumes in assisted mode, decides, and the blocker resolves.
    def decide(request: TurnRequest, tools: ToolInvoker) -> list[str]:
        from multi_route import IDENTITY

        _call(tools, "set_identity", changes=dict(IDENTITY))
        _call(
            tools,
            "submit_stage_proposal",
            summary="Identity; the person declared the assays.",
            evidence=[],
            uncertainties=[],
        )
        return ["Identity is ready for approval."]

    agent.overrides["plan:identity"] = decide
    engine.switch_mode(InteractionMode.ASSISTED, Actor(label="Ada"))
    add_assay_capability(
        root,
        "polya_rnaseq",
        ADA,
        evidence="asserted",
        rationale="The developer confirms poly(A) libraries.",
    )
    asyncio.run(engine.advance())
    for _ in range(10):
        if engine.state.stages[Stage.IDENTITY].status.value == "completed":
            break
        if engine.state.pending is None:
            break
        asyncio.run(engine.approve(Actor(label="Ada")))
    assert engine.state.stages[Stage.IDENTITY].status.value == "completed"
    assert not [
        item
        for item in engine.state.blockers
        if item.stage is Stage.IDENTITY and not item.resolved
    ]
    assert declared_capabilities(root)[0]["registered_code"] == "polya_rnaseq"


def test_only_a_person_may_assert_an_assay(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    agent = ChangeContext(
        actor=Actor(label="agent", kind=ActorKind.AGENT),
        origin=ChangeOrigin.AGENT_AUTONOMOUS,
    )
    with pytest.raises(LayerError, match="only a person"):
        add_assay_capability(
            root, "polya_rnaseq", agent, evidence="asserted", rationale="guess"
        )
    add_assay_capability(
        root,
        "polya_rnaseq",
        agent,
        evidence="documented",
        rationale="documented",
        sources=("README.md:1",),
    )
    assert declared_capabilities(root)[0]["evidence"] == "documented"


# ------------------------------------------------- 10. generic FASTQ pipeline


def test_a_generic_fastq_pipeline_gets_no_assay_candidates(tmp_path: Path) -> None:
    write_pipeline(tmp_path)
    assert detect_assay_candidates(tmp_path) == ()
    result = runner.invoke(
        app,
        ["--actor", "Ada", "init", "--repository", str(tmp_path), "--accept-detected"],
    )
    assert result.exit_code == 0, result.output
    assert declared_capabilities(tmp_path) == []
    result = runner.invoke(
        app,
        [
            "--actor",
            "Ada",
            "configure",
            "identity",
            "--repository",
            str(tmp_path),
            "--add-assay",
            "polya_rnaseq",
            "--assay-rationale",
            "The lab uses this pipeline for poly(A)-selected libraries.",
        ],
    )
    assert declared_capabilities(tmp_path)[0]["registered_code"] == "polya_rnaseq"


# ------------------------------------------------- 11. future API


def _api_rows() -> dict[str, list[dict[str, Any]]]:
    document = content_document(packaged_snapshot())
    return {
        "modality-entities": document["entities"],
        "modality-relationships": document["relationships"],
        "modalities": document["registrations"],
    }


def _fetch(rows: dict[str, Any]) -> Any:
    def fetch(url: str) -> Any:
        return rows[url.rsplit("/", 1)[-1]]

    return fetch


def test_api_source_matches_the_pinned_snapshot() -> None:
    live, result = load_live(
        ApiVocabularySource("https://splice.example/api", _fetch(_api_rows())),
        packaged_snapshot(),
    )
    assert result is not None and not result.conflicts and not result.stale
    assert live.provenance.digest == packaged_snapshot().provenance.digest
    assert live.provenance.source == "api"


def test_api_outage_falls_back_only_when_asked() -> None:
    def down(url: str) -> Any:
        raise TimeoutError("timed out")

    source = ApiVocabularySource("https://splice.example/api", down)
    with pytest.raises(CatalogueError) as caught:
        load_live(source, packaged_snapshot())
    assert caught.value.code == "unavailable"
    snapshot, result = load_live(source, packaged_snapshot(), fallback=True)
    assert result is None
    assert snapshot.provenance.source == "packaged_snapshot"
    assert "unavailable" in (snapshot.provenance.note or "")


def test_api_conflicts_are_refused_unless_reconciled() -> None:
    rows = _api_rows()
    rows["modality-entities"] = [
        {**item, "label": "PolyA"} if item["entity_id"] == 232 else item
        for item in rows["modality-entities"]
    ]
    rows["modalities"] = [
        {**item, "entity_id": 312} if item["modality_name"] == "polya_rnaseq" else item
        for item in rows["modalities"]
    ]
    source = ApiVocabularySource("https://splice.example/api", _fetch(rows))
    with pytest.raises(CatalogueError) as caught:
        load_live(source, packaged_snapshot())
    assert caught.value.code == "conflict"
    _live, result = load_live(source, packaged_snapshot(), reconcile=True)
    assert result is not None and len(result.conflicts) == 2


def test_api_additions_mark_the_snapshot_stale_and_keep_real_accessions() -> None:
    rows = _api_rows()
    rows["modalities"] = [
        {**item, "accession_id": "SPL-0009"}
        if item["modality_name"] == "polya_rnaseq"
        else item
        for item in rows["modalities"]
    ] + [
        {
            "modality_id": 99,
            "modality_name": "new_assay",
            "entity_id": 38,
            "current": False,
            "schema_version_splice": 1,
            "schema_version_ext": "1.0.0",
        }
    ]
    live = ApiVocabularySource("https://splice.example/api", _fetch(rows)).load()
    result = compare(packaged_snapshot(), live)
    assert result.stale and not result.conflicts
    accession = {item.code: item.accession_id for item in live.registrations}
    assert accession["polya_rnaseq"] == "SPL-0009"
    assert accession["total_rnaseq"] is None  # never derived


@pytest.mark.parametrize(
    "rows",
    [
        {"modality-entities": {"unexpected": True}},
        {"modality-entities": [{"entity_id": "232", "label": 5}]},
        {"modality-entities": [{"entity_id": 1, "label": "x", "entity_type": "GENE"}]},
    ],
)
def test_untrusted_api_responses_are_refused(rows: dict[str, Any]) -> None:
    merged = {**_api_rows(), **rows}
    with pytest.raises(CatalogueError) as caught:
        ApiVocabularySource("https://splice.example/api", _fetch(merged)).load()
    assert caught.value.code == "untrusted_response"


# ------------------------------------------------- CLI


def test_catalogue_commands_show_types_and_paths() -> None:
    result = runner.invoke(app, ["catalogue", "show", "xenium_rna", "--json"])
    assert result.exit_code == 0, result.output
    document = json.loads(result.output)
    assert document["entity_type"] == "ASSAY_METHOD"
    assert len(document["paths"]) == 2
    assays = runner.invoke(
        app, ["catalogue", "assays", "--modality", "Transcriptomics", "--json"]
    )
    codes = {item["registered_code"] for item in json.loads(assays.output)["assays"]}
    assert {"polya_rnaseq", "total_rnaseq", "xenium_rna"} <= codes
    assert "atacseq" not in codes
    modalities = runner.invoke(app, ["catalogue", "modalities", "--json"])
    labels = {item["label"] for item in json.loads(modalities.output)["modalities"]}
    assert labels == {
        "Behaviour",
        "Epigenomics",
        "Imaging",
        "Microbiome",
        "Transcriptomics",
    }
    unknown = runner.invoke(app, ["catalogue", "show", "made_up"])
    assert unknown.exit_code == 2
