"""Authoritative bundle.draft.yaml identity layer."""

from __future__ import annotations

from pathlib import Path

import pytest

from nf_splice.domain import Actor, ChangeOrigin
from nf_splice.drafts import DraftConflictError
from nf_splice.layers import ChangeContext, LayerError, confirm_values
from nf_splice.layers.base import load_review_state
from nf_splice.layers.bundle import (
    require_identity,
    seed_bundle_draft,
    set_identity_fields,
    validate_bundle_draft,
)

DRAFT = "splice/drafts/bundle.draft.yaml"
ADA = ChangeContext(actor=Actor(label="Ada"))


def _pipeline(root: Path, *, cff_version: str = "1.2.0") -> None:
    (root / "nextflow.config").write_text(
        "manifest {\n"
        "    name = 'rnaquant'\n"
        "    version = '1.2.0'\n"
        "    homePage = 'https://github.com/org/rnaquant'\n"
        "    description = 'Quantifies RNA-seq reads.'\n"
        "    nextflowVersion = '!>=24.04.0'\n"
        "    contributors = [\n"
        "        [name: 'Ada Lovelace', affiliation: 'Analytical Engines', "
        "orcid: 'https://orcid.org/0000-0002-1825-0097'],\n"
        "        [name: 'Charles Babbage']\n"
        "    ]\n"
        "}\n",
        encoding="utf-8",
    )
    (root / "CITATION.cff").write_text(
        "cff-version: 1.2.0\n"
        f"version: {cff_version}\n"
        "doi: 10.5281/zenodo.1234567\n"
        "license: MIT\n",
        encoding="utf-8",
    )


def _issues(root: Path) -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for item in validate_bundle_draft(root).issues:
        found.setdefault(item.code, set()).add(item.pointer)
    return found


def test_seeding_creates_a_real_incomplete_draft_with_unconfirmed_evidence(
    tmp_path: Path,
) -> None:
    _pipeline(tmp_path)
    result = seed_bundle_draft(tmp_path)
    assert result.created and not result.conflicts
    text = (tmp_path / DRAFT).read_text(encoding="utf-8")
    assert "x-splice-draft:" in text and "status: draft" in text
    assert "project_url: null" in text
    assert not (tmp_path / "splice" / "nf-splice.yaml").exists()

    issues = _issues(tmp_path)
    assert {"/pipeline/name", "/pipeline/version", "/pipeline/id"} <= issues[
        "unconfirmed_detected_value"
    ]
    assert not validate_bundle_draft(tmp_path).ready

    pending = sorted(issues["unconfirmed_detected_value"])
    confirm_values(tmp_path, "bundle", pending, ADA)
    validation = validate_bundle_draft(tmp_path)
    assert validation.ready, validation.issues
    metadata = require_identity(tmp_path)
    assert metadata.id == "rnaquant"
    assert [item.name for item in metadata.authors] == [
        "Ada Lovelace",
        "Charles Babbage",
    ]
    assert metadata.citation is not None and metadata.citation.doi == (
        "10.5281/zenodo.1234567"
    )
    assert metadata.engine_version_min == "24.04.0"
    assert list(metadata.ordered_document())[:4] == ["id", "name", "version", "engine"]


def test_seeding_never_overwrites_and_conflicts_are_not_chosen(tmp_path: Path) -> None:
    _pipeline(tmp_path, cff_version="2.0.0")
    result = seed_bundle_draft(tmp_path)
    assert "/pipeline/version" in result.conflicts
    assert "conflicting_evidence" in _issues(tmp_path)
    path = tmp_path / DRAFT
    edited = path.read_text(encoding="utf-8").replace(
        "  version: null", "  version: 1.2.0  # chosen by the developer"
    )
    path.write_text(edited, encoding="utf-8")
    assert not seed_bundle_draft(tmp_path).created
    assert path.read_text(encoding="utf-8") == edited
    assert "conflicting_evidence" not in _issues(tmp_path)


def test_direct_edits_count_as_authored_and_survive_tool_patches(
    tmp_path: Path,
) -> None:
    _pipeline(tmp_path)
    seed_bundle_draft(tmp_path)
    path = tmp_path / DRAFT
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "name: rnaquant", "name: RNA Quant  # display name"
        ),
        encoding="utf-8",
    )
    assert "/pipeline/name" not in _issues(tmp_path).get(
        "unconfirmed_detected_value", set()
    )

    proposal = set_identity_fields(
        tmp_path,
        {"title": "Example"},
        ChangeContext(
            actor=Actor(label="assistant"),
            origin=ChangeOrigin.AGENT_SUGGESTION,
            approved=False,
        ),
        write=False,
    )
    assert "+  title: Example" in proposal.diff and not proposal.wrote
    with pytest.raises(LayerError, match="explicit approval"):
        set_identity_fields(
            tmp_path,
            {"title": "Example"},
            ChangeContext(actor=Actor(label="assistant"), approved=False),
        )
    applied = set_identity_fields(tmp_path, {"title": "Example"}, ADA)
    text = path.read_text(encoding="utf-8")
    assert applied.wrote and "# display name" in text and "title: Example" in text
    events = load_review_state(tmp_path, "bundle").events
    assert events[-1]["action"] == "set_identity"
    assert events[-1]["actor"]["label"] == "Ada"


def test_concurrent_edit_of_the_same_field_conflicts(tmp_path: Path) -> None:
    _pipeline(tmp_path)
    seed_bundle_draft(tmp_path)
    path = tmp_path / DRAFT
    from nf_splice.drafts import read_yaml

    planned = read_yaml(tmp_path, DRAFT)
    assert planned.draft is not None
    path.write_text(
        path.read_text(encoding="utf-8").replace("version: 1.2.0", "version: 9.9.9"),
        encoding="utf-8",
    )
    from nf_splice.layers.base import edit_draft, ops_for

    with pytest.raises(DraftConflictError):
        edit_draft(
            tmp_path,
            "bundle",
            ops_for(planned.draft.data, {"/pipeline/version": "1.3.0"}),
            ADA,
        )
    assert "version: 9.9.9" in path.read_text(encoding="utf-8")


def test_specific_identity_review_issues(tmp_path: Path) -> None:
    _pipeline(tmp_path)
    seed_bundle_draft(tmp_path)
    set_identity_fields(
        tmp_path,
        {
            "name": "rnaquant",
            "version": "1.2.0",
            "id": "rnaquant",
            "repository_url": "https://github.com/org/rnaquant",
            "project_url": "not a url",
            "release_url": "https://github.com/org/rnaquant/releases/tag/1.0.0",
            "engine_version_min": "23.04.0",
            "licence": "TODO",
            "authors": [{"name": "Org", "type": "organization", "orcid": "x"}],
            "maintainers": [{"name": "Ada", "email": "ada@lab.ac.uk"}],
        },
        ADA,
    )
    issues = _issues(tmp_path)
    assert "/pipeline/project_url" in issues["invalid_value"]
    assert "/pipeline/release_url" in issues["stale_release_url"]
    assert "/pipeline/engine_version_min" in issues["contradictory_engine_version"]
    assert "/pipeline/licence" in issues["placeholder"]
    assert any(
        item.startswith("/pipeline/authors/0") for item in issues["invalid_value"]
    )
    assert "/maintainers_publication_approved" in issues["publication_consent"]
    with pytest.raises(LayerError, match="not ready"):
        require_identity(tmp_path)


def test_missing_and_malformed_drafts_are_reported(tmp_path: Path) -> None:
    assert _issues(tmp_path) == {"missing_draft": {""}}
    (tmp_path / "splice" / "drafts").mkdir(parents=True)
    (tmp_path / DRAFT).write_text("pipeline: [\n", encoding="utf-8")
    assert "syntax" in _issues(tmp_path)
    assert not seed_bundle_draft(tmp_path).created
    assert (tmp_path / DRAFT).read_text(encoding="utf-8") == "pipeline: [\n"
