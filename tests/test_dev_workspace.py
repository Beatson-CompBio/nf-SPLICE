"""Development workspace isolation and staged-path guard."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _guard() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "check_staged_paths", ROOT / "scripts" / "check_staged_paths.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_gitignore_anchors_the_local_workspace() -> None:
    lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "/.nf-splice-local/" in lines
    assert "/.splice-local/" in lines
    for broad in ("*.yaml", "*.json", "tests/", "docs/", "splice/", "src/"):
        assert broad not in lines


@pytest.mark.parametrize(
    "path",
    [
        ".nf-splice-local/agent/notes.md",
        ".nf-splice-local/sessions/abc.json",
        ".splice-local",
        ".splice-local/drafts/outputs.draft.yaml",
        ".splice-local/sessions/abc/session.json",
        ".splice-local/reviews/outputs.review.json",
        ".env",
        "deploy/credentials.json",
        "keys/server.pem",
        "splice/.bundle.json.nf-splice.tmp",
    ],
)
def test_guard_rejects_development_only_and_secret_paths(path: str) -> None:
    assert _guard().violations([path]) == [path]


@pytest.mark.parametrize(
    "path",
    [
        "src/nf_splice/cli.py",
        "tests/fixtures/example-0.3.0/repository/splice/bundle.json",
        "docs/ARCHITECTURE_DECISIONS.md",
        "splice/bundle.json",
        "splice/configs/local.config",
        "tests/fixtures/example-0.3.0/repository/.splice-local/drafts/bundle.draft.yaml",
    ],
)
def test_guard_accepts_committable_paths(path: str) -> None:
    assert _guard().violations([path]) == []


def test_local_workspace_is_ignored_by_git() -> None:
    if not (ROOT / ".git").exists():
        pytest.skip("not running from a Git checkout")
    result = subprocess.run(
        ("git", "-C", str(ROOT), "check-ignore", "-q", ".nf-splice-local/agent/x"),
        check=False,
    )
    assert result.returncode == 0


def test_guard_reads_literal_staged_names_even_when_git_would_quote_them(
    tmp_path: Path,
) -> None:
    """A secret below a non-ASCII folder is still refused (NUL-delimited names)."""
    import os

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    secret = tmp_path / "données" / "credentials.json"
    secret.parent.mkdir()
    secret.write_text("{}", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    quoted = subprocess.run(
        ["git", "-C", str(tmp_path), "diff", "--cached", "--name-only"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert quoted.startswith('"')  # Git's default display would hide the name
    previous = Path.cwd()
    os.chdir(tmp_path)
    try:
        assert _guard()._staged_paths() == ["données/credentials.json"]
        assert _guard().main([]) == 1
    finally:
        os.chdir(previous)


def test_dev_env_keeps_credentials_outside_the_clone(tmp_path: Path) -> None:
    script = (
        f"cd {ROOT} && unset NF_SPLICE_CONFIG_DIR && export HOME={tmp_path} "
        "XDG_CONFIG_HOME= && . scripts/dev-env.sh && echo $NF_SPLICE_CONFIG_DIR "
        "&& unset NF_SPLICE_CONFIG_DIR && . scripts/dev-env.sh "
        "&& echo $NF_SPLICE_CONFIG_DIR"
    )
    result = subprocess.run(
        ["sh", "-c", script], capture_output=True, text=True, check=True
    )
    first, second = result.stdout.split()
    assert first == second == f"{tmp_path}/.config/nf-splice"


def test_guard_rejects_force_added_private_state(tmp_path: Path) -> None:
    """``git add -f`` bypasses .gitignore; the guard still refuses it."""
    run = {"cwd": tmp_path, "check": True, "capture_output": True}
    subprocess.run(("git", "init", "-q"), **run)  # type: ignore[call-overload]
    (tmp_path / ".gitignore").write_text("/.splice-local/\n", encoding="utf-8")
    (tmp_path / ".splice-local" / "drafts").mkdir(parents=True)
    (tmp_path / ".splice-local" / "drafts" / "bundle.draft.yaml").write_text(
        "x: 1\n", encoding="utf-8"
    )
    (tmp_path / "splice").mkdir()
    (tmp_path / "splice" / "bundle.json").write_text("{}\n", encoding="utf-8")
    subprocess.run(("git", "add", "splice/bundle.json"), **run)  # type: ignore[call-overload]
    clean = subprocess.run(
        ("python3", str(ROOT / "scripts" / "check_staged_paths.py")),
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert clean.returncode == 0, clean.stderr
    subprocess.run(("git", "add", "-f", ".splice-local"), **run)  # type: ignore[call-overload]
    forced = subprocess.run(
        ("python3", str(ROOT / "scripts" / "check_staged_paths.py")),
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert forced.returncode == 1
    assert ".splice-local/drafts/bundle.draft.yaml" in forced.stderr
