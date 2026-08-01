"""completion command."""

import click

from clustertool import completion as setup
from clustertool.grouping import keywords


@keywords("autocomplete", "tab", "bash", "zsh", "fish", "complete")
@click.command("completion")
@click.argument("shell", type=click.Choice(setup.SHELLS), required=False)
@click.option("--install", is_flag=True, help="Append the setup line to your shell startup file.")
def completion(shell: str | None, install: bool) -> None:
    """Set up tab completion for clustertool (bash, zsh, fish).

    Prints the line that enables completion for your shell; with --install it
    appends that line to your shell startup file. Restart your shell, or source
    the file, afterward. Completion then suggests subcommands and live values
    such as your job IDs, account names, and partition names.

    \b
    Use cases:
      - Turn on tab completion the first time you use clustertool.

    \b
    Inputs:
      SHELL      One of bash, zsh, fish (default: detected from $SHELL).
      --install  Append the setup line to the shell startup file.
    """
    shell = shell or setup.detect_shell()
    if not shell:
        raise click.UsageError("Could not detect your shell; pass bash, zsh, or fish.")
    line = setup.eval_line(shell)
    path = setup.rc_path(shell)
    if not install:
        click.echo(f"# Add this to {path}, or run: clustertool completion {shell} --install")
        click.echo(line)
        return
    if setup.ensure_line(path, line):
        click.echo(f"Added completion to {path}. Restart your shell or run: source {path}")
    else:
        click.echo(f"Completion already set up in {path}.")
