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

from clustertool import process

_DESTRUCTIVE_NOTE = (
    "{count} of these delete an association outright, which takes its fairshare, "
    "its limits and its recorded usage with it. Per man sacctmgr a recreated "
    "association does not get that usage back."
)


def _reason(out: str, err: str, code: int) -> str:
    """Return why a sacctmgr command failed, from whichever stream it used.

    sacctmgr writes its own diagnostics to stdout, including the ones a caller
    most needs: Nothing modified, Nothing new added, Nothing deleted, and the
    Unknown option and Use keyword where messages. Only the messages it prefixes
    with sacctmgr: error: go to stderr, so reading stderr alone left the caller
    with a bare exit code.
    """
    for stream in (err, out):
        line = " ".join(stream.split())
        if line:
            return line
    return f"exit {code}"


def apply(
    plan: list[list[str]],
    execute: bool,
    assume_yes: bool,
    summary: str,
) -> int:
    """Print the planned commands and, when executing, confirm then run them.

    Returns the number of commands that failed (always 0 in a dry run).
    """
    destructive = [cmd for cmd in plan if cmd[2:4] == ["delete", "user"]]
    if not execute:
        for cmd in plan:
            tag = "[DRY!]" if cmd in destructive else "[DRY ]"
            click.echo(f"{tag} {shlex.join(cmd)}")
        if destructive:
            click.echo(_DESTRUCTIVE_NOTE.format(count=len(destructive)))
        click.echo("Dry run - nothing changed. Re-run with --execute to apply.")
        return 0
    if destructive:
        click.echo(_DESTRUCTIVE_NOTE.format(count=len(destructive)))
    if not assume_yes:
        if not sys.stdin.isatty():
            raise click.ClickException(
                "stdin is not a terminal; re-run with --yes to apply without confirmation"
            )
        for cmd in plan:
            click.echo(f"[WILL] {shlex.join(cmd)}")
        click.confirm(summary, abort=True)
    failures = 0
    for index, cmd in enumerate(plan):
        click.echo(f"[EXEC] {shlex.join(cmd)}")
        code, out, err = process.probe(cmd)
        if code != 0:
            failures += 1
            click.echo(f"[WARN] command failed (exit {code}): {_reason(out, err, code)}", err=True)
            remaining = len(plan) - index - 1
            if remaining:
                click.echo(
                    f"[WARN] stopped after command {index + 1} of {len(plan)}; "
                    f"{remaining} not attempted, so the change is half applied",
                    err=True,
                )
            break
    return failures
