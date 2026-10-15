"""Generate docs/reference/cli.md from the installed command definitions.

python scripts/generate_cli_docs.py          # write
python scripts/generate_cli_docs.py --check  # fail if the reference is stale
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path
from typing import Any

import typer

from nf_splice.cli import app

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "docs" / "reference" / "cli.md"


def _cell(text: str) -> str:
    return " ".join(text.split()).replace("|", "\\|")


def _help(command: Any) -> str:
    return inspect.cleandoc(command.help or "").strip()


def _children(group: Any) -> list[tuple[str, Any]]:
    context = group.context_class(group)
    found = []
    for name in group.list_commands(context):
        child = group.get_command(context, name)
        if child is not None and not getattr(child, "hidden", False):
            found.append((name, child))
    return found


def _metavar(parameter: Any, command: Any) -> str:
    if getattr(parameter, "is_flag", False):
        return ""
    try:
        value = parameter.make_metavar(command.context_class(command))
    except TypeError:
        value = parameter.make_metavar()
    return f"`{value}`" if value else ""


def _default(parameter: Any) -> str:
    value = parameter.default
    if value in (None, False, "", (), []) or callable(value):
        return ""
    if isinstance(value, list | tuple):
        value = ", ".join(str(item) for item in value)
    return f"`{value}`"


def _parameters(command: Any) -> list[str]:
    arguments = [
        parameter
        for parameter in command.params
        if parameter.param_type_name == "argument"
    ]
    options = [
        parameter
        for parameter in command.params
        if parameter.param_type_name == "option"
        and not getattr(parameter, "hidden", False)
    ]
    lines: list[str] = []
    if arguments:
        lines += ["| Argument | Required | Description |", "| --- | --- | --- |"]
        for parameter in arguments:
            lines.append(
                f"| `{parameter.human_readable_name.upper()}` | "
                f"{'yes' if parameter.required else 'no'} | "
                f"{_cell(getattr(parameter, 'help', '') or '')} |"
            )
        lines.append("")
    if options:
        lines += [
            "| Option | Value | Default | Description |",
            "| --- | --- | --- | --- |",
        ]
        for parameter in options:
            names = ", ".join(f"`{name}`" for name in parameter.opts)
            lines.append(
                f"| {names} | {_metavar(parameter, command)} | "
                f"{_default(parameter)} | {_cell(parameter.help or '')} |"
            )
        lines.append("")
    return lines


def _usage(path: list[str], command: Any) -> str:
    pieces = ["nf-splice", *path]
    if any(item.param_type_name == "option" for item in command.params):
        pieces.append("[OPTIONS]")
    for parameter in command.params:
        if parameter.param_type_name == "argument":
            name = parameter.human_readable_name.upper()
            pieces.append(name if parameter.required else f"[{name}]")
    return " ".join(pieces)


def _commands(group: Any, path: list[str]) -> list[tuple[list[str], Any]]:
    found = []
    for name, child in _children(group):
        if hasattr(child, "get_command"):
            found.extend(_commands(child, [*path, name]))
        else:
            found.append(([*path, name], child))
    return found


def render() -> str:
    root = typer.main.get_command(app)
    commands = _commands(root, [])
    lines = [
        "# Command reference",
        "",
        "Every `nf-splice` command and option. This page is generated from the",
        "command definitions by `scripts/generate_cli_docs.py`; run any command",
        "with `--help` for the same information in the terminal. For",
        "step-by-step use, start with the [user guide](../USAGE.md).",
        "",
        "## Global options",
        "",
        "Global options go before the command name, for example",
        '`nf-splice --actor "Ada Lovelace" configure outputs`.',
        "",
        *_parameters(root),
        "## Commands",
        "",
        "| Command | Purpose |",
        "| --- | --- |",
    ]
    for path, command in commands:
        anchor = "nf-splice-" + "-".join(path)
        summary = _help(command).split("\n\n", 1)[0]
        name = f"nf-splice {' '.join(path)}"
        lines.append(f"| [`{name}`](#{anchor}) | {_cell(summary)} |")
    lines.append("")
    for path, command in commands:
        lines += [
            f"### nf-splice {' '.join(path)}",
            "",
            _help(command),
            "",
            "```text",
            _usage(path, command),
            "```",
            "",
            *_parameters(command),
        ]
    return "\n".join(lines).rstrip("\n") + "\n"


def main(argv: list[str]) -> int:
    text = render()
    if "--check" in argv:
        if not TARGET.is_file() or TARGET.read_text(encoding="utf-8") != text:
            print(f"{TARGET.relative_to(ROOT)} is stale", file=sys.stderr)
            return 1
        return 0
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
