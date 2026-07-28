"""jobs cancel command."""

import os

import click

from cluster_tools import process
from cluster_tools.grouping import keywords


@keywords("kill", "stop", "abort", "terminate")
@click.command("cancel")
@click.argument("jobids", nargs=-1, metavar="[JOBID...]")
@click.option("--all", "all_jobs", is_flag=True, help="Cancel all of your jobs.")
@click.option("--pending", is_flag=True, help="Cancel all of your pending jobs.")
def cancel(jobids: tuple[str, ...], all_jobs: bool, pending: bool) -> None:
    """Cancel jobs (via scancel).

    Pass explicit job ids, or use --all / --pending to cancel your own jobs in
    bulk. This is a direct wrapper: it cancels immediately, exactly as scancel
    does.

    \b
    Use cases:
      - Kill a specific job or list of jobs.
      - Clear all of your pending jobs at once.

    \b
    Inputs:
      JOBID...   One or more job ids to cancel.
      --all      Cancel every job you own.
      --pending  Cancel only your pending jobs.
    """
    if jobids:
        cmd = ["scancel", *jobids]
    elif all_jobs or pending:
        cmd = ["scancel", "-u", os.environ.get("USER", "")]
        if pending:
            cmd += ["-t", "PENDING"]
    else:
        raise click.UsageError("Give one or more JOBIDs, or --all / --pending.")
    code = process.stream(cmd)
    if code:
        raise SystemExit(code)
