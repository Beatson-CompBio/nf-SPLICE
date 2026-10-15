"""Reserved SPLICE vocabulary audit (`manifest`) across owned surfaces."""

from __future__ import annotations

import ast
import json
from pathlib import Path

from typer.testing import CliRunner

from nf_splice.cli import app
from nf_splice.contracts import families, meta_schema
from nf_splice.inspectors import inspect_pipeline_identity
from nf_splice.vocabulary import reserved_terms_in

SOURCE = Path(__file__).resolve().parents[1] / "src" / "nf_splice"
# The only module permitted to contain the literal upstream Nextflow token.
_NEXTFLOW_PARSER = SOURCE / "inspectors" / "identity.py"
runner = CliRunner()


def _identifiers(tree: ast.AST) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.append(node.id)
        elif isinstance(node, ast.Attribute):
            names.append(node.attr)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            names.append(node.name)
        elif isinstance(node, ast.arg):
            names.append(node.arg)
        elif isinstance(node, ast.alias):
            names.append(node.asname or node.name)
    return names


def test_no_splice_owned_python_identifier_uses_the_reserved_word() -> None:
    for path in sorted(SOURCE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        offenders = [name for name in _identifiers(tree) if reserved_terms_in(name)]
        assert offenders == [], (path, offenders)


def test_reserved_word_strings_occur_only_in_the_nextflow_parser() -> None:
    for path in sorted(SOURCE.rglob("*.py")):
        if path in {_NEXTFLOW_PARSER, SOURCE / "vocabulary.py"}:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        literals = [
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        ]
        offenders = [value for value in literals if reserved_terms_in(value)]
        assert offenders == [], (path, offenders)


def test_contract_definitions_and_registry_avoid_the_reserved_word() -> None:
    for item in families():
        assert not reserved_terms_in(json.dumps(meta_schema(item.id)))
        assert not reserved_terms_in(item.id + item.key + item.title)


def test_cli_help_never_uses_the_reserved_word() -> None:
    commands = [
        [],
        ["schema"],
        ["analysis-output"],
        ["build"],
        ["configure"],
        ["plan"],
        ["validate"],
        ["init"],
    ]
    for command in commands:
        result = runner.invoke(app, [*command, "--help"])
        assert result.exit_code == 0, (command, result.output)
        assert not reserved_terms_in(result.output), command


def test_upstream_nextflow_metadata_scope_is_still_parsed(tmp_path: Path) -> None:
    (tmp_path / "nextflow.config").write_text(
        "manifest {\n    name = 'block-name'\n    version = '2.0.0'\n}\n"
        "manifest.homePage = 'https://github.com/org/block-name'\n",
        encoding="utf-8",
    )
    values = {
        (item.field, item.value) for item in inspect_pipeline_identity(tmp_path).values
    }
    assert ("name", "block-name") in values
    assert ("version", "2.0.0") in values
    assert ("repository_url", "https://github.com/org/block-name") in values
