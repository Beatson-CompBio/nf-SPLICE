"""Docs stay truthful: commands exist, links resolve, references are current."""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

import typer
import yaml  # type: ignore[import-untyped]

from nf_splice.cli import app

ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = [
    ROOT / "README.md",
    *sorted((ROOT / "docs").rglob("*.md")),
]
_FENCE = re.compile(r"```bash\n(.*?)```", re.DOTALL)


def _commands() -> list[tuple[Path, list[str]]]:
    found = []
    for path in DOCUMENTS:
        for block in _FENCE.findall(path.read_text(encoding="utf-8")):
            for line in block.replace("\\\n", " ").splitlines():
                line = line.strip()
                if line.startswith("nf-splice "):
                    found.append((path, shlex.split(line)[1:]))
    return found


def _resolve(arguments: list[str]) -> tuple[Any, list[str]]:
    command: Any = typer.main.get_command(app)
    remaining = list(arguments)
    while hasattr(command, "get_command"):
        while remaining and remaining[0].startswith("--"):
            option = remaining.pop(0)
            if option == "--actor":
                remaining.pop(0)
        if not remaining:
            break
        name = remaining.pop(0)
        child = command.get_command(command.context_class(command), name)
        assert child is not None, f"unknown command {name!r} in {arguments}"
        command = child
    return command, remaining


def test_every_documented_command_and_option_exists() -> None:
    commands = _commands()
    assert len(commands) > 40
    for path, arguments in commands:
        command, remaining = _resolve(arguments)
        options = {
            name
            for parameter in command.params
            for name in getattr(parameter, "opts", [])
        } | {"--help"}
        for token in remaining:
            if token.startswith("--"):
                assert token.split("=", 1)[0] in options, (path.name, arguments, token)


def test_relative_links_resolve() -> None:
    for path in DOCUMENTS:
        for target in re.findall(r"\]\(([^)#]+)\)", path.read_text(encoding="utf-8")):
            if "://" in target:
                continue
            assert (path.parent / target).exists(), (path.name, target)


def test_generated_field_references_are_current() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "generate_schema_docs.py"), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_reserved_word_only_in_the_glossary_explanation() -> None:
    for path in DOCUMENTS:
        if path.name in {"GLOSSARY.md", "ARCHITECTURE_DECISIONS.md"}:
            continue
        assert "manifest" not in path.read_text(encoding="utf-8").lower(), path.name


def test_command_reference_is_current() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "generate_cli_docs.py"), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_documented_analysis_output_example_is_valid(tmp_path: Path) -> None:
    from jsonschema import Draft7Validator  # type: ignore[import-untyped]

    from nf_splice.domain import (
        OutputEntityType,
        OutputFormat,
        OutputScope,
        ReviewedOutput,
    )
    from nf_splice.renderers import (
        OutputContractInput,
        OutputPipeline,
        render_outputs,
    )

    def output(
        key: str, category: str, scope: OutputScope, fmt: OutputFormat, pattern: str
    ) -> ReviewedOutput:
        return ReviewedOutput(
            key=key,
            title=key,
            description=f"{key}.",
            category=category,
            stage="reporting" if key == "multiqc_report" else None,
            formats=(fmt,),
            scopes=(scope,),
            entity_types=(OutputEntityType.FILE,),
            path_patterns=(pattern,),
        )

    rendered = render_outputs(
        OutputContractInput(
            pipeline=OutputPipeline(
                id="rnaquant",
                name="rnaquant",
                version="1.2.0",
                repository_url="https://github.com/org/rnaquant",
            ),
            schema_version="1.0.0",
            outputs=(
                output(
                    "multiqc_report",
                    "quality_control",
                    OutputScope.JOB,
                    OutputFormat.HTML,
                    r"^multiqc/multiqc_report\.html$",
                ),
                output(
                    "gene_counts",
                    "quantification",
                    OutputScope.SAMPLE,
                    OutputFormat.TSV,
                    r"^quant/{sample}/counts\.tsv$",
                ),
                output(
                    "read_qc",
                    "quality_control",
                    OutputScope.RUN,
                    OutputFormat.JSON,
                    r"^qc/{sample}/{run}\.json$",
                ),
            ),
        )
    )
    page = (ROOT / "docs" / "schemas" / "analysis-output.md").read_text(
        encoding="utf-8"
    )
    example = json.loads(re.findall(r"```json\n(.*?)```", page, re.DOTALL)[0])
    errors = list(Draft7Validator(rendered.schema_document).iter_errors(example))
    assert not errors, [error.message for error in errors]


def test_companion_reference_lists_every_lock_and_catalogue_key() -> None:
    page = (ROOT / "docs" / "schemas" / "companion-files.md").read_text(
        encoding="utf-8"
    )
    bundle = ROOT / "tests" / "fixtures" / "example-0.3.0" / "repository" / "splice"
    lock = json.loads((bundle / "nf-splice.lock.json").read_text(encoding="utf-8"))
    catalogue = yaml.safe_load((bundle / "outputs.yaml").read_text(encoding="utf-8"))
    for key in [*lock, *catalogue]:
        assert f"`{key}" in page, key
