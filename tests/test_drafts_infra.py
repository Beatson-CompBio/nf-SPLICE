"""Restricted YAML 1.2, expected-value patches and safe draft storage."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from nf_splice.drafts import (
    ABSENT,
    DraftConflictError,
    DraftStoreError,
    DraftSyntaxError,
    PatchConflictError,
    PatchOp,
    create_file,
    diff,
    dump_yaml_data,
    load_yaml_draft,
    merge,
    patch_yaml,
    read_sidecar,
    read_yaml,
    replace_file,
    sha256,
    write_sidecar,
)
from nf_splice.drafts import patch as patching

DRAFT = ".splice-local/drafts/example.draft.yaml"


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("a: 1\na: 2\n", "duplicate"),
        ("a: &x 1\nb: *x\n", "anchors"),
        ("a: !!python/object:os.system 1\n", "tag"),
        ("a: !custom 1\n", "tag"),
        ("a: 2024-01-01\n", "timestamps"),
        ("a: 1\n---\nb: 2\n", "exactly one document"),
        ("1: a\n", "keys must be strings"),
        ("a: .nan\n", "NaN"),
        ("a: [1\n", "line"),
    ],
)
def test_unsafe_or_non_json_yaml_is_rejected(text: str, message: str) -> None:
    with pytest.raises(DraftSyntaxError) as raised:
        load_yaml_draft(text)
    assert message.lower() in str(raised.value).lower()


def test_yaml_1_2_semantics_preserve_types_and_strings() -> None:
    loaded = load_yaml_draft(
        "pattern: '^[A-Z]+\\.csv$'\nref: '#/$defs/group'\nswitch: on\n"
        "quoted: 'on'\nzero: '01'\nnumber: 0.10\nunion: [string, 'null']\n"
        "nothing: null\nflag: true\n"
    )
    assert loaded.data == {
        "pattern": "^[A-Z]+\\.csv$",
        "ref": "#/$defs/group",
        "switch": "on",
        "quoted": "on",
        "zero": "01",
        "number": 0.1,
        "union": ["string", "null"],
        "nothing": None,
        "flag": True,
    }
    assert any("'on'" in warning for warning in loaded.warnings)


def test_dumped_drafts_round_trip_for_yaml_1_1_and_1_2_readers() -> None:
    data = {
        "words": ["on", "off", "yes", "no", "01", "1e3", "2024-01-01", "~", "null"],
        "text": "plain text",
        "colon": "a: b",
        "empty": "",
        "nested": {"pattern": "^a/(?P<x>[^/]+)$", "value": 1.5, "flag": False},
    }
    text = dump_yaml_data(data, header=["Draft header"])
    assert text.startswith("# Draft header\n")
    assert load_yaml_draft(text).data == data
    assert yaml.safe_load(text) == data
    assert dump_yaml_data(data) == dump_yaml_data(json.loads(json.dumps(data)))
    assert "absent: null" in dump_yaml_data({"absent": None})


def test_diff_and_merge_are_three_way() -> None:
    base = {"a": 1, "b": {"c": 2}, "items": [1, 2]}
    planned = {"a": 1, "b": {"c": 3}, "items": [1, 2, 3], "new": "x"}
    operations = diff(base, planned)
    assert patching.apply(base, operations) == planned

    concurrent = {"a": 9, "b": {"c": 2}, "items": [1, 2], "other": True}
    merged, conflicts = merge(concurrent, operations)
    assert conflicts == []
    assert merged == {
        "a": 9,
        "b": {"c": 3},
        "items": [1, 2, 3],
        "new": "x",
        "other": True,
    }

    overlapping = {"a": 1, "b": {"c": 7}, "items": [1, 2]}
    _, conflicts = merge(overlapping, operations)
    assert [item.path for item in conflicts] == ["/b/c"]
    assert conflicts[0].expected == 2 and conflicts[0].actual == 7

    already = patching.apply(base, operations)
    assert (
        patching.apply(already, [op for op in operations if op.op != "add"]) == already
    )
    assert PatchOp.from_json(operations[0].to_json()) == operations[0]
    assert PatchOp("add", "/x", 1).to_json() == {"op": "add", "path": "/x", "value": 1}
    assert patching.resolve(base, "/missing") is ABSENT
    with pytest.raises(PatchConflictError):
        patching.apply(overlapping, operations)


def test_patch_preserves_comments_and_concurrent_external_edits(tmp_path: Path) -> None:
    original = (
        "# Developer notes stay.\n"
        "pipeline:\n"
        "  name: example  # inline comment\n"
        "  version: 1.0.0\n"
        "outputs: []\n"
    )
    assert create_file(tmp_path, DRAFT, original.encode())
    assert not create_file(tmp_path, DRAFT, b"other: 1\n")
    planned = read_yaml(tmp_path, DRAFT)
    assert planned.draft is not None
    operations = diff(
        planned.draft.data,
        {"pipeline": {"name": "example", "version": "1.1.0"}, "outputs": []},
    )

    external = original.replace("outputs: []", "outputs: []\nextra: kept  # mine")
    path = tmp_path / DRAFT
    path.write_text(external, encoding="utf-8")

    preview = patch_yaml(tmp_path, DRAFT, operations, write=False)
    assert not preview.wrote and path.read_text(encoding="utf-8") == external
    applied = patch_yaml(tmp_path, DRAFT, operations, write=True)
    text = path.read_text(encoding="utf-8")
    assert applied.wrote
    assert "# Developer notes stay." in text and "# inline comment" in text
    assert "extra: kept  # mine" in text
    assert "version: 1.1.0" in text
    assert "-  version: 1.0.0" in applied.diff

    path.write_text(text.replace("1.1.0", "2.0.0"), encoding="utf-8")
    stale = diff({"pipeline": {"version": "1.1.0"}}, {"pipeline": {"version": "3.0"}})
    with pytest.raises(DraftConflictError) as raised:
        patch_yaml(tmp_path, DRAFT, stale, write=True)
    assert raised.value.conflicts[0].actual == "2.0.0"
    assert "2.0.0" in path.read_text(encoding="utf-8")


def test_malformed_drafts_are_preserved_not_regenerated(tmp_path: Path) -> None:
    create_file(tmp_path, DRAFT, b"pipeline: [unclosed\n")
    state = read_yaml(tmp_path, DRAFT)
    assert state.error is not None and state.error.line is not None
    with pytest.raises(DraftStoreError, match="syntax"):
        patch_yaml(tmp_path, DRAFT, [PatchOp("add", "/x", 1)], write=True)
    assert (tmp_path / DRAFT).read_bytes() == b"pipeline: [unclosed\n"


def test_compare_and_swap_and_path_safety(tmp_path: Path) -> None:
    relative = ".splice-local/drafts/file.txt"
    first = replace_file(tmp_path, relative, b"one", expected_sha256=None)
    assert first == sha256(b"one")
    with pytest.raises(DraftConflictError):
        replace_file(tmp_path, relative, b"two", expected_sha256=None)
    replace_file(tmp_path, relative, b"two", expected_sha256=first)
    assert (tmp_path / relative).read_bytes() == b"two"
    assert not list((tmp_path / ".splice-local" / "drafts").glob(".*.tmp"))

    for unsafe in ("../x", "/etc/passwd", "splice/../x", "other/file"):
        with pytest.raises(DraftStoreError):
            replace_file(tmp_path, unsafe, b"x", expected_sha256=None)
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "splice").mkdir(exist_ok=True)
    (tmp_path / "splice" / "linked").symlink_to(outside)
    with pytest.raises(DraftStoreError, match="symbolic link"):
        replace_file(tmp_path, "splice/linked/file", b"x", expected_sha256=None)
    assert not any(outside.iterdir())


def test_sidecars_are_compare_and_swap_json(tmp_path: Path) -> None:
    document, digest = read_sidecar(tmp_path, "outputs")
    assert document == {} and digest is None
    digest = write_sidecar(
        tmp_path, "outputs", {"candidates": {}}, expected_sha256=None
    )
    assert read_sidecar(tmp_path, "outputs") == ({"candidates": {}}, digest)
    with pytest.raises(DraftConflictError):
        write_sidecar(tmp_path, "outputs", {}, expected_sha256=None)
