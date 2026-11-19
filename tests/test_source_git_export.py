"""Source isolation, local Git commits and verified ZIP export."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from layer_fixtures import ADA, ready_repository, write_pipeline
from nf_splice.cli import app
from nf_splice.services import gitops
from nf_splice.services.export import ExportError, ExportScope, export_archive
from nf_splice.services.lifecycle import promote, validate_bundle
from nf_splice.services.source import SourceError, prepare_integration_copy

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
runner = CliRunner()
IDENTITY = {
    "GIT_AUTHOR_NAME": "Ada Lovelace",
    "GIT_AUTHOR_EMAIL": "ada@example.org",
    "GIT_COMMITTER_NAME": "Ada Lovelace",
    "GIT_COMMITTER_EMAIL": "ada@example.org",
}


@pytest.fixture(autouse=True)
def _isolated_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "gitconfig"
    config.write_text(
        "[user]\n\tname = Ada Lovelace\n\temail = ada@example.org\n"
        "[init]\n\tdefaultBranch = main\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


def _git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        text=True,
        env=dict(os.environ) | IDENTITY,
    ).stdout.strip()


def _tree(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file() and ".git" not in path.relative_to(root).parts
    }


def _git_pipeline(root: Path) -> Path:
    root.mkdir(parents=True)
    write_pipeline(root)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "pipeline")
    return root


def test_plain_folder_is_copied_and_initialised(tmp_path: Path) -> None:
    source = tmp_path / "pipeline"
    source.mkdir()
    write_pipeline(source)
    (source / "work").mkdir()
    (source / "work" / "big.bam").write_text("x", encoding="utf-8")
    (source / ".nextflow.log").write_text("log", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    (source / "link.txt").symlink_to(outside)
    before = _tree(source)

    copy = prepare_integration_copy(str(source), tmp_path / "copy")
    target = Path(copy.path)
    assert copy.source_kind == "directory"
    assert copy.branch == "nf-splice/integration-pipeline"
    assert (target / "main.nf").is_file()
    assert not (target / "work").exists()
    assert not (target / ".nextflow.log").exists()
    assert not (target / "link.txt").exists()
    assert any("symbolic link" in item for item in copy.skipped)
    assert _git(target, "log", "--format=%an <%ae> %s") == (
        "Ada Lovelace <ada@example.org> Import pipeline for SPLICE integration"
    )
    assert "/.splice-local/" in (target / ".gitignore").read_text(encoding="utf-8")
    assert (target / ".splice-local" / "integration.json").is_file()
    assert _git(target, "ls-files", ".splice-local") == ""
    assert _tree(source) == before


def test_git_sources_are_cloned_onto_a_branch_and_left_unchanged(
    tmp_path: Path,
) -> None:
    source = _git_pipeline(tmp_path / "pipeline")
    (source / "main.nf").write_text("// edited\n", encoding="utf-8")  # dirty
    (source / "new.nf").write_text("// new\n", encoding="utf-8")
    head = _git(source, "rev-parse", "HEAD")
    status = _git(source, "status", "--porcelain")

    copy = prepare_integration_copy(str(source), tmp_path / "clean")
    target = Path(copy.path)
    assert copy.source_kind == "git_local" and copy.source_head == head
    assert sorted(copy.uncommitted_in_source) == ["main.nf", "new.nf"]
    assert _git(target, "branch", "--show-current") == "nf-splice/integration-pipeline"
    assert (target / "main.nf").read_text(encoding="utf-8") != "// edited\n"
    assert not (target / "new.nf").exists()

    imported = prepare_integration_copy(
        str(source), tmp_path / "with-changes", include_uncommitted=True
    )
    assert imported.imported_uncommitted
    assert (Path(imported.path) / "new.nf").read_text(encoding="utf-8") == "// new\n"
    assert _git(source, "rev-parse", "HEAD") == head
    assert _git(source, "status", "--porcelain") == status
    assert _git(source, "branch", "--list", "nf-splice/*") == ""

    # Detached HEAD and an explicit ref both work.
    _git(source, "stash", "-u")
    _git(source, "checkout", "-q", "--detach")
    detached = prepare_integration_copy(str(source), tmp_path / "detached", ref=head)
    assert Path(detached.path, "main.nf").is_file()


def test_urls_clone_and_errors_are_actionable(tmp_path: Path) -> None:
    source = _git_pipeline(tmp_path / "pipeline")
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(source), str(bare)], check=True)
    copy = prepare_integration_copy(f"file://{bare}", tmp_path / "from-url")
    assert copy.source_kind == "git_remote"
    assert Path(copy.path, "main.nf").is_file()

    with pytest.raises(SourceError, match=r"not found|cannot read|failed"):
        prepare_integration_copy(f"file://{tmp_path}/missing.git", tmp_path / "x")
    with pytest.raises(SourceError, match="does not exist"):
        prepare_integration_copy(str(source), tmp_path / "bad-ref", ref="no-such-tag")


def test_destinations_are_never_overwritten_or_nested(tmp_path: Path) -> None:
    source = tmp_path / "pipeline"
    source.mkdir()
    write_pipeline(source)
    busy = tmp_path / "busy"
    busy.mkdir()
    (busy / "keep.txt").write_text("x", encoding="utf-8")
    with pytest.raises(SourceError, match="not empty"):
        prepare_integration_copy(str(source), busy)
    with pytest.raises(SourceError, match="inside the pipeline"):
        prepare_integration_copy(str(source), source / "copy")
    locked = tmp_path / "locked"
    locked.mkdir(mode=0o500)
    try:
        with pytest.raises((OSError, SourceError)):
            prepare_integration_copy(str(source), locked / "copy")
    finally:
        locked.chmod(0o700)


def test_missing_identity_and_missing_git_are_explained(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "pipeline"
    source.mkdir()
    write_pipeline(source)
    empty = tmp_path / "empty-config"
    empty.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))
    for name in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "EMAIL"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(SourceError, match="no identity"):
        prepare_integration_copy(str(source), tmp_path / "no-identity")
    named = prepare_integration_copy(
        str(source),
        tmp_path / "named",
        git_name="Grace Hopper",
        git_email="grace@example.org",
    )
    assert _git(Path(named.path), "log", "--format=%an") == "Grace Hopper"

    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(SourceError, match="Git is not installed"):
        prepare_integration_copy(str(source), tmp_path / "no-git", use_git=True)
    plain = prepare_integration_copy(str(source), tmp_path / "plain", use_git=False)
    assert plain.branch is None and not Path(plain.path, ".git").exists()


def test_in_place_needs_explicit_consent(tmp_path: Path) -> None:
    source = tmp_path / "pipeline"
    source.mkdir()
    write_pipeline(source)
    refused = runner.invoke(app, ["source", "prepare", str(source), "--in-place"])
    assert refused.exit_code == 2 and "--yes" in refused.output
    accepted = runner.invoke(
        app, ["source", "prepare", str(source), "--in-place", "--yes", "--json"]
    )
    assert accepted.exit_code == 0, accepted.output
    assert (source / ".splice-local" / "integration.json").is_file()


def _built_copy(tmp_path: Path) -> Path:
    source = _git_pipeline(tmp_path / "pipeline")
    copy = Path(prepare_integration_copy(str(source), tmp_path / "copy").path)
    shutil.rmtree(copy / "modules")
    (copy / "modules.json").unlink()
    (copy / "nextflow_schema.json").unlink()
    (copy / "main.nf").unlink()
    if (copy / "conf").exists():
        shutil.rmtree(copy / "conf")
    (copy / "nextflow.config").unlink()
    ready_repository(copy)
    return copy


def test_commits_only_the_validated_bundle(tmp_path: Path) -> None:
    copy = _built_copy(tmp_path)
    with pytest.raises(gitops.GitOperationError, match="does not validate"):
        gitops.commit(copy, "too early")
    promote(copy, None, ADA)
    current = gitops.status(copy)
    assert any(path.startswith("splice/") for path in current.owned)
    assert not any(
        path.startswith(".splice-local") for path in current.owned + current.other
    )
    (copy / "notes.txt").write_text("x", encoding="utf-8")
    _git(copy, "add", "notes.txt")
    with pytest.raises(gitops.GitOperationError, match="already staged"):
        gitops.commit(copy, "mixed")
    _git(copy, "reset", "-q", "notes.txt")
    result = gitops.commit(copy, "Publish the SPLICE bundle")
    assert result["committed"]
    committed = _git(copy, "show", "--name-only", "--format=", "HEAD").split()
    assert all(path.startswith("splice/") or path == ".gitignore" for path in committed)
    assert not any(path.startswith(".splice-local") for path in committed)
    assert gitops.commit(copy, "again")["committed"] is False
    with pytest.raises(gitops.GitOperationError, match="private"):
        gitops.commit(copy, "x", extra_paths=[".splice-local/drafts"])


def test_push_is_explicit_and_checked(tmp_path: Path) -> None:
    copy = _built_copy(tmp_path)
    promote(copy, None, ADA)
    gitops.commit(copy, "Publish")
    with pytest.raises(gitops.GitOperationError, match="not configured"):
        gitops.push(copy, "upstream")
    refused = runner.invoke(
        app, ["git", "push", "--remote", "origin", "--repository", str(copy)]
    )
    assert refused.exit_code == 2 and "--yes" in refused.output
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    _git(copy, "remote", "add", "share", str(remote))
    pushed = gitops.push(copy, "share")
    assert pushed["pushed"]
    assert (
        _git(remote, "branch", "--list")
        .strip()
        .endswith("nf-splice/integration-pipeline")
    )
    _git(copy, "remote", "add", "gone", str(tmp_path / "missing.git"))
    with pytest.raises(gitops.GitOperationError, match="dry-run push failed"):
        gitops.push(copy, "gone")


def test_exports_are_deterministic_verified_and_private_free(tmp_path: Path) -> None:
    copy = _built_copy(tmp_path)
    with pytest.raises(ExportError, match="build the bundle first"):
        export_archive(copy)
    promote(copy, None, ADA)
    gitops.commit(copy, "Publish")
    (copy / ".env").write_text("TOKEN=1\n", encoding="utf-8")

    bundle = export_archive(copy, ExportScope.BUNDLE)
    assert bundle.verified and bundle.path.endswith("-splice-bundle.zip")
    assert ".splice-local/exports/" in bundle.path
    names = zipfile.ZipFile(bundle.path).namelist()
    assert all(name.startswith("splice/") for name in names)
    with pytest.raises(ExportError, match="already exists"):
        export_archive(copy, ExportScope.BUNDLE)
    again = export_archive(copy, ExportScope.BUNDLE, overwrite=True)
    assert again.sha256 == bundle.sha256  # deterministic

    pipeline = export_archive(copy, ExportScope.PIPELINE, tmp_path / "pipeline.zip")
    archive = zipfile.ZipFile(pipeline.path)
    members = archive.namelist()
    # A Workflow RO-Crate: the pipeline at the archive root, with the reviewed
    # crate as the root descriptor (the published one, byte for byte).
    assert "main.nf" in members or "nextflow.config" in members
    assert "splice/bundle.json" in members
    assert (
        archive.read("ro-crate-metadata.json")
        == (copy / "splice" / "ro-crate-metadata.json").read_bytes()
    )
    assert any("archive-root ro-crate" in item for item in pipeline.checks)
    assert not any(".splice-local" in name or ".git/" in name for name in members)
    assert not any(name.endswith(".env") for name in members)
    extracted = tmp_path / "extracted"
    archive.extractall(extracted)
    assert validate_bundle(extracted).valid

    with pytest.raises(ExportError, match="include itself"):
        export_archive(copy, ExportScope.PIPELINE, copy / "inside.zip")
    (copy / "splice" / "notes.json").write_text(
        '{"k": "ghp_' + "a" * 36 + '"}', "utf-8"
    )
    with pytest.raises(ExportError, match="credentials"):
        export_archive(copy, ExportScope.BUNDLE, tmp_path / "leak.zip")
    (copy / "splice" / "notes.json").unlink()

    draft = copy / ".splice-local" / "drafts" / "bundle.draft.yaml"
    draft.write_text(
        draft.read_text(encoding="utf-8").replace(
            "Quantifies RNA-seq reads.", "Quantifies RNA-seq reads per sample."
        ),
        encoding="utf-8",
    )
    with pytest.raises(ExportError, match="out of date"):
        export_archive(copy, ExportScope.BUNDLE, tmp_path / "stale.zip")


def test_cli_export_and_git_commands(tmp_path: Path) -> None:
    copy = _built_copy(tmp_path)
    promote(copy, None, ADA)
    status = runner.invoke(app, ["git", "status", "--repository", str(copy)])
    assert "bundle change: splice/" in status.output
    committed = runner.invoke(app, ["git", "commit", "--repository", str(copy)])
    assert committed.exit_code == 0 and "Committed" in committed.output
    exported = runner.invoke(
        app,
        ["export", "--archive-scope", "pipeline", "--repository", str(copy)],
    )
    assert exported.exit_code == 0, exported.output
    assert "verified: the extracted bundle validates" in exported.output
    assert "SHA-256:" in exported.output
