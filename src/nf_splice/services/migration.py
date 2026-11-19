"""Move drafts, reviews and sessions of an earlier layout into ``.splice-local/``.

Earlier development builds kept drafts in ``splice/drafts/`` (with review
sidecars in ``splice/drafts/.reviews/``) and agent sessions in
``.nf-splice-local/agent/``. Migration is explicit and reversible:

- ``plan_migration`` lists every move, its content hash and any conflict, and
  changes nothing;
- ``apply_migration`` backs up every source file, copies it to its new path,
  verifies each hash, and only then removes the originals; any failure
  restores the original state;
- ``rollback_migration`` restores the backup and removes the copies that are
  still unchanged.

A target that already exists with different content is a conflict: nothing
is overwritten. Running migration again when nothing is left to move is a
no-op.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from nf_splice.layout import (
    DRAFTS_DIR,
    LEGACY_AGENT_DIR,
    LEGACY_DRAFTS_DIR,
    PRIVATE_DIR,
    REVIEWS_DIR,
    SESSIONS_DIR,
    prepare_private_workspace,
)

MIGRATIONS_DIR = f"{PRIVATE_DIR}/migrations"
_DRAFT_NAMES = {
    "bundle.draft.yaml": "bundle.draft.yaml",
    "inputs.schema.draft.yaml": "inputs.draft.yaml",
    "outputs.draft.yaml": "outputs.draft.yaml",
    "components.draft.yaml": "components.draft.yaml",
    "execution-profiles.draft.yaml": "execution-profiles.draft.yaml",
    "ro-crate-metadata.draft.yaml": "provenance.draft.yaml",
}


class MigrationError(RuntimeError):
    """Migration cannot proceed safely."""


@dataclass(frozen=True, slots=True)
class Move:
    """One file to move, with its content hash."""

    source: str
    target: str
    sha256: str

    def to_json(self) -> dict[str, str]:
        return {"source": self.source, "target": self.target, "sha256": self.sha256}


@dataclass(slots=True)
class MigrationPlan:
    """Everything a migration would do, and what stops it."""

    moves: list[Move] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def needed(self) -> bool:
        return bool(self.moves)

    def to_json(self) -> dict[str, Any]:
        return {
            "needed": self.needed,
            "moves": [item.to_json() for item in self.moves],
            "conflicts": list(self.conflicts),
            "skipped": list(self.skipped),
            "notes": list(self.notes),
        }


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _files(base: Path) -> list[Path]:
    found = []
    for current, directories, names in os.walk(base, followlinks=False):
        directories.sort()
        for name in sorted(names):
            found.append(Path(current) / name)
    return found


def _draft_target(relative_inside: str) -> str | None:
    """New path for a file found below ``splice/drafts/``."""
    parts = PurePosixPath(relative_inside).parts
    if len(parts) == 1 and parts[0] in _DRAFT_NAMES:
        return f"{DRAFTS_DIR}/{_DRAFT_NAMES[parts[0]]}"
    if len(parts) == 2 and parts[0] == "configs" and parts[1].endswith(".draft.config"):
        return f"{DRAFTS_DIR}/configs/{parts[1]}"
    if len(parts) == 2 and parts[0] == ".reviews" and parts[1].endswith(".review.json"):
        return f"{REVIEWS_DIR}/{parts[1]}"
    return None


def _session_target(relative_inside: str) -> str | None:
    """New path for a file found below ``.nf-splice-local/agent/``."""
    parts = PurePosixPath(relative_inside).parts
    if len(parts) < 3 or parts[0] != "sessions":
        return None
    session, rest = parts[1], parts[2:]
    if rest == ("tools.jsonl",):
        rest = ("events.jsonl",)
    if rest[0] == "checkpoints" and len(rest) >= 3:
        checkpoint, inner = rest[1], rest[2:]
        if inner[:2] == ("splice", "drafts"):
            mapped = _draft_target("/".join(inner[2:]))
            if mapped is None:
                return None
            return f"{SESSIONS_DIR}/{session}/checkpoints/{checkpoint}/{mapped}"
    if rest[0] in {"sandbox", "scripted-progress.json"}:
        return None
    return f"{SESSIONS_DIR}/{session}/{'/'.join(rest)}"


def plan_migration(repository_root: str | Path) -> MigrationPlan:
    """What migration would move; changes nothing."""
    root = Path(repository_root).resolve()
    plan = MigrationPlan()
    for legacy, mapper in (
        (LEGACY_DRAFTS_DIR, _draft_target),
        (LEGACY_AGENT_DIR, _session_target),
    ):
        base = root / legacy
        if not base.is_dir():
            continue
        if base.is_symlink():
            plan.conflicts.append(f"{legacy} is a symbolic link; refusing to read it")
            continue
        for path in _files(base):
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                plan.conflicts.append(
                    f"{relative} is a symbolic link; refusing to move it"
                )
                continue
            target = mapper(path.relative_to(base).as_posix())
            if target is None:
                if path.name not in {"lock.json"} and not path.name.endswith(".tmp"):
                    plan.skipped.append(relative)
                continue
            digest = _hash(path)
            destination = root / target
            if destination.exists():
                if destination.is_file() and _hash(destination) == digest:
                    plan.notes.append(f"{target} already holds {relative}; kept")
                    plan.moves.append(Move(relative, target, digest))
                    continue
                plan.conflicts.append(
                    f"{target} already exists with different content; it would be "
                    f"overwritten by {relative}"
                )
                continue
            plan.moves.append(Move(relative, target, digest))
    if (root / LEGACY_AGENT_DIR / "lock.json").exists():
        plan.notes.append("an old session lock was found; it is not migrated")
    return plan


def apply_migration(repository_root: str | Path) -> dict[str, Any]:
    """Back up, copy, verify, then remove the originals; roll back on failure."""
    root = Path(repository_root).resolve()
    plan = plan_migration(root)
    if plan.conflicts:
        raise MigrationError(
            "migration stopped before changing anything: " + "; ".join(plan.conflicts)
        )
    if not plan.needed:
        return {"migrated": False, "reason": "nothing to migrate", **plan.to_json()}
    prepare_private_workspace(root)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    record_dir = root / MIGRATIONS_DIR / stamp
    backup = record_dir / "backup"
    backup.mkdir(parents=True, mode=0o700)
    created: list[Path] = []
    try:
        for move in plan.moves:
            source = root / move.source
            saved = backup / move.source
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, saved)
            if _hash(saved) != move.sha256:
                raise MigrationError(f"backup of {move.source} does not match")
        for move in plan.moves:
            target = root / move.target
            if target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / move.source, target)
            created.append(target)
            if _hash(target) != move.sha256:
                raise MigrationError(f"copy of {move.source} does not match")
        record_data = {
            "migration": stamp,
            "status": "applied",
            "moves": [item.to_json() for item in plan.moves],
            "created": [item.relative_to(root).as_posix() for item in created],
        }
        (record_dir / "record.json").write_text(
            json.dumps(record_data, indent=2) + "\n", encoding="utf-8"
        )
    except BaseException:
        for path in created:
            path.unlink(missing_ok=True)
        shutil.rmtree(record_dir, ignore_errors=True)
        raise
    for move in plan.moves:
        (root / move.source).unlink(missing_ok=True)
    for legacy in (LEGACY_DRAFTS_DIR, LEGACY_AGENT_DIR):
        _remove_empty(root / legacy)
    return {"migrated": True, "migration": stamp, **plan.to_json()}


def _remove_empty(base: Path) -> None:
    if not base.is_dir():
        return
    for current, directories, _names in os.walk(base, topdown=False):
        for name in directories:
            try:
                (Path(current) / name).rmdir()
            except OSError:
                pass
    try:
        base.rmdir()
    except OSError:
        pass


def migrations(repository_root: str | Path) -> list[dict[str, Any]]:
    """Applied migrations, most recent first."""
    root = Path(repository_root).resolve()
    found = []
    for path in sorted((root / MIGRATIONS_DIR).glob("*/record.json"), reverse=True):
        found.append(json.loads(path.read_text(encoding="utf-8")))
    return found


def rollback_migration(
    repository_root: str | Path, migration: str | None = None
) -> dict[str, Any]:
    """Restore the originals of one migration and remove unchanged copies."""
    root = Path(repository_root).resolve()
    applied = [item for item in migrations(root) if item.get("status") == "applied"]
    if migration is not None:
        applied = [item for item in applied if item["migration"] == migration]
    if not applied:
        raise MigrationError("no applied migration to roll back")
    record = applied[0]
    record_dir = root / MIGRATIONS_DIR / record["migration"]
    backup = record_dir / "backup"
    changed = [
        move["target"]
        for move in record["moves"]
        if (root / move["target"]).is_file()
        and _hash(root / move["target"]) != move["sha256"]
    ]
    if changed:
        raise MigrationError(
            "these files changed after migration; roll back would lose the "
            "changes: " + ", ".join(changed)
        )
    for move in record["moves"]:
        source = root / move["source"]
        if not source.exists():
            source.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup / move["source"], source)
    for target in record.get("created", []):
        (root / target).unlink(missing_ok=True)
    record["status"] = "rolled_back"
    (record_dir / "record.json").write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8"
    )
    return {"rolled_back": record["migration"], "restored": len(record["moves"])}
