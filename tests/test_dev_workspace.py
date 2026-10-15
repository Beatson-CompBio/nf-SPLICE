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
    for broad in ("*.yaml", "*.json", "tests/", "docs/", "splice/", "src/"):
        assert broad not in lines


@pytest.mark.parametrize(
    "path",
    [
        ".nf-splice-local/agent/notes.md",
        ".nf-splice-local/sessions/abc.json",
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
        "tests/fixtures/legacy-0.1.0/repository/splice/bundle.json",
        "docs/ARCHITECTURE_DECISIONS.md",
        "splice/drafts/outputs.draft.yaml",
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
