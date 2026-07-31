"""Dry-run/execute gate shared by the qos write commands.

Write commands build a list of sacctmgr argv, then call apply(). By default
nothing runs: each command is printed with a DRY tag. With execute set, the user
is asked to confirm (unless assume_yes), then each command is printed with an
EXEC tag and run. Every sacctmgr call carries -i, so the app's gate, not
sacctmgr, is what protects against accidental changes.
"""

import shlex
import sys

import click

from cluster_tools import process


def apply(
    plan: list[list[str]],
    execute: bool,
    assume_yes: bool,
    summary: str,
) -> int:
    """Print the planned commands and, when executing, confirm then run them.

    Returns the number of commands that failed (always 0 in a dry run).
    """
    if not execute:
        for cmd in plan:
            click.echo(f"[DRY ] {shlex.join(cmd)}")
        click.echo("Dry run - nothing changed. Re-run with --execute to apply.")
        return 0
    if not assume_yes:
        if not sys.stdin.isatty():
            raise click.ClickException(
                "stdin is not a terminal; re-run with --yes to apply without confirmation"
            )
        click.confirm(summary, abort=True)
    failures = 0
    for cmd in plan:
        click.echo(f"[EXEC] {shlex.join(cmd)}")
        code, _out, err = process.probe(cmd)
        if code != 0:
            failures += 1
            click.echo(f"[WARN] command failed (exit {code}): {err.strip()}", err=True)
            break
    return failures
