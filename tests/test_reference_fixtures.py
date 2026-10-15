"""Committed reference fixtures: one validated bundle, one incomplete draft set."""

from __future__ import annotations

import shutil
from pathlib import Path

from layer_fixtures import ADA
from nf_splice.services.lifecycle import (
    list_artifacts,
    plan_promotion,
    promote,
    validate_bundle,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _copy(name: str, root: Path) -> Path:
    target = root / name
    shutil.copytree(FIXTURES / name / "repository", target)
    return target


def test_example_bundle_validates_and_rebuilds_byte_identically(tmp_path: Path) -> None:
    repository = _copy("example-0.3.0", tmp_path)
    report = validate_bundle(repository)
    assert report.valid, report.issues
    assert {item.state.value for item in list_artifacts(repository)} == {"ready"}
    before = {
        path.relative_to(repository).as_posix(): path.read_bytes()
        for path in (repository / "splice").rglob("*")
        if path.is_file() and ".reviews" not in path.parts
    }
    assert promote(repository, None, ADA).wrote == ()
    after = {
        path.relative_to(repository).as_posix(): path.read_bytes()
        for path in (repository / "splice").rglob("*")
        if path.is_file() and ".reviews" not in path.parts
    }
    assert after == before


def test_incomplete_drafts_are_clearly_not_ingestible(tmp_path: Path) -> None:
    repository = _copy("incomplete-drafts-0.3.0", tmp_path)
    splice = repository / "splice"
    assert not (splice / "bundle.json").exists()
    drafts = sorted(path.name for path in (splice / "drafts").glob("*.draft.yaml"))
    assert len(drafts) == 6
    for name in drafts:
        assert "x-splice-draft:" in (splice / "drafts" / name).read_text(
            encoding="utf-8"
        )
    plan = plan_promotion(repository)
    assert not plan.ready and plan.blockers
    assert {item.state.value for item in list_artifacts(repository)} == {"incomplete"}
    assert validate_bundle(repository).issues[0].rule == "missing"
