"""jobs scope command."""

import os
import pwd
import sys

import click

from clustertool import process
from clustertool.grouping import keywords


@keywords("efficiency", "profiling", "completed", "jobscope")
@click.command(
    "scope",
    context_settings={"ignore_unknown_options": True, "help_option_names": []},
)
@click.argument("args", nargs=-1, type=click.UNPROCESSED, metavar="[ARG]...")
def scope(args: tuple[str, ...]) -> None:
    """Report efficiency of completed jobs, via the bundled jobscope tool.

    All arguments are forwarded to jobscope unchanged, so every jobscope view
    and selector is available. Run 'clustertool jobs scope --help' for the
    full option list (that help is produced by jobscope itself).

    \b
    Most useful:
      jobs scope -D 3         your jobs from the last 3 days
      jobs scope 1234567      one job by id
      jobs scope --cgpu -D 2  CPU and GPU summary, fully offline
      jobs scope describe     explain every column and metric

    For live jobs use 'gpu monitor-job'; jobscope reports completed jobs.

    Where neither a user nor a job id or subcommand is given, yours is taken from
    your uid and passed on explicitly, since the bundled tool would otherwise
    read $USER, which the caller can set and a batch script or an su session can
    leave stale.

    A window wider than the site's slurmdbd MaxQueryTimeRange is refused by the
    database for anyone below operator; man slurmdbd.conf exempts operators, so
    this succeeds for an admin and fails for the person it was written for.
    """
    forwarded = list(args)
    named = any(arg == "-u" or arg.startswith(("-u", "--user")) for arg in forwarded)
    positional = bool(forwarded) and not forwarded[0].startswith("-")
    if not named and not positional:
        forwarded = ["-u", pwd.getpwuid(os.getuid()).pw_name, *forwarded]
    code = process.stream([sys.executable, "-m", "jobscope", *forwarded])
    if code:
        raise SystemExit(code)
