"""Command-line entry point for nf-splice."""

import typer

from nf_splice import __version__

app = typer.Typer(
    name="nf-splice",
    help="Author and maintain a SPLICE integration layer.",
    add_completion=False,
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"nf-splice {__version__}")
        raise typer.Exit


@app.callback()
def cli(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the nf-splice version and exit.",
    ),
) -> None:
    """Author and maintain a SPLICE integration layer."""


def main() -> None:
    """Run the nf-splice command-line interface."""
    app()
