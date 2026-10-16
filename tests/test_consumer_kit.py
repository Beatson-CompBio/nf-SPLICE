"""The bundle consumer kit stays true to the contracts it describes.

The kit is for developers who build on bundles without nf-splice, so these
tests use it the way they would: plain JSON Schema validators over the kit's
own copies of the definitions and examples. They also check that every key
path the skills name exists in the contracts, so a renamed or invented key
fails here rather than in someone's database.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from jsonschema import (  # type: ignore[import-untyped]
    Draft7Validator,
    Draft202012Validator,
)

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / "bundle-consumer-kit"
EXAMPLE = KIT / "examples" / "bundle"
SKILLS = (
    "splice-bundle-contracts",
    "splice-bundle-ingestion",
    "splice-analysis-output",
    "splice-web-ui",
    "splice-job-launch",
)
FAMILY_FILES = {
    "bundle": "bundle.json",
    "inputs": "inputs.schema.json",
    "outputs": "outputs.schema.json",
    "components": "components.json",
    "execution-profiles": "execution-profiles.json",
}
KIT_DOCUMENTS = [
    KIT / "README.md",
    KIT / "AGENTS.md",
    *(KIT / "skills" / name / "SKILL.md" for name in SKILLS),
]


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def test_generated_files_are_current() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_consumer_kit.py"), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("family", sorted(FAMILY_FILES))
def test_example_bundle_validates_with_plain_json_schema(family: str) -> None:
    document = _load(EXAMPLE / FAMILY_FILES[family])
    declared = _load(EXAMPLE / "bundle.json")["schemas"]
    uri = f"https://schemas.splice-data.io/workflow-bundle/{family}"
    revision = declared[uri]["version"]
    schema = _load(KIT / "schemas" / family / f"v{revision}" / "schema.json")
    Draft202012Validator(schema).validate(document)
    example = _load(KIT / "schemas" / family / f"v{revision}" / "example.json")
    Draft202012Validator(schema).validate(example)


def test_job_inventory_validates_against_its_bundle() -> None:
    runtime = _load(EXAMPLE / "outputs.schema.json")
    Draft7Validator.check_schema(runtime)
    Draft202012Validator.check_schema(_load(EXAMPLE / "inputs.schema.json"))
    document = _load(KIT / "examples" / "analysis_output.json")
    Draft7Validator(runtime).validate(document)
    catalogue = runtime["x-output-catalog"]
    keys = {item["key"] for item in catalogue["output_types"]}
    used = {record["output_type"] for record in document["files"]}
    # The example job took the STAR route: other routes are absent, as the
    # skills say they will be.
    assert {"star_alignment", "multiqc_report"} <= used < keys
    assert not {"hisat2_alignment", "salmon_quantification"} & used


def test_identity_is_repeated_consistently_in_the_example() -> None:
    bundle = _load(EXAMPLE / "bundle.json")["pipeline"]
    identity = {key: bundle[key] for key in ("id", "name", "version")}
    for found in (
        _load(EXAMPLE / "components.json")["pipeline"],
        _load(EXAMPLE / "execution-profiles.json")["pipeline"],
        _load(EXAMPLE / "inputs.schema.json")["x-splice-pipeline"],
        _load(EXAMPLE / "outputs.schema.json")["x-output-catalog"]["pipeline"],
    ):
        assert {key: found[key] for key in identity} == identity


@pytest.mark.parametrize("name", SKILLS)
def test_skills_are_complete_and_listed(name: str) -> None:
    text = (KIT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
    header = re.match(r"---\nname: (.+)\ndescription: (.+)\n---\n", text)
    assert header and header.group(1) == name and len(header.group(2)) > 80
    assert "## When to use" in text
    for listing in (
        KIT / "README.md",
        KIT / "AGENTS.md",
        ROOT / "docs" / "CONTRACTS.md",
    ):
        assert name in listing.read_text(encoding="utf-8"), (name, listing.name)


def _known_keys() -> set[str]:
    """Every key name the contracts, the runtime schema or nf-schema define."""
    known: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in {"properties", "$defs", "definitions", "patternProperties"}:
                    if isinstance(value, dict):
                        known.update(value)
                known.add(key)
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for path in sorted((KIT / "schemas").rglob("*.json")):
        walk(_load(path))
    for path in sorted(EXAMPLE.glob("*.json")):
        walk(_load(path))
    walk(_load(KIT / "examples" / "analysis_output.json"))
    # Standard JSON Schema and nf-schema keywords a parameter may carry.
    known |= {
        "title", "description", "type", "default", "enum", "minimum", "maximum",
        "pattern", "format", "required", "help_text", "fa_icon", "mimetype",
        "schema",
    }  # fmt: skip
    return known


_PATH = re.compile(r"`([A-Za-z_$][\w$\-]*(?:\[\])?(?:\.[\w$\-*<>\[\]]+)+)`")
_SEGMENT = re.compile(r"^<[^>]+>$|^\*$")


def test_every_key_path_named_by_the_kit_exists() -> None:
    known = _known_keys()
    # File names and placeholders are not key paths.
    ignored = {"json", "md", "yaml", "config", "cff", "py", "js"}
    for document in KIT_DOCUMENTS:
        text = document.read_text(encoding="utf-8")
        for path in _PATH.findall(text):
            segments = [re.sub(r"\[[^\]]*\]$", "", part) for part in path.split(".")]
            if segments[-1] in ignored or segments[0] in {"params", "ajv"}:
                continue
            if re.match(r"^v?\d", path):  # a version such as v1.2.3
                continue
            for segment in segments:
                if _SEGMENT.match(segment) or segment in known:
                    continue
                where = document.relative_to(ROOT)
                pytest.fail(f"{where}: `{path}` names unknown key {segment!r}")


def test_kit_needs_no_nf_splice_commands_except_result_generation() -> None:
    for document in KIT_DOCUMENTS:
        text = document.read_text(encoding="utf-8")
        for command in re.findall(r"`(nf-splice [^`]+)`", text):
            assert command == "nf-splice analysis-output generate", (
                document.name,
                command,
            )


def test_kit_never_names_the_retired_free_text_modality_key() -> None:
    """``pipeline.modality`` was replaced by typed ``assay_capabilities``."""
    for document in KIT_DOCUMENTS:
        text = document.read_text(encoding="utf-8")
        assert "`modality`" not in text, document.name
        assert "pipeline.modality" not in text, document.name
