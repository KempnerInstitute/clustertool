"""jobs cancel command."""

import os

import click

from cluster_tools import process


@click.command("cancel")
@click.argument("jobids", nargs=-1, metavar="[JOBID...]")
@click.option("--all", "all_jobs", is_flag=True, help="Cancel all of your jobs.")
@click.option("--pending", is_flag=True, help="Cancel all of your pending jobs.")
@click.option("-y", "--yes", is_flag=True, help="Do not prompt for confirmation.")
def cancel(jobids: tuple[str, ...], all_jobs: bool, pending: bool, yes: bool) -> None:
    """Cancel jobs (via scancel).

    Pass explicit job ids, or use --all / --pending to cancel your own jobs in
    bulk (which prompt for confirmation unless --yes is given).

    \b
    Use cases:
      - Kill a specific job or list of jobs.
      - Clear all of your pending jobs at once.

    \b
    Inputs:
      JOBID...    One or more job ids to cancel.
      --all       Cancel every job you own.
      --pending   Cancel only your pending jobs.
      -y, --yes   Skip the confirmation prompt for bulk cancels.
    """
    user = os.environ.get("USER", "")
    if jobids:
        cmd = ["scancel", *jobids]
    elif all_jobs or pending:
        target = "your pending jobs" if pending else "all of your jobs"
        if not yes:
            click.confirm(f"Cancel {target} ({user})?", abort=True)
        cmd = ["scancel", "-u", user]
        if pending:
            cmd += ["-t", "PENDING"]
    else:
        raise click.UsageError("Give one or more JOBIDs, or --all / --pending.")
    code = process.stream(cmd)
    if code:
        raise SystemExit(code)
