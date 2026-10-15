"""Built sdist/wheel contain the package data and the installed CLI works."""

from __future__ import annotations

import os
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def artefacts(tmp_path_factory: pytest.TempPathFactory) -> Path:
    pytest.importorskip("build")
    pytest.importorskip("setuptools")
    out = tmp_path_factory.mktemp("dist")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--no-isolation",
            "--outdir",
            str(out),
            str(ROOT),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return out


def test_wheel_and_sdist_contain_contract_data_and_wizard_styles(
    artefacts: Path,
) -> None:
    wheel = next(artefacts.glob("nf_splice-0.3.0-*.whl"))
    names = set(zipfile.ZipFile(wheel).namelist())
    assert "nf_splice/contracts/data/registry.json" in names
    for family in ("bundle", "inputs", "outputs", "components", "execution-profiles"):
        assert f"nf_splice/contracts/data/schemas/{family}/0.3.0.schema.json" in names
    assert "nf_splice/interfaces/tui/tui.tcss" in names
    for skill in (
        "nf-splice-agent-operations",
        "nf-splice-authoring",
        "nf-splice-output-discovery",
        "nf-splice-validation",
    ):
        assert f"nf_splice/agents/skills/{skill}/SKILL.md" in names
    assert not any(".nf-splice-local" in name for name in names)
    metadata = next(name for name in names if name.endswith("METADATA"))
    text = zipfile.ZipFile(wheel).read(metadata).decode()
    assert "Provides-Extra: claude" in text and "Requires-Python: <3.15,>=3.10" in text
    sdist = next(artefacts.glob("nf_splice-0.3.0.tar.gz"))
    members = tarfile.open(sdist).getnames()
    assert any(name.endswith("contracts/data/registry.json") for name in members)


def test_installed_wheel_runs_offline(artefacts: Path, tmp_path: Path) -> None:
    wheel = next(artefacts.glob("nf_splice-0.3.0-*.whl"))
    target = tmp_path / "site"
    zipfile.ZipFile(wheel).extractall(target)  # a pure-Python wheel unpacks as-is
    env = {**os.environ, "PYTHONPATH": str(target)}
    location = subprocess.run(
        [sys.executable, "-c", "import nf_splice; print(nf_splice.__file__)"],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert location.stdout.strip().startswith(str(target))
    for arguments, expected in (
        (["--version"], "nf-splice 0.3.0"),
        (["schema", "list"], "workflow-bundle/execution-profiles 0.3.0"),
    ):
        result = subprocess.run(
            [sys.executable, "-m", "nf_splice", *arguments],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        assert expected in result.stdout
