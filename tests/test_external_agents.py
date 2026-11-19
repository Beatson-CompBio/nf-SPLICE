"""The integration skill for external coding agents and its installer."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from layer_fixtures import (
    ADA,
    LOCAL_PROFILE,
    REPORT_OUTPUT,
    edit_draft_file,
    ready_repository,
    write_pipeline,
)
from nf_splice.agents import skills
from nf_splice.agents.operations import CONTROL_SCHEMAS, OPERATIONS
from nf_splice.cli import app
from nf_splice.services import agent_skills
from nf_splice.services.export import ExportScope, export_archive
from nf_splice.services.lifecycle import promote
from nf_splice.services.source import NotIsolatedError, prepare_integration_copy

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
runner = CliRunner()
ROOT = Path(__file__).resolve().parents[1]
INSTALLED = {
    "codex": ".agents/skills/nf-splice-integration/SKILL.md",
    "claude": ".claude/skills/nf-splice-integration/SKILL.md",
    "opencode": ".opencode/skills/nf-splice-integration/SKILL.md",
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


def _copy(tmp_path: Path, *, git: bool = True) -> Path:
    source = tmp_path / "pipeline"
    source.mkdir()
    write_pipeline(source)
    copy = prepare_integration_copy(
        str(source), destination=tmp_path / "copy", use_git=git
    )
    return Path(copy.path)


def _git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *arguments],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


# ------------------------------------------------------------------ the skill


def test_integration_skill_is_packaged_and_frontmatter_is_portable() -> None:
    skill = skills.load("nf-splice-integration")
    # OpenCode's rules: lower-case hyphenated name matching the folder,
    # description of at most 1024 characters.
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", skill.name)
    assert 0 < len(skill.description) <= 1024
    assert "Codex" in skill.description and "OpenCode" in skill.description


def test_integration_skill_drives_the_cli_not_the_embedded_engine() -> None:
    body = skills.load("nf-splice-integration").body
    # No internal typed operation or control tool is named.
    for name in set(OPERATIONS) | set(CONTROL_SCHEMAS):
        assert f"`{name}`" not in body, name
    # `nf-splice session start` appears only as something never to run.
    text = " ".join(body.split())
    assert text.count("session start") == 1
    assert "Never start `nf-splice session start`" in text
    assert "splice/" in body and "by hand" in body
    for command in (
        "nf-splice init",
        "nf-splice draft validate",
        "nf-splice status",
        "nf-splice plan",
        "nf-splice build all",
        "nf-splice validate",
    ):
        assert command in body, command


def test_every_command_the_skill_names_exists() -> None:
    body = skills.load("nf-splice-integration").body
    words = re.compile(r"[a-z][a-z-]*")
    commands: set[tuple[str, ...]] = set()
    for match in re.findall(r"`nf-splice ([^`]+)`", body):
        path: list[str] = []
        for token in match.split():
            if not words.fullmatch(token):
                break
            path.append(token)
        commands.add(tuple(path))
    for command in sorted(commands):
        result = runner.invoke(app, [*command, "--help"])
        assert result.exit_code == 0, (command, result.output)


# -------------------------------------------------------------- installation


def test_install_for_every_agent_in_its_discovery_folder(tmp_path: Path) -> None:
    root = _copy(tmp_path)
    result = runner.invoke(
        app, ["skills", "install", "--agent", "all", "--repository", str(root)]
    )
    assert result.exit_code == 0, result.output
    canonical = (ROOT / "skills" / "nf-splice-integration" / "SKILL.md").read_bytes()
    for agent, relative in INSTALLED.items():
        assert (root / relative).read_bytes() == canonical, agent
        assert relative in result.output
    assert "Use nf-SPLICE to build the SPLICE integration" in result.output
    # Native discovery suffices: no root instruction files.
    assert not (root / "AGENTS.md").exists() and not (root / "CLAUDE.md").exists()


@pytest.mark.parametrize("agent", agent_skills.AGENTS)
def test_install_one_agent_only(tmp_path: Path, agent: str) -> None:
    root = _copy(tmp_path)
    result = runner.invoke(
        app, ["skills", "install", "--agent", agent, "-r", str(root), "--json"]
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert [item["path"] for item in data["skills"]] == [INSTALLED[agent]]
    assert [path for path in INSTALLED.values() if (root / path).exists()] == [
        INSTALLED[agent]
    ]


def test_unknown_agent_is_refused(tmp_path: Path) -> None:
    root = _copy(tmp_path)
    result = runner.invoke(
        app, ["skills", "install", "--agent", "cursor", "-r", str(root)]
    )
    assert result.exit_code == 2 and "unknown agent" in result.output


def test_repeated_install_never_duplicates(tmp_path: Path) -> None:
    root = _copy(tmp_path)
    agent_skills.install(root, list(agent_skills.AGENTS))
    exclude_before = (root / ".git" / "info" / "exclude").read_text("utf-8")
    again = agent_skills.install(root, list(agent_skills.AGENTS))
    assert {item.action for item in again.skills} == {"unchanged"}
    assert again.excluded == []
    assert (root / ".git" / "info" / "exclude").read_text("utf-8") == exclude_before
    for folder in agent_skills.AGENT_FOLDERS.values():
        assert [path.name for path in (root / folder).iterdir()] == [
            "nf-splice-integration"
        ]
    for rule in agent_skills.MANAGED_FOLDERS:
        assert exclude_before.count(f"/{rule}/") == 1


def test_pre_existing_files_are_respected(tmp_path: Path) -> None:
    root = _copy(tmp_path)
    own = root / ".claude" / "skills" / "my-skill" / "SKILL.md"
    own.parent.mkdir(parents=True)
    own.write_text("---\nname: my-skill\n---\nmine\n", encoding="utf-8")
    settings = root / ".claude" / "settings.json"
    settings.write_text("{}\n", encoding="utf-8")
    (root / "AGENTS.md").write_text("# House rules\n", encoding="utf-8")
    edited = root / INSTALLED["codex"]
    edited.parent.mkdir(parents=True)
    edited.write_text("my own version\n", encoding="utf-8")

    result = agent_skills.install(root, list(agent_skills.AGENTS))

    actions = {item.agent: item.action for item in result.skills}
    assert actions == {"codex": "kept", "claude": "installed", "opencode": "installed"}
    assert edited.read_text("utf-8") == "my own version\n"
    assert own.read_text("utf-8").endswith("mine\n")
    assert settings.read_text("utf-8") == "{}\n"
    assert (root / "AGENTS.md").read_text("utf-8") == "# House rules\n"
    # Only the copies nf-splice manages are excluded from Git.
    exclude = (root / ".git" / "info" / "exclude").read_text("utf-8")
    assert "/.claude/skills/nf-splice-integration/" in exclude
    assert "/.agents/skills/nf-splice-integration/" not in exclude
    assert "my-skill" not in exclude and "settings" not in exclude


def test_an_older_nf_splice_copy_is_updated_but_an_edit_is_kept(
    tmp_path: Path,
) -> None:
    root = _copy(tmp_path)
    agent_skills.install(root, ["claude"])
    target = root / INSTALLED["claude"]
    # Simulate the copy an earlier nf-splice release installed.
    older = b"---\nname: nf-splice-integration\ndescription: old\n---\nold\n"
    target.write_bytes(older)
    written = root / agent_skills.RECORD
    data = json.loads(written.read_text("utf-8"))
    data[INSTALLED["claude"]] = agent_skills._digest(older)
    written.write_text(json.dumps(data), encoding="utf-8")
    assert agent_skills.install(root, ["claude"]).skills[0].action == "updated"
    target.write_text("edited by a person\n", encoding="utf-8")
    assert agent_skills.install(root, ["claude"]).skills[0].action == "kept"
    assert target.read_text("utf-8") == "edited by a person\n"


def test_symbolic_links_are_never_written_through(tmp_path: Path) -> None:
    root = _copy(tmp_path)
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (root / ".claude").symlink_to(outside)
    with pytest.raises(agent_skills.SkillInstallError, match="symbolic link"):
        agent_skills.install(root, ["claude"])
    assert not any(outside.iterdir())


def test_the_original_pipeline_is_never_modified(tmp_path: Path) -> None:
    original = tmp_path / "pipeline"
    original.mkdir()
    write_pipeline(original)
    _git(original, "init", "--quiet")
    before = sorted(str(path) for path in original.rglob("*"))
    with pytest.raises(NotIsolatedError):
        agent_skills.install(original, list(agent_skills.AGENTS))
    result = runner.invoke(
        app, ["skills", "install", "--agent", "all", "-r", str(original)]
    )
    assert result.exit_code == 2
    assert "nf-splice source prepare" in result.output
    assert sorted(str(path) for path in original.rglob("*")) == before


# -------------------------------------------------------------- Git and archives


def test_installed_skills_stay_out_of_git(tmp_path: Path) -> None:
    root = _copy(tmp_path)
    agent_skills.install(root, list(agent_skills.AGENTS))
    assert _git(root, "status", "--porcelain", "--untracked-files=all") == ""
    # Even `git add -A` leaves them out; .gitignore is not touched.
    _git(root, "add", "-A")
    assert _git(root, "diff", "--cached", "--name-only") == ""
    assert "nf-splice-integration" not in (root / ".gitignore").read_text("utf-8")


def test_exclusions_reach_the_common_git_directory_of_a_worktree(
    tmp_path: Path,
) -> None:
    root = _copy(tmp_path)
    worktree = tmp_path / "worktree"
    _git(root, "worktree", "add", "--quiet", "-b", "second", str(worktree))
    shutil.copytree(root / ".splice-local", worktree / ".splice-local")
    result = agent_skills.install(worktree, ["codex"])
    common = Path(_git(worktree, "rev-parse", "--git-common-dir").strip())
    if not common.is_absolute():
        common = worktree / common
    assert Path(str(result.exclude_file)) == (common / "info" / "exclude").resolve()
    assert _git(worktree, "status", "--porcelain", "--untracked-files=all") == ""


def test_plain_copy_archives_leave_the_skills_out(tmp_path: Path) -> None:
    source = tmp_path / "pipeline"
    source.mkdir()
    (source / "README.md").write_text("rnaquant\n", encoding="utf-8")
    root = Path(
        prepare_integration_copy(str(source), tmp_path / "copy", use_git=False).path
    )
    ready_repository(root)
    promote(root, None, ADA)
    result = agent_skills.install(root, list(agent_skills.AGENTS))
    assert result.exclude_file is None
    archive = export_archive(root, ExportScope.PIPELINE, tmp_path / "pipeline.zip")
    with zipfile.ZipFile(archive.path) as handle:
        names = handle.namelist()
    assert "main.nf" in names and "splice/bundle.json" in names
    assert not [name for name in names if "nf-splice-integration" in name]


# --------------------------------------------------------------- smoke test


def test_external_agent_workflow_from_copy_to_published_bundle(
    tmp_path: Path,
) -> None:
    """The commands an external coding agent runs, with direct file edits."""
    source = tmp_path / "rnaquant"
    source.mkdir()
    write_pipeline(source)
    copy = tmp_path / "rnaquant-splice-integration"

    def cli(*arguments: str) -> Any:
        result = runner.invoke(app, list(arguments))
        assert result.exit_code == 0, (arguments, result.output)
        return result

    cli("source", "prepare", str(source), "--into", str(copy), "--no-open")
    cli("skills", "install", "--agent", "all", "--repository", str(copy))
    cli(
        "init",
        "-r", str(copy),
        "--name", "rnaquant",
        "--pipeline-version", "1.2.0",
        "--repository-url", "https://github.com/org/rnaquant",
        "--description", "Quantifies RNA-seq reads.",
        "--licence", "MIT",
        "--contract-version", "1.0.0",
    )  # fmt: skip
    # The seeded drafts do not validate yet; the agent reads the issues.
    seeded = runner.invoke(app, ["draft", "validate", "-r", str(copy), "--json"])
    assert seeded.exit_code == 2
    assert "missing_assay_classification" in seeded.output

    # Author the drafts as a coding agent would: edit the YAML files.
    def identity(data: dict[str, Any]) -> None:
        data["pipeline"]["id"] = "rnaquant"
        data["pipeline"]["released_at"] = "2026-10-15T10:00:00Z"
        data["pipeline"]["assay_capabilities"] = [
            {
                "registered_code": "polya_rnaseq",
                "evidence": "asserted",
                "rationale": "The developers process poly(A)-selected libraries.",
            }
        ]

    def inputs(data: dict[str, Any]) -> None:
        group = data["$defs"]["analysis"]["properties"]
        group["threshold"]["x-splice-access"] = {"editable_by": ["agent", "user"]}
        group["threshold"]["x-splice-ui"] = {"visibility": "standard"}
        group["outdir"]["x-splice-access"] = {"editable_by": ["platform"]}

    def outputs(data: dict[str, Any]) -> None:
        data["outputs"] = [dict(REPORT_OUTPUT)]

    def components(data: dict[str, Any]) -> None:
        data["require_downloadable_images"] = False

    def profiles(data: dict[str, Any]) -> None:
        data["profiles"] = [dict(LOCAL_PROFILE)]
        data["default_profile"] = "local"

    def provenance(data: dict[str, Any]) -> None:
        for node in data["crate"]["@graph"]:
            if node["@id"] == "./":
                node["datePublished"] = "2026-10-15"

    for layer, mutate in (
        ("bundle", identity),
        ("inputs", inputs),
        ("outputs", outputs),
        ("components", components),
        ("execution-profiles", profiles),
        ("provenance", provenance),
    ):
        edit_draft_file(copy, layer, mutate)
    (copy / ".splice-local/drafts/configs/default.draft.config").unlink()

    cli("draft", "validate", "-r", str(copy))
    cli("plan", "-r", str(copy))
    cli("build", "all", "-r", str(copy), "--non-interactive")
    assert "ready for ingestion." in cli("validate", "-r", str(copy)).output
    cli("status", "-r", str(copy), "--json")

    bundle = json.loads((copy / "splice" / "bundle.json").read_text("utf-8"))
    assert bundle
    assert (copy / "splice" / "outputs.yaml").is_file()
    published = [path.as_posix() for path in (copy / "splice").rglob("*")]
    assert not [path for path in published if "nf-splice-integration" in path]
    # Only the bundle (and the private-workspace rule) is new to Git.
    changed = {
        line[3:].split("/", 1)[0]
        for line in _git(copy, "status", "--porcelain").splitlines()
    }
    assert changed <= {"splice", ".gitignore"}, changed
    # The original pipeline was never touched.
    assert not (source / ".splice-local").exists()
    assert not (source / ".claude").exists()
