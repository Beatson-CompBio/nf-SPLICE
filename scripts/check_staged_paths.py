"""Reject staged development-only paths, even when they were force-added.

Run from the repository root before every commit (or from CI against a
diff range)::

    python scripts/check_staged_paths.py            # inspects the index
    python scripts/check_staged_paths.py PATH ...   # inspects explicit paths
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import PurePosixPath

# Development-only prefixes that must never enter version control.
FORBIDDEN_PREFIXES = (
    ".nf-splice-local/",
    ".venv/",
    "venv/",
    ".mypy_cache/",
    ".ruff_cache/",
    ".pytest_cache/",
    "build/",
    "dist/",
    ".nextflow/",
    "work/",
)
# File names that indicate credentials or local runtime state.
FORBIDDEN_NAMES = frozenset(
    {".env", ".envrc", ".coverage", "credentials.json", ".netrc", "id_rsa"}
)
FORBIDDEN_SUFFIXES = (".pem", ".key", ".p12", ".nf-splice.tmp")


def violations(paths: list[str]) -> list[str]:
    """Return every path that is development-only or secret-bearing."""
    found = []
    for raw in paths:
        path = PurePosixPath(raw.strip())
        text = path.as_posix()
        if not text or text == ".":
            continue
        if any(
            text == prefix.rstrip("/") or text.startswith(prefix)
            for prefix in FORBIDDEN_PREFIXES
        ):
            found.append(text)
        elif path.name in FORBIDDEN_NAMES or text.endswith(FORBIDDEN_SUFFIXES):
            found.append(text)
    return found


def _staged_paths() -> list[str]:
    result = subprocess.run(
        ("git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"),
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def main(argv: list[str]) -> int:
    paths = argv or _staged_paths()
    bad = violations(paths)
    for item in bad:
        print(f"refusing development-only or secret path: {item}", file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
