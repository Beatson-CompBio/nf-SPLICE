"""The filesystem contract of an integration working copy.

```text
<pipeline>/
  .gitignore            includes /.splice-local/
  splice/               published, Git-trackable bundle files only
  .splice-local/        private authoring and runtime state (never published)
    drafts/             one editable draft per layer (+ configs/)
    reviews/            review sidecars
    sessions/<id>/      session.json, events.jsonl, checkpoints/
    cache/  staging/
```

Private state is created only after ``/.splice-local/`` is in the copy's
``.gitignore`` and Git is known not to track it. A directory whose name
differs from ``splice`` or ``.splice-local`` only by case is refused, because
it collides on case-insensitive filesystems such as macOS.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

PUBLISHED_DIR = "splice"
PRIVATE_DIR = ".splice-local"
DRAFTS_DIR = f"{PRIVATE_DIR}/drafts"
REVIEWS_DIR = f"{PRIVATE_DIR}/reviews"
SESSIONS_DIR = f"{PRIVATE_DIR}/sessions"
CACHE_DIR = f"{PRIVATE_DIR}/cache"
STAGING_DIR = f"{PRIVATE_DIR}/staging"
IGNORE_RULE = "/.splice-local/"
#: Directories of earlier development builds, migrated by ``nf-splice migrate``.
LEGACY_DRAFTS_DIR = "splice/drafts"
LEGACY_AGENT_DIR = ".nf-splice-local/agent"

_PREPARED: set[str] = set()


class WorkspaceLayoutError(ValueError):
    """The working copy's layout is unsafe for writing private state."""


def case_collisions(root: Path) -> list[str]:
    """Entries that differ from ``splice`` or ``.splice-local`` only by case."""
    if not root.is_dir():
        return []
    wanted = {PUBLISHED_DIR, PRIVATE_DIR}
    return sorted(
        entry.name
        for entry in root.iterdir()
        if entry.name.lower() in wanted and entry.name not in wanted
    )


def legacy_paths(root: Path) -> list[str]:
    """Earlier layouts present in this working copy."""
    return [
        relative
        for relative in (LEGACY_DRAFTS_DIR, LEGACY_AGENT_DIR)
        if (root / relative).is_dir() and not (root / relative).is_symlink()
    ]


def git_available() -> bool:
    return shutil.which("git") is not None


def is_git_work_tree(root: Path) -> bool:
    if not git_available():
        return False
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def tracked_private_paths(root: Path) -> list[str]:
    """Files under ``.splice-local/`` that Git tracks (should be none)."""
    if not is_git_work_tree(root):
        return []
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--", PRIVATE_DIR],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def ensure_ignore_rule(root: Path) -> bool:
    """Add ``/.splice-local/`` to ``.gitignore`` once; return whether it changed."""
    path = root / ".gitignore"
    if path.is_symlink():
        raise WorkspaceLayoutError(".gitignore is a symbolic link; refusing to edit it")
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = [line.strip() for line in text.splitlines()]
    if any(
        line in {IGNORE_RULE, "/.splice-local", ".splice-local/", ".splice-local"}
        for line in lines
    ):
        return False
    prefix = "" if not text or text.endswith("\n") else "\n"
    path.write_text(
        text
        + prefix
        + "\n# nf-splice private authoring state (never commit)\n"
        + IGNORE_RULE
        + "\n",
        encoding="utf-8",
    )
    return True


def prepare_private_workspace(root: Path) -> Path:
    """Make ``.splice-local/`` safe to write: ignored, untracked, no collisions."""
    root = root.resolve()
    key = str(root)
    private = root / PRIVATE_DIR
    if key in _PREPARED and private.is_dir():
        return private
    collisions = case_collisions(root)
    if collisions:
        raise WorkspaceLayoutError(
            f"{', '.join(collisions)} differs from splice/ or .splice-local/ only by "
            "case and collides on case-insensitive filesystems; rename it before "
            "using nf-splice"
        )
    if private.is_symlink():
        raise WorkspaceLayoutError(
            ".splice-local is a symbolic link; refusing to use it"
        )
    tracked = tracked_private_paths(root)
    if tracked:
        raise WorkspaceLayoutError(
            f"Git tracks {len(tracked)} file(s) under .splice-local/ (for example "
            f"{tracked[0]}); private drafts and sessions must not be committed. Run "
            "`nf-splice workspace untrack --yes` to stop tracking them (files are "
            "kept, history is not rewritten)"
        )
    ensure_ignore_rule(root)
    private.mkdir(mode=0o700, exist_ok=True)
    _PREPARED.add(key)
    return private


def untrack_private_workspace(root: Path) -> list[str]:
    """Remove ``.splice-local/`` from Git's index only (a person's decision)."""
    tracked = tracked_private_paths(root)
    if tracked:
        subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "rm",
                "-r",
                "--cached",
                "--quiet",
                "--",
                PRIVATE_DIR,
            ],
            check=True,
            capture_output=True,
            timeout=60,
        )
    ensure_ignore_rule(root)
    _PREPARED.discard(str(root.resolve()))
    return tracked
