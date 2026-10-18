"""Load the packaged nf-splice skills that guide every provider.

The canonical skills live in the repository's ``skills/`` directory, one
``SKILL.md`` per skill. Identical copies are packaged in
``nf_splice/agents/skills/`` so an installed nf-splice can use them; a test
fails if the two drift apart. The session engine puts the relevant skills
into each provider turn's system prompt, so every provider, not only one
vendor's, follows the same procedures. ``nf-splice skills export`` copies them
to a directory an external coding agent discovers.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from nf_splice.agents.stages import Stage

NAMES = (
    "nf-splice-agent-operations",
    "nf-splice-assay-capabilities",
    "nf-splice-authoring",
    "nf-splice-components-images",
    "nf-splice-execution-config",
    "nf-splice-input-access",
    "nf-splice-output-discovery",
    "nf-splice-provenance",
    "nf-splice-validation",
)
#: The procedure each layer stage follows, besides the two every turn gets.
_STAGE_SKILLS = {
    Stage.IDENTITY: "nf-splice-assay-capabilities",
    Stage.INPUTS: "nf-splice-input-access",
    Stage.OUTPUTS: "nf-splice-output-discovery",
    Stage.COMPONENTS: "nf-splice-components-images",
    Stage.PROFILES: "nf-splice-execution-config",
    Stage.PROVENANCE: "nf-splice-provenance",
}
_FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)


@dataclass(frozen=True, slots=True)
class Skill:
    """One skill: front-matter name and description, and its Markdown body."""

    name: str
    description: str
    body: str
    text: str


def _directory() -> Path:
    return Path(str(resources.files("nf_splice.agents").joinpath("skills")))


def skill_text(name: str) -> str:
    """The full ``SKILL.md`` of a packaged skill."""
    if name not in NAMES:
        raise ValueError(f"unknown skill {name!r}; known: {', '.join(NAMES)}")
    return (_directory() / name / "SKILL.md").read_text(encoding="utf-8")


def load(name: str) -> Skill:
    """Parse a packaged skill."""
    text = skill_text(name)
    match = _FRONT_MATTER.match(text)
    if match is None:
        raise ValueError(f"skill {name} has no front matter")
    fields = dict(
        line.split(":", 1) for line in match.group(1).splitlines() if ":" in line
    )
    declared = fields.get("name", "").strip()
    if declared != name:
        raise ValueError(f"skill {name} declares name {declared!r}")
    return Skill(
        name=name,
        description=fields.get("description", "").strip(),
        body=text[match.end() :],
        text=text,
    )


def skills_for(purpose: str, stage: Stage | None) -> tuple[Skill, ...]:
    """The skills a turn needs: operations and authoring always, plus specifics."""
    names = ["nf-splice-agent-operations", "nf-splice-authoring"]
    if purpose == "help":
        # A read-only answer needs the page's procedure, not every skill.
        names = ["nf-splice-authoring"] + (
            [_STAGE_SKILLS[stage]]
            if stage in _STAGE_SKILLS
            else ["nf-splice-validation"]
        )
    elif stage in _STAGE_SKILLS:
        names.append(_STAGE_SKILLS[stage])
    if stage in {Stage.VALIDATE, Stage.BUILD, Stage.VERIFY}:
        names.append("nf-splice-validation")
    return tuple(load(name) for name in dict.fromkeys(names))


def export(destination: Path) -> list[Path]:
    """Copy every skill to ``destination/<name>/SKILL.md``."""
    written = []
    for name in NAMES:
        target = destination / name / "SKILL.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(_directory() / name / "SKILL.md", target)
        written.append(target)
    return written
