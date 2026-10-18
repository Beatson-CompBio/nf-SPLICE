"""The skills are canonical, packaged, accurate and used by the runtime."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from nf_splice.agents import skills
from nf_splice.agents.operations import CONTROL_SCHEMAS, OPERATIONS
from nf_splice.agents.prompts import system_prompt
from nf_splice.agents.stages import Stage

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "skills"
PACKAGED = ROOT / "src" / "nf_splice" / "agents" / "skills"
SECTIONS = (
    "## When to use",
    "## Prerequisites",
    "## Workflow",
    "## Verification gates",
    "## Failure handling",
    "## Evidence reporting",
    "## Safety boundaries",
)
_SOURCE = "\n".join(
    path.read_text(encoding="utf-8")
    for path in (ROOT / "src" / "nf_splice").rglob("*.py")
)


def test_canonical_and_packaged_skills_do_not_drift() -> None:
    canonical = sorted(path.parent.name for path in CANONICAL.glob("*/SKILL.md"))
    assert canonical == sorted(skills.NAMES)
    for name in skills.NAMES:
        assert (CANONICAL / name / "SKILL.md").read_bytes() == (
            PACKAGED / name / "SKILL.md"
        ).read_bytes(), f"{name}: copy skills/{name}/SKILL.md into the package"


@pytest.mark.parametrize("name", skills.NAMES)
def test_every_skill_is_complete(name: str) -> None:
    skill = skills.load(name)
    assert skill.description and len(skill.description) < 400
    for heading in SECTIONS:
        assert heading in skill.body, (name, heading)


@pytest.mark.parametrize("name", skills.NAMES)
def test_skills_name_only_real_tools_and_values(name: str) -> None:
    body = skills.load(name).body
    tools = set(OPERATIONS) | set(CONTROL_SCHEMAS)
    for token in set(re.findall(r"`([a-z][a-z0-9]*(?:_[a-z0-9]+)+)`", body)):
        assert token in tools or f'"{token}"' in _SOURCE, (name, token)


def test_runtime_prompts_load_the_relevant_skills() -> None:
    planning = system_prompt("plan", Stage.OUTPUTS)
    assert 'skill name="nf-splice-output-discovery"' in planning
    assert 'skill name="nf-splice-agent-operations"' in planning
    assert "nf-splice-validation" not in planning
    building = system_prompt("execute", Stage.BUILD)
    assert 'skill name="nf-splice-validation"' in building
    # Ask loads the page's procedure only, under read-only rules.
    help_prompt = system_prompt("help", Stage.OUTPUTS)
    assert 'skill name="nf-splice-output-discovery"' in help_prompt
    assert 'skill name="nf-splice-assay-capabilities"' not in help_prompt
    assert "read-only assistant" in help_prompt
    assert "complete_review" not in help_prompt.split("Skills (")[0]
    review = system_prompt("help", None)
    assert 'skill name="nf-splice-validation"' in review


def test_root_agents_file_points_at_real_paths() -> None:
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    for path in re.findall(r"`((?:src|skills|docs|tests|scripts)/[^`*<]+)`", text):
        assert (ROOT / path).exists(), path
    for name in skills.NAMES:
        assert f"skills/{name}/SKILL.md" in text
