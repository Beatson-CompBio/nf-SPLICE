"""Install the integration skill where external coding agents discover it.

Codex, Claude Code and OpenCode each discover project skills in their own
folder of the working copy. ``nf-splice skills install`` copies the one
canonical ``nf-splice-integration`` skill into those folders, so the agent
the person launches there can integrate the pipeline with the ordinary
nf-splice CLI. The copies are local authoring aids, never part of the
bundle: they are excluded through the repository's own ``info/exclude``
(never ``.gitignore``), and nf-splice records what it wrote in the private
workspace so a later install updates its own copy but keeps a file someone
changed.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from nf_splice.layout import PRIVATE_DIR, is_git_work_tree, prepare_private_workspace
from nf_splice.services.source import refuse_self_checkout, require_authorised

SKILL = "nf-splice-integration"
#: Each agent's project-level skill discovery folder.
AGENT_FOLDERS = {
    "codex": ".agents/skills",
    "claude": ".claude/skills",
    "opencode": ".opencode/skills",
}
AGENTS = tuple(AGENT_FOLDERS)
#: The folders nf-splice manages; never published, committed or archived.
MANAGED_FOLDERS = tuple(f"{folder}/{SKILL}" for folder in AGENT_FOLDERS.values())
RECORD = f"{PRIVATE_DIR}/agent-skills.json"
_EXCLUDE_HEADER = "# nf-splice external agent skills (local only, never commit)"


class SkillInstallError(RuntimeError):
    """The skill cannot be installed safely; the message says why."""


@dataclass(slots=True)
class InstalledSkill:
    agent: str
    path: str
    action: str  # installed, updated, unchanged or kept (changed by someone)


@dataclass(slots=True)
class SkillInstallation:
    repository: str
    skills: list[InstalledSkill] = field(default_factory=list)
    exclude_file: str | None = None
    excluded: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _refuse_links(root: Path, relative: Path) -> None:
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise SkillInstallError(
                f"{current.relative_to(root)} is a symbolic link; refusing to "
                "write through it"
            )


def _git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *arguments],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    ).stdout.strip()


def _exclude(root: Path, folders: list[Path]) -> tuple[str | None, list[str]]:
    """Add each installed skill folder to Git's ``info/exclude`` once."""
    if not is_git_work_tree(root):
        return None, []
    top = Path(_git(root, "rev-parse", "--show-toplevel")).resolve()
    # --git-path resolves info/exclude to the common directory in a worktree.
    exclude = (root / _git(root, "rev-parse", "--git-path", "info/exclude")).resolve()
    if exclude.is_symlink():
        raise SkillInstallError(f"{exclude} is a symbolic link; refusing to edit it")
    text = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
    present = {line.strip() for line in text.splitlines()}
    wanted = [
        "/" + (root / folder).relative_to(top).as_posix() + "/" for folder in folders
    ]
    missing = [rule for rule in wanted if rule not in present]
    if missing:
        block = ([] if _EXCLUDE_HEADER in present else [_EXCLUDE_HEADER]) + missing
        prefix = "" if not text or text.endswith("\n") else "\n"
        exclude.parent.mkdir(parents=True, exist_ok=True)
        exclude.write_text(text + prefix + "\n".join(block) + "\n", encoding="utf-8")
    return str(exclude), missing


def install(repository: Path, agents: list[str]) -> SkillInstallation:
    """Install the integration skill for ``agents`` in an integration copy."""
    from nf_splice.agents.skills import skill_text

    root = Path(repository).resolve()
    if not root.is_dir():
        raise SkillInstallError(f"{root} is not a directory")
    unknown = sorted(set(agents) - set(AGENTS))
    if unknown:
        raise SkillInstallError(
            f"unknown agent {', '.join(unknown)}; choose {', '.join(AGENTS)} or all"
        )
    refuse_self_checkout(root)
    require_authorised(root)
    prepare_private_workspace(root)
    record_path = root / RECORD
    written: dict[str, str] = (
        json.loads(record_path.read_text(encoding="utf-8"))
        if record_path.is_file()
        else {}
    )
    content = skill_text(SKILL).encode("utf-8")
    result = SkillInstallation(repository=str(root))
    folders = []
    for agent in dict.fromkeys(agents):
        folder = Path(AGENT_FOLDERS[agent]) / SKILL
        relative = folder / "SKILL.md"
        _refuse_links(root, relative)
        target = root / relative
        if not target.exists():
            action = "installed"
        else:
            current = _digest(target.read_bytes())
            if current == _digest(content):
                action = "unchanged"
            elif written.get(relative.as_posix()) == current:
                action = "updated"  # nf-splice's own earlier copy
            else:
                action = "kept"
        if action in {"installed", "updated"}:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        if action != "kept":
            written[relative.as_posix()] = _digest(content)
            folders.append(folder)
        result.skills.append(InstalledSkill(agent, relative.as_posix(), action))
    record_path.write_text(
        json.dumps(written, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    result.exclude_file, result.excluded = _exclude(root, folders)
    return result
