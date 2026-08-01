"""jobs scope command."""

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
    """
    code = process.stream([sys.executable, "-m", "jobscope", *args])
    if code:
        raise SystemExit(code)
