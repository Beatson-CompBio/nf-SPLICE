"""Local Git review and commits of the integration copy, and opt-in pushing.

Git records the finished, distributable files: ``splice/`` and the
``.gitignore`` rule that keeps ``.splice-local/`` private. Incomplete drafts
are tracked by session checkpoints instead, never by Git.

A commit is made only after the published bundle validates, contains only
the paths nf-splice owns (``splice/``, ``.gitignore``) plus any extra paths
the person names, and uses the person's own Git identity. Pushing is a
separate, explicit action that is checked with a dry run first; nf-splice
never pushes, creates remote branches or opens pull requests on its own.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nf_splice.layout import PRIVATE_DIR, PUBLISHED_DIR, is_git_work_tree
from nf_splice.services.lifecycle import validate_bundle
from nf_splice.services.source import SourceError, redact_url

OWNED_PATHS = (PUBLISHED_DIR, ".gitignore")


class GitOperationError(RuntimeError):
    """A Git action was refused or failed; the message says why."""


def _git(
    root: Path, *arguments: str, check: bool = True
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
        env=dict(os.environ) | {"GIT_TERMINAL_PROMPT": "0"},
    )
    if check and result.returncode != 0:
        raise GitOperationError(
            redact_url(result.stderr.strip() or result.stdout.strip())
        )
    return result


@dataclass(slots=True)
class GitStatus:
    """What changed, split into what nf-splice owns and everything else."""

    repository: bool
    branch: str | None = None
    head: str | None = None
    owned: list[str] = field(default_factory=list)
    other: list[str] = field(default_factory=list)
    private_tracked: list[str] = field(default_factory=list)
    remotes: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "repository": self.repository,
            "branch": self.branch,
            "head": self.head,
            "owned_changes": list(self.owned),
            "other_changes": list(self.other),
            "private_tracked": list(self.private_tracked),
            "remotes": list(self.remotes),
        }


def status(repository_root: str | Path) -> GitStatus:
    """Read-only Git status of the integration copy."""
    root = Path(repository_root).resolve()
    if not is_git_work_tree(root):
        return GitStatus(repository=False)
    branch = _git(root, "branch", "--show-current").stdout.strip() or None
    head = _git(
        root, "rev-parse", "--verify", "--quiet", "HEAD", check=False
    ).stdout.strip()
    lines = _git(root, "status", "--porcelain", "--untracked-files=all").stdout
    owned: list[str] = []
    other: list[str] = []
    for line in lines.splitlines():
        path = line[3:].split(" -> ")[-1]
        if path.startswith(PRIVATE_DIR + "/"):
            continue
        (owned if path.split("/", 1)[0] in OWNED_PATHS else other).append(path)
    tracked = _git(root, "ls-files", "--", PRIVATE_DIR).stdout.split()
    remotes = [
        f"{name} {redact_url(url)}"
        for name, url in (
            line.split()[:2]
            for line in _git(root, "remote", "-v").stdout.splitlines()
            if line.endswith("(push)")
        )
    ]
    return GitStatus(True, branch, head or None, owned, other, tracked, remotes)


def diff(repository_root: str | Path) -> str:
    """Diff of the nf-splice-owned paths against ``HEAD`` (new files included)."""
    root = Path(repository_root).resolve()
    if not is_git_work_tree(root):
        raise GitOperationError("this working copy is not a Git repository")
    _git(root, "add", "--intent-to-add", "--", *OWNED_PATHS, check=False)
    return _git(root, "diff", "--", *OWNED_PATHS).stdout


def commit(
    repository_root: str | Path,
    message: str,
    *,
    extra_paths: list[str] | None = None,
    trailer: str | None = None,
) -> dict[str, Any]:
    """Commit the validated bundle; refuses anything private or unvalidated."""
    root = Path(repository_root).resolve()
    if not is_git_work_tree(root):
        raise GitOperationError(
            "this working copy is not a Git repository; create one with "
            "`nf-splice source prepare`"
        )
    report = validate_bundle(root)
    if not report.valid:
        raise GitOperationError(
            "the published bundle does not validate; fix it before committing: "
            + "; ".join(item.message for item in report.issues[:3])
        )
    paths = list(OWNED_PATHS) + list(extra_paths or [])
    for path in paths:
        if path == PRIVATE_DIR or path.startswith(PRIVATE_DIR + "/"):
            raise GitOperationError(".splice-local/ is private and is never committed")
    name = _git(root, "config", "user.name", check=False).stdout.strip()
    email = _git(root, "config", "user.email", check=False).stdout.strip()
    if not name or not email:
        raise GitOperationError(
            "Git has no identity for the commit; configure user.name and user.email"
        )
    existing = [path for path in paths if (root / path).exists()]
    _git(root, "add", "--", *existing)
    staged = _git(root, "diff", "--cached", "--name-only").stdout.split()
    private = [path for path in staged if path.startswith(PRIVATE_DIR + "/")]
    if private:
        _git(root, "reset", "--quiet", "--", *private)
        raise GitOperationError(".splice-local/ files were staged; they were unstaged")
    if not staged:
        return {"committed": False, "reason": "nothing to commit"}
    unexpected = [
        path
        for path in staged
        if path.split("/", 1)[0] not in OWNED_PATHS and path not in (extra_paths or [])
    ]
    if unexpected:
        raise GitOperationError(
            "other changes are already staged (" + ", ".join(unexpected[:5]) + "); "
            "commit or unstage them first"
        )
    text = message.strip() + ("\n\n" + trailer if trailer else "")
    _git(root, "commit", "--quiet", "-m", text)
    head = _git(root, "rev-parse", "HEAD").stdout.strip()
    return {"committed": True, "commit": head, "paths": staged, "author": name}


def push(
    repository_root: str | Path, remote: str, branch: str | None = None
) -> dict[str, Any]:
    """Push the current branch after a dry run proves it is allowed."""
    root = Path(repository_root).resolve()
    current = status(root)
    if not current.repository:
        raise GitOperationError("this working copy is not a Git repository")
    target = branch or current.branch
    if not target:
        raise GitOperationError("no branch to push (detached HEAD); name one")
    names = {item.split()[0] for item in current.remotes}
    if remote not in names:
        raise GitOperationError(
            f"remote {remote!r} is not configured; add it with git remote add"
        )
    dry = _git(
        root, "push", "--dry-run", remote, f"HEAD:refs/heads/{target}", check=False
    )
    if dry.returncode != 0:
        raise GitOperationError(
            "a dry-run push failed, so you may not have permission to push here: "
            + redact_url(dry.stderr.strip())
        )
    _git(root, "push", remote, f"HEAD:refs/heads/{target}")
    return {"pushed": True, "remote": remote, "branch": target}


def assert_source_untouched(record: dict[str, Any]) -> list[str]:
    """Differences from the recorded source state (for reports and tests)."""
    source = Path(str(record.get("source", "")))
    if record.get("source_kind") != "git_local" or not source.is_dir():
        return []
    try:
        head = _git(source, "rev-parse", "HEAD").stdout.strip()
    except (GitOperationError, SourceError):
        return ["the source repository cannot be read"]
    problems = []
    if record.get("source_head") and head != record["source_head"]:
        problems.append("the source repository's HEAD moved")
    return problems
