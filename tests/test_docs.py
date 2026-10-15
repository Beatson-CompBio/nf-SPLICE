"""Docs stay truthful: commands exist, links resolve, references are current."""

from __future__ import annotations

import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

import typer

from nf_splice.cli import app

ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]
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
    for path in [*DOCUMENTS, *sorted((ROOT / "docs" / "schemas").rglob("*.md"))]:
        if path.name in {"GLOSSARY.md", "ARCHITECTURE_DECISIONS.md"}:
            continue
        assert "manifest" not in path.read_text(encoding="utf-8").lower(), path.name
