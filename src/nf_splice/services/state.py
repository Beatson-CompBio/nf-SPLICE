"""Preview and apply non-destructive legacy state reconciliation."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from nf_splice.inspectors.splice_tree import (
    validate_authoring_state,
    validate_lock_state,
)


class StateMigrationError(ValueError):
    """Raised when legacy state cannot be reconciled safely."""


class MigrationChangeKind(str, Enum):
    """Effect of one legacy-state reconciliation."""

    CREATE = "create"
    UNCHANGED = "unchanged"


@dataclass(frozen=True, slots=True)
class StateMigrationChange:
    """One source/destination pair in a migration preview."""

    source: Path
    destination: Path
    kind: MigrationChangeKind


@dataclass(frozen=True, slots=True)
class StateMigrationResult:
    """Deterministic migration preview and application result."""

    changes: tuple[StateMigrationChange, ...]
    wrote: bool


_VALIDATORS = {
    "nf-splice.yaml": validate_authoring_state,
    "nf-splice.lock.json": validate_lock_state,
}


def plan_state_migration(repository_root: str | Path) -> StateMigrationResult:
    """Validate and preview copying recognized root state into ``splice/``."""
    root = Path(repository_root).resolve()
    splice = root / "splice"
    if splice.exists() and (splice.is_symlink() or not splice.is_dir()):
        raise StateMigrationError(
            f"repository-root splice path must be a regular directory: {splice}"
        )

    changes: list[StateMigrationChange] = []
    for name, validator in _VALIDATORS.items():
        source = root / name
        if not source.exists() and not source.is_symlink():
            continue
        if source.is_symlink() or not source.is_file():
            raise StateMigrationError(f"legacy state must be a regular file: {source}")
        classification, detail = validator(source)
        if classification != "recognized":
            raise StateMigrationError(
                f"legacy state {source} is {classification}: {detail}"
            )

        destination = splice / name
        if destination.exists() or destination.is_symlink():
            if destination.is_symlink() or not destination.is_file():
                raise StateMigrationError(
                    f"migration destination must be a regular file: {destination}"
                )
            if source.read_bytes() != destination.read_bytes():
                raise StateMigrationError(
                    f"legacy source conflicts with migration destination: "
                    f"{source} -> {destination}"
                )
            kind = MigrationChangeKind.UNCHANGED
        else:
            kind = MigrationChangeKind.CREATE
        changes.append(
            StateMigrationChange(
                source=source,
                destination=destination,
                kind=kind,
            )
        )
    return StateMigrationResult(changes=tuple(changes), wrote=False)


def apply_state_migration(repository_root: str | Path) -> StateMigrationResult:
    """Atomically copy compatible legacy files while preserving every source."""
    plan = plan_state_migration(repository_root)
    pending = tuple(
        item for item in plan.changes if item.kind is MigrationChangeKind.CREATE
    )
    if not pending:
        return plan

    root = Path(repository_root).resolve()
    splice = root / "splice"
    created_splice = not splice.exists()
    splice.mkdir(exist_ok=True)
    temporaries: list[Path] = []
    written: list[Path] = []
    try:
        for item in pending:
            if item.destination.exists() or item.destination.is_symlink():
                raise StateMigrationError(
                    f"migration destination appeared after preview: {item.destination}"
                )
            temporary = item.destination.with_name(
                f".{item.destination.name}.nf-splice-migration.tmp"
            )
            with temporary.open("xb") as handle:
                handle.write(item.source.read_bytes())
                handle.flush()
                os.fsync(handle.fileno())
            temporaries.append(temporary)
        for item, temporary in zip(pending, temporaries, strict=True):
            os.replace(temporary, item.destination)
            written.append(item.destination)
    except Exception:
        for path in written:
            path.unlink(missing_ok=True)
        raise
    finally:
        for path in temporaries:
            path.unlink(missing_ok=True)
        if created_splice and splice.exists() and not any(splice.iterdir()):
            splice.rmdir()
    return StateMigrationResult(changes=plan.changes, wrote=True)
