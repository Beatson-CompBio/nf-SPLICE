"""The working-copy layout: private .splice-local/, published splice/, migration."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from layer_fixtures import ADA, ready_repository
from nf_splice import layout
from nf_splice.cli import app
from nf_splice.layers import LayerError
from nf_splice.layers.base import read_layer
from nf_splice.services import migration
from nf_splice.services.lifecycle import promote, validate_bundle

FIXTURES = Path(__file__).parent / "fixtures"
runner = CliRunner()
LEGACY_NAMES = {
    "bundle.draft.yaml": "bundle.draft.yaml",
    "inputs.draft.yaml": "inputs.schema.draft.yaml",
    "outputs.draft.yaml": "outputs.draft.yaml",
    "components.draft.yaml": "components.draft.yaml",
    "execution-profiles.draft.yaml": "execution-profiles.draft.yaml",
    "provenance.draft.yaml": "ro-crate-metadata.draft.yaml",
}


def _git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        text=True,
        env={
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.org",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.org",
            "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
        },
    ).stdout


def _hashes(base: Path) -> dict[str, str]:
    return {
        path.relative_to(base).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(base.rglob("*"))
        if path.is_file()
    }


def test_ignore_rule_is_added_once_and_existing_rules_are_kept(tmp_path: Path) -> None:
    ready_repository(tmp_path)
    ignore = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert ignore.splitlines().count("/.splice-local/") == 1
    assert (tmp_path / ".splice-local" / "drafts" / "bundle.draft.yaml").is_file()
    assert not (tmp_path / "splice" / "drafts").exists()

    second = tmp_path / "second"
    second.mkdir()
    (second / ".gitignore").write_text("results/\n*.log", encoding="utf-8")
    assert layout.ensure_ignore_rule(second) is True
    assert layout.ensure_ignore_rule(second) is False
    lines = (second / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert lines[:2] == ["results/", "*.log"]
    assert lines.count("/.splice-local/") == 1


def test_tracked_private_state_is_refused_until_untracked(tmp_path: Path) -> None:
    if not layout.git_available():
        pytest.skip("git is not installed")
    root = tmp_path / "pipeline"
    root.mkdir()
    (root / "main.nf").write_text("workflow {}\n", encoding="utf-8")
    (root / ".splice-local").mkdir()
    (root / ".splice-local" / "notes.txt").write_text("private", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "tracks private state")
    with pytest.raises(layout.WorkspaceLayoutError, match="workspace untrack"):
        layout.prepare_private_workspace(root)
    checked = runner.invoke(app, ["workspace", "check", "--repository", str(root)])
    assert checked.exit_code == 2 and "Git tracks 1 file(s)" in checked.output
    refused = runner.invoke(app, ["workspace", "untrack", "--repository", str(root)])
    assert refused.exit_code == 2
    untracked = runner.invoke(
        app, ["workspace", "untrack", "--yes", "--repository", str(root)]
    )
    assert untracked.exit_code == 0, untracked.output
    assert (root / ".splice-local" / "notes.txt").is_file()  # kept on disk
    assert layout.tracked_private_paths(root) == []
    assert _git(root, "log", "--oneline").count("\n") == 1  # history unchanged
    layout.prepare_private_workspace(root)


def test_case_collisions_and_symlinks_are_refused(tmp_path: Path) -> None:
    root = tmp_path / "pipeline"
    root.mkdir()
    (root / "SPLICE").mkdir()
    assert layout.case_collisions(root) == ["SPLICE"]
    with pytest.raises(layout.WorkspaceLayoutError, match="case"):
        layout.prepare_private_workspace(root)

    linked = tmp_path / "linked"
    linked.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (linked / ".splice-local").symlink_to(elsewhere)
    with pytest.raises(layout.WorkspaceLayoutError, match="symbolic link"):
        layout.prepare_private_workspace(linked)


def _legacy_copy(tmp_path: Path) -> Path:
    """The example fixture laid out the way earlier builds wrote it."""
    root = tmp_path / "legacy"
    shutil.copytree(FIXTURES / "example-0.3.0" / "repository", root)
    private = root / ".splice-local"
    drafts = root / "splice" / "drafts"
    (drafts / ".reviews").mkdir(parents=True)
    for new, old in LEGACY_NAMES.items():
        shutil.move(private / "drafts" / new, drafts / old)
    for review in (private / "reviews").glob("*.review.json"):
        shutil.move(review, drafts / ".reviews" / review.name)
    shutil.rmtree(private)
    session = root / ".nf-splice-local" / "agent" / "sessions" / "session-1"
    (session / "checkpoints" / "checkpoint-1" / "splice" / "drafts").mkdir(parents=True)
    (session / "session.json").write_text('{"format": "1"}', encoding="utf-8")
    (session / "tools.jsonl").write_text('{"tool": "x"}\n', encoding="utf-8")
    shutil.copy(
        drafts / "bundle.draft.yaml",
        session / "checkpoints" / "checkpoint-1" / "splice" / "drafts",
    )
    return root


def test_legacy_layout_is_refused_until_migrated(tmp_path: Path) -> None:
    root = _legacy_copy(tmp_path)
    with pytest.raises(LayerError, match="nf-splice migrate --check"):
        read_layer(root, "bundle")


def test_migration_moves_verifies_and_rolls_back(tmp_path: Path) -> None:
    root = _legacy_copy(tmp_path)
    before = _hashes(root)
    plan = migration.plan_migration(root)
    assert plan.needed and not plan.conflicts
    targets = {move.target for move in plan.moves}
    assert ".splice-local/drafts/inputs.draft.yaml" in targets
    assert ".splice-local/drafts/provenance.draft.yaml" in targets
    assert ".splice-local/reviews/outputs.review.json" in targets
    assert ".splice-local/sessions/session-1/events.jsonl" in targets
    assert (
        ".splice-local/sessions/session-1/checkpoints/checkpoint-1/"
        ".splice-local/drafts/bundle.draft.yaml"
    ) in targets
    assert _hashes(root) == before  # --check changes nothing

    checked = runner.invoke(app, ["migrate", "--check", "--repository", str(root)])
    assert checked.exit_code == 0 and "move: splice/drafts/" in checked.output
    applied = runner.invoke(app, ["migrate", "--apply", "--repository", str(root)])
    assert applied.exit_code == 0, applied.output
    assert not (root / "splice" / "drafts").exists()
    assert not (root / ".nf-splice-local" / "agent").exists()
    for move in plan.moves:
        content = (root / move.target).read_bytes()
        assert hashlib.sha256(content).hexdigest() == move.sha256
    assert "/.splice-local/" in (root / ".gitignore").read_text(encoding="utf-8")

    # Migrated drafts publish exactly the same bundle.
    expected = _hashes(FIXTURES / "example-0.3.0" / "repository" / "splice")
    promote(root, None, ADA)
    assert validate_bundle(root).valid
    assert _hashes(root / "splice") == expected

    again = runner.invoke(app, ["migrate", "--apply", "--repository", str(root)])
    assert again.exit_code == 0 and "Nothing to migrate." in again.output

    rolled = runner.invoke(app, ["migrate", "--rollback", "--repository", str(root)])
    assert rolled.exit_code == 0, rolled.output
    assert (root / "splice" / "drafts" / "bundle.draft.yaml").is_file()
    assert not (root / ".splice-local" / "drafts" / "bundle.draft.yaml").exists()
    record = migration.migrations(root)[0]
    assert record["status"] == "rolled_back"


def test_migration_never_overwrites_and_survives_interruption(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _legacy_copy(tmp_path)
    target = root / ".splice-local" / "drafts" / "bundle.draft.yaml"
    target.parent.mkdir(parents=True)
    target.write_text("unrelated: content\n", encoding="utf-8")
    plan = migration.plan_migration(root)
    assert any(
        "already exists with different content" in item for item in plan.conflicts
    )
    with pytest.raises(migration.MigrationError, match="before changing anything"):
        migration.apply_migration(root)
    assert target.read_text(encoding="utf-8") == "unrelated: content\n"

    target.unlink()
    before = _hashes(root / "splice")
    calls = {"count": 0}
    original = shutil.copy2

    def failing_copy(source: Path, destination: Path) -> object:
        calls["count"] += 1
        if calls["count"] > len(plan.moves) + 2:
            raise OSError("disk full")
        return original(source, destination)

    monkeypatch.setattr(shutil, "copy2", failing_copy)
    with pytest.raises(OSError, match="disk full"):
        migration.apply_migration(root)
    monkeypatch.setattr(shutil, "copy2", original)
    assert _hashes(root / "splice") == before
    assert not (root / ".splice-local" / "drafts").exists() or not any(
        (root / ".splice-local" / "drafts").iterdir()
    )
    assert migration.migrations(root) == []
    assert migration.apply_migration(root)["migrated"] is True


def test_workspace_navigation_is_kept_with_the_working_copy(tmp_path: Path) -> None:
    from nf_splice.interfaces.tui.store import (
        NavigationState,
        NavigationStore,
        default_session_directory,
        repository_key,
    )

    ready_repository(tmp_path)
    directory = default_session_directory(tmp_path, environment={})
    assert directory == tmp_path.resolve() / ".splice-local" / "sessions" / "workspace"
    store = NavigationStore(directory)
    store.save(tmp_path, NavigationState(repository_key=repository_key(tmp_path)))
    saved = list(directory.glob("*.json"))
    assert len(saved) == 1
    assert json.loads(saved[0].read_text("utf-8"))["current_page"] == "welcome"
