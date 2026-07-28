"""jobs history command."""

import os

import click

from cluster_tools import process
from cluster_tools.grouping import keywords

_FORMAT = "JobID,JobName%25,Partition,State,Elapsed,MaxRSS,NodeList"


@keywords("past", "finished", "completed", "recent")
@click.command("history")
@click.option(
    "-d", "--days", type=int, default=7, show_default=True, help="How many days back to list."
)
@click.option("-u", "--user", default=None, help="User whose history to show (default: you).")
def history(days: int, user: str | None) -> None:
    """List your recent finished jobs (via sacct).

    \b
    Use cases:
      - Review what ran over the last few days and how it ended.
      - Find a past job's id, runtime, or peak memory.

    \b
    Inputs:
      -d, --days  How many days back to include (default 7).
      -u, --user  User whose history to show (default: current user).
    """
    user = user or os.environ.get("USER", "")
    cmd = ["sacct", "-u", user, "-S", f"now-{days}days", "-X", "--format", _FORMAT]
    code = process.stream(cmd)
    if code:
        raise SystemExit(code)
