"""Guard the frozen nf-splice 0.1.0 fixture against accidental edits."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from nf_splice.validators import validate_analysis_output

LEGACY = Path(__file__).parent / "fixtures" / "legacy-0.1.0"
_UNCHECKED = {"README.md", "SHA256SUMS"}


def _checksums() -> dict[str, str]:
    lines = (LEGACY / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    result = {}
    for line in lines:
        digest, relative = line.split(maxsplit=1)
        result[relative.strip()] = digest
    return result


def test_legacy_fixture_bytes_are_frozen() -> None:
    expected = _checksums()
    present = {
        path.relative_to(LEGACY).as_posix()
        for path in LEGACY.rglob("*")
        if path.is_file()
    } - _UNCHECKED
    assert present == set(expected)
    for relative, digest in expected.items():
        payload = (LEGACY / relative).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == digest, relative


def test_legacy_lock_inventory_matches_frozen_bundle_bytes() -> None:
    splice = LEGACY / "repository" / "splice"
    lock = json.loads((splice / "nf-splice.lock.json").read_text(encoding="utf-8"))
    assert lock["schema_version"] == "1.0"
    assert lock["generator"] == {"name": "nf-splice", "version": "0.1.0"}
    for relative, record in lock["managed_files"].items():
        payload = (splice / relative).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == record["sha256"], relative


def test_legacy_analysis_output_is_valid_against_its_own_static_contract() -> None:
    schema = json.loads(
        (LEGACY / "repository" / "splice" / "outputs.schema.json").read_text(
            encoding="utf-8"
        )
    )
    document = json.loads(
        (LEGACY / "completed-job" / "analysis_output.json").read_text(encoding="utf-8")
    )
    report = validate_analysis_output(document, schema)
    assert report.valid, report.issues
    assert dict(report.by_scope) == {"library": 3, "run": 1, "sample": 2}
