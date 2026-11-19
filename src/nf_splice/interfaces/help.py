"""Command-line help organised around what a researcher is doing.

The root ``--help`` shows the starting points and the everyday commands;
``--help-all`` lists every command, grouped, with each group's subcommands.
Command-specific ``--help`` stays complete. Help is plain text: Click's
formatter wraps it to the terminal (at most :data:`MAX_WIDTH` columns), so it
never draws wide panels and redirects without escape sequences.
"""

from __future__ import annotations

import textwrap
from collections.abc import Iterable, Sequence
from typing import Any

import typer
from typer.core import TyperGroup

from nf_splice import __version__

#: Widest help text, whatever the terminal width.
MAX_WIDTH = 100
#: Shown in the root view and as the first section of ``--help-all``.
STARTING_POINTS = (
    ("nf-splice", "Start or resume interactively (in a terminal)"),
    ("nf-splice source prepare PATH", "Make a safe working copy and open it"),
    ("nf-splice tui", "Open the workspace for this working copy"),
)
#: The everyday commands in the root view, with concise summaries.
EVERYDAY: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    (
        "Authoring and validation",
        (
            ("init", "Create the editable drafts in a working copy"),
            ("status", "Show integration progress"),
            ("plan", "List what still blocks publication"),
            ("build", "Publish validated drafts to splice/"),
            ("validate", "Check the published bundle and ingestion readiness"),
            ("export", "Write a verified ZIP of the bundle or pipeline"),
        ),
    ),
    (
        "AI integration",
        (
            ("provider", "Set up, check and test an AI provider"),
            ("ask", "Ask AI a read-only question"),
            ("session", "Run AI-assisted or autonomous integration"),
        ),
    ),
)
#: Every top-level command, by task, for ``--help-all``.
SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Working copy and workspace", ("source", "tui")),
    (
        "Authoring and validation",
        (
            "init",
            "configure",
            "status",
            "plan",
            "draft",
            "build",
            "validate",
            "assess",
            "export",
            "git",
        ),
    ),
    ("AI integration", ("provider", "ask", "session", "skills")),
    (
        "Reference and diagnostics",
        (
            "inspect",
            "catalogue",
            "schema",
            "preview",
            "containers",
            "analysis-output",
            "audit",
            "workspace",
            "migrate",
        ),
    ),
)
TAGLINE = "Prepare, integrate and validate Nextflow pipelines for the SPLICE platform."
HELP_ALL_KEY = "nf_splice_help_all"


def wrap(text: str, width: int, indent: str = "", subsequent: str = "") -> str:
    """Wrap paragraphs without splitting hyphenated words or paths."""
    wrapper = textwrap.TextWrapper(
        max(width, 10),
        initial_indent=indent,
        subsequent_indent=subsequent or indent,
        break_on_hyphens=False,
    )
    paragraphs = [
        " ".join(line.strip() for line in block.splitlines())
        for block in textwrap.dedent(text.expandtabs()).split("\n\n")
        if block.strip()
    ]
    return "\n\n".join(wrapper.fill(item) for item in paragraphs)


#: Typer ships its own copy of Click; its formatter is the one to extend.
_Formatter: Any = typer.Context.formatter_class


class HelpFormatter(_Formatter):  # type: ignore[misc]
    """Click's plain formatter, wrapping without breaking at hyphens."""

    def write_text(self, text: str) -> None:
        self.write(wrap(text, self.width, " " * self.current_indent) + "\n")

    def write_dl(
        self,
        rows: Iterable[tuple[str, str]],
        col_max: int = 30,
        col_spacing: int = 2,
    ) -> None:
        rows = list(rows)
        first_col = min(max(len(first) for first, _ in rows), col_max) + col_spacing
        margin = " " * (first_col + self.current_indent)
        for first, second in rows:
            self.write(f"{'':>{self.current_indent}}{first}")
            if not second:
                self.write("\n")
                continue
            if len(first) <= first_col - col_spacing:
                self.write(" " * (first_col - len(first)))
            else:
                self.write("\n" + margin)
            lines = wrap(second, self.width - first_col - self.current_indent)
            self.write(lines.replace("\n", "\n" + margin) + "\n")


class Context(typer.Context):
    """Every nf-splice command formats its help with :class:`HelpFormatter`."""

    formatter_class = HelpFormatter


class Group(TyperGroup):
    """A command group whose commands share nf-splice's help formatting."""

    context_class = Context

    def get_command(self, ctx: Any, cmd_name: str) -> Any:
        command = super().get_command(ctx, cmd_name)
        if command is not None:
            command.context_class = Context
        return command

    def format_commands(self, ctx: Any, formatter: Any) -> None:
        rows = [
            (name, command.get_short_help_str(10_000))
            for name, command in _commands(self, ctx, self.list_commands(ctx))
        ]
        if rows:
            _write_rows(formatter, "Commands", rows)


def sectioned() -> set[str]:
    """Every command name the full reference places in a section."""
    return {name for _title, names in SECTIONS for name in names}


def _write_rows(formatter: Any, title: str, rows: Sequence[tuple[str, str]]) -> None:
    with formatter.section(title):
        formatter.write_dl(list(rows), col_max=32)


def _summary(command: Any, limit: int) -> str:
    text = str(command.get_short_help_str(limit)).rstrip(".")
    if isinstance(command, TyperGroup):
        context = Context(command)
        names = [
            name
            for name in command.list_commands(context)
            if not getattr(command.get_command(context, name), "hidden", False)
        ]
        if names:
            text += ". Commands: " + ", ".join(names)
    return text


def _commands(
    group: TyperGroup, context: Any, names: Iterable[str]
) -> list[tuple[str, Any]]:
    found = []
    for name in names:
        command = group.get_command(context, name)
        if command is not None and not command.hidden:
            found.append((name, command))
    return found


class RootGroup(Group):
    """The ``nf-splice`` group, with task-oriented root help."""

    def format_help(self, ctx: Any, formatter: Any) -> None:
        full = bool(ctx.meta.get(HELP_ALL_KEY))
        formatter.write_text(f"nf-SPLICE {__version__} | Nextflow Integration Toolkit")
        formatter.write_paragraph()
        formatter.write_text(TAGLINE)
        formatter.write_paragraph()
        self.format_usage(ctx, formatter)
        _write_rows(formatter, "Getting started", STARTING_POINTS)
        if full:
            for title, names in SECTIONS:
                rows = [
                    (name, _summary(command, 10_000))
                    for name, command in _commands(self, ctx, names)
                ]
                if rows:
                    _write_rows(formatter, title, rows)
            leftover = sorted(set(self.list_commands(ctx)) - sectioned() - {"help"})
            rows = [
                (name, _summary(command, 10_000))
                for name, command in _commands(self, ctx, leftover)
            ]
            if rows:
                _write_rows(formatter, "Other commands", rows)
        else:
            for title, entries in EVERYDAY:
                _write_rows(formatter, title, entries)
        self.format_options(ctx, formatter)
        formatter.write_paragraph()
        formatter.write_text(
            "Run 'nf-splice COMMAND --help' for a command's options."
            if full
            else "Run 'nf-splice --help-all' for every command, and "
            "'nf-splice COMMAND --help' for a command's options."
        )

    def format_options(self, ctx: Any, formatter: Any) -> None:
        rows: list[Any] = []
        for parameter in self.get_params(ctx):
            record = parameter.get_help_record(ctx)
            if record is not None:
                rows.append(record)
        if rows:
            _write_rows(formatter, "Options", rows)
