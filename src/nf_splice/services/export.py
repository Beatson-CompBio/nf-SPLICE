"""Deterministic, independently verified ZIP archives of a finished bundle.

Two scopes:

- ``bundle``: the published ``splice/`` folder only;
- ``pipeline``: the integration copy's pipeline files plus ``splice/`` (in a
  Git copy, the files Git tracks; otherwise an explicit walk), never
  ``.splice-local/``, ``.git/``, run directories, caches, environment or
  secrets files. Members sit at the archive root, and the archive's root
  ``ro-crate-metadata.json`` is the published ``splice/ro-crate-metadata.json``
  (its IDs are relative to the pipeline directory), so the ZIP is a
  recognisable Workflow RO-Crate. A developer's own root crate on disk is
  never changed; in the archive it is replaced by the reviewed one.

The bundle-only archive holds ``splice/`` alone. Its crate references files
(``main.nf``) that are not in it: it describes the pipeline but is not a
self-contained Workflow RO-Crate. Neither archive embeds its own checksum.

An archive is made only from a valid, current build. It is written to a
temporary file and renamed, never overwrites an existing archive without
permission, and is then reopened: every member's path, hash and the member
set are compared with the files that were meant to be included, and the
archive is extracted into an isolated folder whose bundle must validate.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any

from nf_splice.layout import PRIVATE_DIR, PUBLISHED_DIR, is_git_work_tree
from nf_splice.services.agent_skills import MANAGED_FOLDERS
from nf_splice.services.lifecycle import plan_promotion, validate_bundle

EXPORTS_DIR = f"{PRIVATE_DIR}/exports"
_FIXED_TIME = (1980, 1, 1, 0, 0, 0)
_EXCLUDED_DIRECTORIES = {
    ".git",
    PRIVATE_DIR,
    ".nf-splice-local",
    "work",
    ".nextflow",
    ".nf-test",
    "results",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
}
_EXCLUDED_NAMES = (
    re.compile(r"^\.nextflow\.log.*$"),
    re.compile(r"^\.env(\..*)?$"),
    re.compile(r".*\.(pem|key|p12|pfx|keystore)$"),
    re.compile(r"^(id_rsa|id_ed25519|id_ecdsa).*$"),
    re.compile(r"^(\.netrc|\.npmrc|\.pypirc)$"),
    re.compile(r"^credentials.*$"),
    re.compile(r".*secret.*", re.IGNORECASE),
    re.compile(r"^\.DS_Store$"),
)
_SECRET_CONTENT = (
    re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(rb"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(rb"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)
_MAX_FILE_BYTES = 100 * 1024 * 1024


class ExportScope(str, Enum):
    """What an archive contains."""

    BUNDLE = "bundle"
    PIPELINE = "pipeline"


class ExportError(RuntimeError):
    """An archive cannot be created or did not verify."""


@dataclass(slots=True)
class ExportResult:
    """The archive and how it was verified."""

    path: str
    scope: ExportScope
    size: int
    sha256: str
    members: list[dict[str, Any]]
    verified: bool
    checks: list[str] = field(default_factory=list)
    excluded: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "scope": self.scope.value,
            "size": self.size,
            "sha256": self.sha256,
            "members": len(self.members),
            "verified": self.verified,
            "checks": list(self.checks),
            "excluded": list(self.excluded),
        }


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _identity(root: Path) -> tuple[str, str]:
    bundle = json.loads((root / PUBLISHED_DIR / "bundle.json").read_text("utf-8"))
    pipeline = bundle.get("pipeline") or {}
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", str(pipeline.get("name") or root.name))
    version = re.sub(r"[^A-Za-z0-9._-]+", "-", str(pipeline.get("version") or "0"))
    return name.strip("-") or "pipeline", version.strip("-") or "0"


def default_archive_path(repository_root: str | Path, scope: ExportScope) -> Path:
    """``.splice-local/exports/<name>-<version>-<scope>.zip`` (never self-included)."""
    root = Path(repository_root).resolve()
    name, version = _identity(root)
    return root / EXPORTS_DIR / f"{name}-{version}-splice-{scope.value}.zip"


def _excluded_name(name: str) -> bool:
    return any(pattern.match(name) for pattern in _EXCLUDED_NAMES)


def _bundle_members(root: Path) -> tuple[list[tuple[str, Path]], list[str]]:
    members, excluded = [], []
    splice = root / PUBLISHED_DIR
    for current, directories, names in os.walk(splice, followlinks=False):
        directories[:] = sorted(
            item for item in directories if not item.startswith(".nf-splice")
        )
        for name in sorted(names):
            path = Path(current) / name
            relative = path.relative_to(root).as_posix()
            if name.startswith(".nf-splice") or name.endswith(".nf-splice.tmp"):
                excluded.append(relative)
                continue
            if path.is_symlink():
                raise ExportError(
                    f"{relative} is a symbolic link; it cannot be archived"
                )
            members.append((relative, path))
    return members, excluded


def _git_files(root: Path) -> list[str]:
    output = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--cached"],
        capture_output=True,
        check=True,
        timeout=120,
    ).stdout
    return [item.decode() for item in output.split(b"\0") if item]


def _pipeline_members(root: Path) -> tuple[list[tuple[str, Path]], list[str]]:
    excluded: list[str] = []
    candidates: set[str] = set()
    if is_git_work_tree(root):
        candidates.update(_git_files(root))
    else:
        for current, directories, names in os.walk(root, followlinks=False):
            relative_directory = Path(current).relative_to(root)
            kept = []
            for name in sorted(directories):
                if name in _EXCLUDED_DIRECTORIES:
                    excluded.append((relative_directory / name).as_posix() + "/")
                else:
                    kept.append(name)
            directories[:] = kept
            candidates.update((relative_directory / name).as_posix() for name in names)
    bundle, bundle_excluded = _bundle_members(root)
    candidates.update(item for item, _ in bundle)
    candidates.add(".gitignore")
    excluded.extend(bundle_excluded)
    members = []
    for relative in sorted(candidates):
        path = root / relative
        parts = PurePosixPath(relative).parts
        if not path.exists():
            continue
        if (
            any(part in _EXCLUDED_DIRECTORIES for part in parts[:-1])
            or _excluded_name(parts[-1])
            or any(relative.startswith(f"{folder}/") for folder in MANAGED_FOLDERS)
        ):
            excluded.append(relative)
            continue
        if path.is_symlink() or not path.is_file():
            excluded.append(f"{relative} (not a regular file)")
            continue
        if path.stat().st_size > _MAX_FILE_BYTES:
            excluded.append(f"{relative} (larger than 100 MB)")
            continue
        members.append((relative, path))
    return members, excluded


def _safe_member(name: str) -> bool:
    pure = PurePosixPath(name)
    return (
        bool(name)
        and not pure.is_absolute()
        and ".." not in pure.parts
        and "\\" not in name
    )


def export_archive(
    repository_root: str | Path,
    scope: ExportScope = ExportScope.BUNDLE,
    output: str | Path | None = None,
    *,
    overwrite: bool = False,
) -> ExportResult:
    """Create, then independently verify, a ZIP of the validated bundle."""
    root = Path(repository_root).resolve()
    if not (root / PUBLISHED_DIR / "bundle.json").is_file():
        raise ExportError("nothing is published yet; build the bundle first")
    report = validate_bundle(root)
    if not report.valid:
        raise ExportError(
            "the published bundle does not validate: "
            + "; ".join(item.message for item in report.issues[:3])
        )
    try:
        plan = plan_promotion(root)
    except ValueError as error:
        raise ExportError(f"the drafts cannot be checked: {error}") from error
    stale = [item.path for item in plan.changes if item.kind != "unchanged"]
    if plan.ready and stale:
        raise ExportError(
            "splice/ is out of date with the drafts ("
            + ", ".join(stale[:5])
            + "); build again before exporting"
        )
    target = (
        Path(output).expanduser().resolve()
        if output
        else default_archive_path(root, scope)
    )
    if target.suffix.lower() != ".zip":
        raise ExportError("the archive name must end in .zip")
    if target.exists() and not overwrite:
        raise ExportError(f"{target} already exists; pass --overwrite to replace it")
    members, excluded = (
        _bundle_members(root)
        if scope is ExportScope.BUNDLE
        else _pipeline_members(root)
    )
    if not members:
        raise ExportError("no files to archive")
    if scope is ExportScope.PIPELINE and target.is_relative_to(root):
        inside = target.relative_to(root).parts
        if not inside or inside[0] != PRIVATE_DIR:
            raise ExportError(
                "a pipeline archive inside the working copy would include itself; "
                "write it outside the copy or under .splice-local/"
            )
    prefix = ""
    payloads: dict[str, bytes] = {
        relative: path.read_bytes() for relative, path in members
    }
    replaced_root_crate = False
    if scope is ExportScope.PIPELINE:
        canonical = root / PUBLISHED_DIR / CRATE
        if canonical.is_file():
            replaced_root_crate = CRATE in payloads
            payloads[CRATE] = canonical.read_bytes()
    expected: dict[str, str] = {}
    secrets_found = []
    for relative, payload in sorted(payloads.items()):
        if any(pattern.search(payload) for pattern in _SECRET_CONTENT):
            secrets_found.append(relative)
        expected[prefix + relative] = _digest(payload)
    if secrets_found:
        raise ExportError(
            "these files look like they contain credentials and were not archived: "
            + ", ".join(secrets_found[:10])
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        prefix=".nf-splice-export-", suffix=".zip", dir=target.parent
    )
    os.close(handle)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(
            temporary, "w", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            for relative, payload in sorted(payloads.items()):
                info = zipfile.ZipInfo(prefix + relative, date_time=_FIXED_TIME)
                info.external_attr = 0o644 << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, payload)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    checks = verify_archive(target, expected, scope)
    if replaced_root_crate:
        checks.append(
            "the repository's own root ro-crate-metadata.json was replaced in the "
            "archive by the reviewed crate; the file on disk is unchanged"
        )
    payload = target.read_bytes()
    return ExportResult(
        path=str(target),
        scope=scope,
        size=len(payload),
        sha256=_digest(payload),
        members=[{"path": name, "sha256": digest} for name, digest in expected.items()],
        verified=True,
        checks=checks,
        excluded=excluded,
    )


CRATE = "ro-crate-metadata.json"


def verify_crate_members(extracted: Path) -> list[str]:
    """The archive-root crate is the published one and its local files exist."""
    root_crate = extracted / CRATE
    if not root_crate.is_file():
        raise ExportError("the pipeline archive has no root ro-crate-metadata.json")
    if root_crate.read_bytes() != (extracted / PUBLISHED_DIR / CRATE).read_bytes():
        raise ExportError(
            "the archive-root RO-Crate differs from splice/ro-crate-metadata.json"
        )
    try:
        crate = json.loads(root_crate.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ExportError(f"the archive-root RO-Crate is not JSON: {error}") from error
    missing = []
    for entity in crate.get("@graph") or []:
        identifier = str(entity.get("@id", "")) if isinstance(entity, dict) else ""
        if (
            not identifier
            or identifier in {"./", CRATE}
            or identifier.startswith(("#", "_:"))
            or "://" in identifier
            or identifier.startswith("mailto:")
        ):
            continue
        types = entity.get("@type")
        types = types if isinstance(types, list) else [types]
        if not {"File", "Dataset"} & {str(item) for item in types}:
            continue
        if not _safe_member(identifier.rstrip("/")):
            missing.append(identifier)
        elif not (extracted / identifier.rstrip("/")).exists():
            missing.append(identifier)
    if missing:
        raise ExportError(
            "the RO-Crate names files the archive does not contain: "
            + ", ".join(sorted(missing)[:10])
        )
    return [
        "the archive-root ro-crate-metadata.json is the published crate and every "
        "local file it names is in the archive"
    ]


def verify_archive(
    path: Path, expected: dict[str, str], scope: ExportScope
) -> list[str]:
    """Reopen an archive and prove it holds exactly the expected files."""
    checks = []
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ExportError("the archive is corrupt")
        names = archive.namelist()
        bad = [name for name in names if not _safe_member(name)]
        if bad:
            raise ExportError(f"unsafe archive member names: {bad[:5]}")
        if sorted(names) != sorted(expected):
            raise ExportError("the archive's members differ from the files to include")
        for name in names:
            if _digest(archive.read(name)) != expected[name]:
                raise ExportError(f"{name} does not match its source file")
        forbidden = [
            name
            for name in names
            if any(part in {PRIVATE_DIR, ".git"} for part in PurePosixPath(name).parts)
        ]
        if forbidden:
            raise ExportError(f"private or Git files in the archive: {forbidden[:5]}")
        checks.append(f"{len(names)} member(s) match their SHA-256 hashes")
        with tempfile.TemporaryDirectory(prefix="nf-splice-verify-") as scratch:
            archive.extractall(scratch)
            extracted = Path(scratch)
            base = extracted
            report = validate_bundle(base)
            if not report.valid:
                raise ExportError(
                    "the extracted bundle does not validate: "
                    + "; ".join(item.message for item in report.issues[:3])
                )
            checks.append("the extracted bundle validates")
            if scope is ExportScope.PIPELINE:
                checks.extend(verify_crate_members(extracted))
    checks.append("no .splice-local/ or .git/ content")
    return checks
