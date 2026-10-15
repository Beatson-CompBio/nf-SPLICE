"""Preview staged operations on a private copy of the repository.

In an assisted session the agent stages operations instead of applying them.
Each staged operation runs, through the real services, against a copy of the
repository inside the session directory, so the user sees the exact diff and
validation outcome before approving. The copy omits Git metadata, the
workspace, work directories and large files; private audit records are not
written for previews.
"""

from __future__ import annotations

import difflib
import os
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from nf_splice.agents.operations import Operation, OperationContext
from nf_splice.agents.permissions import ExecutionPolicy
from nf_splice.layers import ChangeContext
from nf_splice.services.audit import suppress_private_audit
from nf_splice.services.lifecycle import validate_layer

_SKIP = {
    ".git",
    ".nf-splice-local",
    ".nextflow",
    "work",
    "node_modules",
    "__pycache__",
    ".venv",
    ".nf-splice-staging",
    ".nf-splice-backup",
}
_MAX_COPY_BYTES = 5_000_000


def _snapshot(root: Path) -> dict[str, str]:
    splice = root / "splice"
    found: dict[str, str] = {}
    if not splice.is_dir():
        return found
    for current, directories, names in os.walk(splice, followlinks=False):
        directories[:] = sorted(item for item in directories if item not in _SKIP)
        for name in sorted(names):
            path = Path(current) / name
            if path.suffix == ".json" and name.endswith(".review.json"):
                continue
            try:
                found[path.relative_to(root).as_posix()] = path.read_text(
                    encoding="utf-8", errors="replace"
                )
            except OSError:
                continue
    return found


class Sandbox:
    """A disposable copy used to preview staged operations."""

    def __init__(self, root: Path, directory: Path, examples: list[Path]) -> None:
        self.source = root.resolve()
        self.directory = directory
        self.repository = directory / "repository"
        if directory.exists():
            shutil.rmtree(directory)
        directory.mkdir(parents=True, mode=0o700)
        skip_paths = {item.resolve() for item in examples}

        def ignore(current: str, names: list[str]) -> set[str]:
            ignored = set()
            for name in names:
                path = Path(current) / name
                if name in _SKIP or path.is_symlink() or path.resolve() in skip_paths:
                    ignored.add(name)
                elif path.is_file() and path.stat().st_size > _MAX_COPY_BYTES:
                    ignored.add(name)
            return ignored

        shutil.copytree(self.source, self.repository, ignore=ignore)
        self.before = _snapshot(self.repository)

    def run(
        self,
        operation: Operation,
        arguments: Mapping[str, Any],
        *,
        change: ChangeContext,
        policy: ExecutionPolicy,
        examples: list[Path],
    ) -> dict[str, Any]:
        """Run one operation against the copy (never against the repository)."""
        context = OperationContext(
            root=self.repository,
            change=change,
            policy=policy,
            session_directory=self.directory,
            examples=examples,
        )
        with suppress_private_audit():
            return operation.handler(context, arguments)

    def diff(self) -> str:
        """Unified diff of ``splice/`` against the state before staging."""
        after = _snapshot(self.repository)
        parts: list[str] = []
        for path in sorted(set(self.before) | set(after)):
            old, new = self.before.get(path, ""), after.get(path, "")
            if old == new:
                continue
            parts.extend(
                difflib.unified_diff(
                    old.splitlines(keepends=True),
                    new.splitlines(keepends=True),
                    fromfile=f"a/{path}",
                    tofile=f"b/{path}",
                )
            )
        return "".join(parts)

    def issues(self, layers: list[str]) -> list[str]:
        """Validation errors the staged changes would leave in ``layers``."""
        found = []
        for layer in layers:
            try:
                validation = validate_layer(self.repository, layer)
            except ValueError as error:
                found.append(f"{layer}: {error}")
                continue
            found.extend(
                f"{item.path}#{item.pointer or '/'} [{item.code}] {item.message}"
                for item in validation.errors
            )
        return found

    def close(self) -> None:
        shutil.rmtree(self.directory, ignore_errors=True)
