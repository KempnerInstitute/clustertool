"""jobs history command."""

import os
import pwd

import click

from clustertool import process, slurm
from clustertool.grouping import keywords

_FORMAT = "JobID,JobName%40,Partition%30,State%20,Elapsed,NodeList%40"


@keywords("past", "finished", "completed", "recent")
@click.command("history")
@click.option(
    "-d",
    "--days",
    type=click.IntRange(min=1),
    default=7,
    show_default=True,
    help="How many days back to list.",
)
@click.option("-u", "--user", default=None, help="User whose history to show (default: you).")
def history(days: int, user: str | None) -> None:
    """List your recent jobs (via sacct).

    Lists one row per job allocation, so it covers jobs that are still running as
    well as finished ones. Peak memory is a per-step figure that a
    per-allocation listing cannot carry, so use 'jobs debug JOBID' or
    'jobs scope' for that.

    \b
    Use cases:
      - Review what ran over the last few days and how it ended.
      - Find a past job's id, runtime, or nodes.

    \b
    Inputs:
      -d, --days  How many days back to include (default 7).
      -u, --user  User whose history to show (default: current user).
    """
    target = user or pwd.getpwuid(os.getuid()).pw_name
    if not slurm.user_exists(target):
        raise click.ClickException(f"no such user on this host: {target}")
    cmd = ["sacct", "-u", target, "-S", f"now-{days}days", "-X", "--format", _FORMAT]
    code, out, err = process.probe(cmd)
    if code == 0:
        click.echo(out.rstrip())
        return
    if "too wide" in (out + err).lower() or "query" in (out + err).lower():
        raise click.ClickException(
            f"slurmdbd refused a {days}-day query: {err.strip() or out.strip()}. Sites cap "
            "the span with MaxQueryTimeRange in slurmdbd.conf, and man slurmdbd.conf "
            "exempts only operators, so ask for fewer days"
        )
    raise click.ClickException(f"'sacct' failed: {err.strip() or out.strip() or code}")
