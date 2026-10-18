"""Isolate the pipeline being integrated in its own local working copy.

nf-splice changes only an *integration copy*, never the original pipeline:

- a local Git repository is cloned and checked out on a dedicated branch
  ``nf-splice/integration-<name>``; uncommitted changes are left behind
  unless the person asks to import them;
- a plain directory is copied (without following symbolic links or copying
  temporary data) and initialised as a new local Git repository;
- a Git URL (GitHub, GitLab or any host) is cloned; no remote account is
  ever needed for the rest of the work.

Working on the original in place is possible only with explicit consent.
Pushing, creating remote branches or pull requests are separate actions.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from nf_splice import __version__
from nf_splice.layout import PRIVATE_DIR, git_available, prepare_private_workspace

INTEGRATION_RECORD = f"{PRIVATE_DIR}/integration.json"
_COPY_EXCLUDES = {
    ".git",
    PRIVATE_DIR,
    ".nf-splice-local",
    "work",
    ".nextflow",
    ".nf-test",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    ".venv",
}
_COPY_EXCLUDE_PATTERNS = (re.compile(r"^\.nextflow\.log(\.\d+)?$"),)
_URL = re.compile(r"^(https?://|ssh://|git@|git://|file://)")
_CREDENTIALS_IN_URL = re.compile(r"(https?://)[^/@\s]+@")


class SourceError(RuntimeError):
    """The source cannot be isolated safely; the message says what to do."""


@dataclass(slots=True)
class IntegrationCopy:
    """Where the work happens and where it came from."""

    path: str
    source_kind: str
    source: str
    source_revision: str | None
    source_remote: str | None
    source_head: str | None
    branch: str | None
    in_place: bool
    uncommitted_in_source: list[str] = field(default_factory=list)
    imported_uncommitted: bool = False
    skipped: list[str] = field(default_factory=list)
    created_at: str = ""
    nf_splice_version: str = __version__

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


def redact_url(url: str) -> str:
    """Remove any user or token embedded in a URL."""
    return _CREDENTIALS_IN_URL.sub(r"\1", url)


def _git(arguments: list[str], cwd: Path | None = None, timeout: float = 600) -> str:
    if not git_available():
        raise SourceError(
            "Git is not installed. Install Git, or work on a plain folder copy with "
            "--no-git"
        )
    result = subprocess.run(
        ["git", *arguments],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
        env=dict(os.environ) | {"GIT_TERMINAL_PROMPT": "0"},
    )
    if result.returncode != 0:
        raise SourceError(_explain_git_error(arguments, result.stderr))
    return result.stdout


def _explain_git_error(arguments: list[str], stderr: str) -> str:
    message = redact_url(stderr.strip().splitlines()[-1] if stderr.strip() else "")
    lowered = stderr.lower()
    if "authentication failed" in lowered or "could not read username" in lowered:
        return (
            "Git could not authenticate to the repository. Sign in with your Git "
            "host's usual method (for example a credential helper or SSH key) and "
            f"try again. Git said: {message}"
        )
    if "repository not found" in lowered or "not found" in lowered:
        return (
            "The repository was not found, or your account cannot read it. Check "
            f"the address and your access. Git said: {message}"
        )
    if "could not resolve host" in lowered or "unable to access" in lowered:
        return (
            f"The Git host could not be reached. Check the network. Git said: {message}"
        )
    if "did not match any" in lowered or "unknown revision" in lowered:
        return f"That branch, tag or commit does not exist. Git said: {message}"
    return f"git {arguments[0]} failed: {message}"


def _is_repository(path: Path) -> bool:
    """Whether ``path`` is itself the root of a Git working tree.

    ``--is-inside-work-tree`` is also true for a folder merely contained by
    a checkout (a workspace in an evaluation folder, a pipeline in a
    monorepo); such a folder must not inherit an outer repository's
    revision, branch or uncommitted list, so only the repository's own root
    counts.
    """
    try:
        return _top_level(path).resolve() == path.resolve()
    except SourceError:
        return False


def _top_level(path: Path) -> Path:
    return Path(_git(["-C", str(path), "rev-parse", "--show-toplevel"]).strip())


def _uncommitted(path: Path) -> list[str]:
    output = _git(["-C", str(path), "status", "--porcelain", "--untracked-files=all"])
    return [line[3:] for line in output.splitlines() if line.strip()]


def _safe_name(value: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-.").lower()
    return name or "pipeline"


def _source_checkout() -> Path | None:
    """nf-splice's own source checkout, when running from one."""
    candidate = Path(__file__).resolve().parents[3]
    project = candidate / "pyproject.toml"
    if project.is_file() and 'name = "nf-splice"' in project.read_text("utf-8"):
        return candidate
    return None


def refuse_self_checkout(path: Path) -> None:
    """Never integrate into nf-splice's own source tree (dev workspace aside)."""
    checkout = _source_checkout()
    if checkout is None:
        return
    resolved = path.resolve()
    workspace = checkout / ".nf-splice-local"
    if resolved.is_relative_to(checkout) and not resolved.is_relative_to(workspace):
        raise SourceError(
            f"{resolved} is inside nf-splice's own source checkout; choose a "
            "directory outside it"
        )


def _check_destination(destination: Path, source: Path | None) -> None:
    if destination.exists() and any(destination.iterdir()):
        raise SourceError(
            f"{destination} already exists and is not empty; choose a new "
            "directory (nothing is overwritten)"
        )
    if source is not None:
        resolved = destination.resolve()
        if resolved.is_relative_to(source.resolve()):
            raise SourceError(
                "the integration copy cannot be inside the pipeline it copies"
            )
    refuse_self_checkout(destination)


def default_destination(source: str) -> Path:
    """``<name>-splice-integration`` next to a local source, or here for a URL."""
    if _URL.match(source):
        name = _safe_name(source.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git"))
        return Path.cwd() / f"{name}-splice-integration"
    path = Path(source).expanduser().resolve()
    return path.parent / f"{_safe_name(path.name)}-splice-integration"


def _copy_tree(source: Path, destination: Path) -> list[str]:
    """Copy regular files and folders; skip links, temporary and private data."""
    skipped: list[str] = []
    for current, directories, names in os.walk(source, followlinks=False):
        current_path = Path(current)
        relative = current_path.relative_to(source)
        kept = []
        for name in sorted(directories):
            path = current_path / name
            if name in _COPY_EXCLUDES:
                skipped.append((relative / name).as_posix() + "/")
            elif path.is_symlink():
                skipped.append((relative / name).as_posix() + " (symbolic link)")
            else:
                kept.append(name)
        directories[:] = kept
        (destination / relative).mkdir(parents=True, exist_ok=True)
        for name in sorted(names):
            path = current_path / name
            item = (relative / name).as_posix()
            if any(pattern.match(name) for pattern in _COPY_EXCLUDE_PATTERNS):
                skipped.append(item)
            elif path.is_symlink():
                skipped.append(f"{item} (symbolic link)")
            elif path.is_file():
                shutil.copy2(path, destination / relative / name)
    return skipped


def _require_identity(root: Path) -> None:
    name = subprocess.run(
        ["git", "-C", str(root), "config", "user.name"], capture_output=True, text=True
    ).stdout.strip()
    email = subprocess.run(
        ["git", "-C", str(root), "config", "user.email"],
        capture_output=True,
        text=True,
    ).stdout.strip()
    if not name or not email:
        raise SourceError(
            "Git has no identity to record the import commit. Set one first, for "
            'example: git config --global user.name "Your Name" and git config '
            '--global user.email "you@example.org" (or pass --git-name and '
            "--git-email to set it for this copy only)"
        )


def _record(copy: IntegrationCopy) -> IntegrationCopy:
    root = Path(copy.path)
    prepare_private_workspace(root)
    copy.created_at = (
        datetime.datetime.now(datetime.timezone.utc)
        .replace(microsecond=0)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    path = root / INTEGRATION_RECORD
    path.write_text(json.dumps(copy.to_json(), indent=2) + "\n", encoding="utf-8")
    return copy


def read_record(root: Path) -> dict[str, Any] | None:
    path = root / INTEGRATION_RECORD
    if not path.is_file():
        return None
    loaded: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return loaded


def prepare_integration_copy(
    source: str,
    destination: Path | None = None,
    *,
    ref: str | None = None,
    branch: str | None = None,
    include_uncommitted: bool = False,
    git_name: str | None = None,
    git_email: str | None = None,
    in_place: bool = False,
    use_git: bool = True,
) -> IntegrationCopy:
    """Create (or, with consent, adopt in place) the integration working copy."""
    is_url = bool(_URL.match(source))
    if in_place:
        if is_url:
            raise SourceError("a Git URL cannot be used in place; clone it instead")
        root = Path(source).expanduser().resolve()
        refuse_self_checkout(root)
        repository = _is_repository(root)
        copy = IntegrationCopy(
            path=str(root),
            source_kind="in_place",
            source=str(root),
            source_revision=_git(["-C", str(root), "rev-parse", "HEAD"]).strip()
            if repository
            else None,
            source_remote=None,
            source_head=None,
            branch=None,
            in_place=True,
            uncommitted_in_source=_uncommitted(root) if repository else [],
        )
        return _record(copy)
    target = (destination or default_destination(source)).expanduser().resolve()
    local = None if is_url else Path(source).expanduser().resolve()
    if local is not None and not local.is_dir():
        raise SourceError(f"{source} is not a directory")
    _check_destination(target, local)
    label = _safe_name(
        source.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
        if is_url
        else (local.name if local else "pipeline")
    )
    work_branch = branch or f"nf-splice/integration-{label}"
    if is_url or (local is not None and use_git and _is_repository(local)):
        origin = source if is_url else str(_top_level(local))  # type: ignore[arg-type]
        uncommitted = [] if is_url else _uncommitted(Path(origin))
        source_head = (
            None if is_url else _git(["-C", origin, "rev-parse", "HEAD"]).strip()
        )
        source_remote = None
        if not is_url:
            try:
                source_remote = redact_url(
                    _git(["-C", origin, "remote", "get-url", "origin"]).strip()
                )
            except SourceError:
                source_remote = None
        target.parent.mkdir(parents=True, exist_ok=True)
        _git(["clone", "--quiet", "--no-hardlinks", origin, str(target)])
        if ref:
            _git(["-C", str(target), "checkout", "--quiet", ref])
        revision = _git(["-C", str(target), "rev-parse", "HEAD"]).strip()
        _git(["-C", str(target), "checkout", "--quiet", "-b", work_branch])
        if git_name or git_email:
            if git_name:
                _git(["-C", str(target), "config", "user.name", git_name])
            if git_email:
                _git(["-C", str(target), "config", "user.email", git_email])
        imported = False
        if uncommitted and include_uncommitted and local is not None:
            for relative in uncommitted:
                source_file = Path(origin) / relative
                if source_file.is_file() and not source_file.is_symlink():
                    (target / relative).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source_file, target / relative)
            imported = True
        copy = IntegrationCopy(
            path=str(target),
            source_kind="git_remote" if is_url else "git_local",
            source=redact_url(source) if is_url else origin,
            source_revision=revision,
            source_remote=redact_url(source) if is_url else source_remote,
            source_head=source_head,
            branch=work_branch,
            in_place=False,
            uncommitted_in_source=uncommitted,
            imported_uncommitted=imported,
        )
        return _record(copy)
    assert local is not None
    if use_git and not git_available():
        raise SourceError(
            "Git is not installed, so the copy cannot be tracked. Install Git, or "
            "pass --no-git to work on a plain folder copy"
        )
    target.mkdir(parents=True, exist_ok=True)
    skipped = _copy_tree(local, target)
    copy = IntegrationCopy(
        path=str(target),
        source_kind="directory",
        source=str(local),
        source_revision=None,
        source_remote=None,
        source_head=None,
        branch=None,
        in_place=False,
        skipped=skipped,
    )
    if use_git and git_available():
        _git(["-C", str(target), "init", "--quiet", "-b", work_branch])
        if git_name:
            _git(["-C", str(target), "config", "user.name", git_name])
        if git_email:
            _git(["-C", str(target), "config", "user.email", git_email])
        _require_identity(target)
        prepare_private_workspace(target)
        _git(["-C", str(target), "add", "-A"])
        _git(
            [
                "-C",
                str(target),
                "commit",
                "--quiet",
                "-m",
                f"Import {local.name} for SPLICE integration",
            ]
        )
        copy.branch = work_branch
        copy.source_revision = None
    return _record(copy)
