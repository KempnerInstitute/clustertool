"""jobs cancel command."""

import os

import click

from clustertool import completion, process
from clustertool.grouping import keywords


@keywords("kill", "stop", "abort", "terminate")
@click.command("cancel")
@click.argument(
    "jobids", nargs=-1, metavar="[JOBID...]", shell_complete=completion.complete_job_ids
)
@click.option("--all", "all_jobs", is_flag=True, help="Cancel all of your jobs.")
@click.option("--pending", is_flag=True, help="Cancel all of your pending jobs.")
@click.option("-y", "--yes", is_flag=True, help="Skip the confirmation prompt.")
def cancel(jobids: tuple[str, ...], all_jobs: bool, pending: bool, yes: bool) -> None:
    """Cancel jobs (via scancel).

    Naming job ids cancels them immediately, exactly as scancel does. The bulk
    forms --all and --pending act on every job you own rather than a list you
    named, so they prompt for confirmation unless -y.

    \b
    Use cases:
      - Kill a specific job or list of jobs.
      - Clear all of your pending jobs at once.

    \b
    Inputs:
      JOBID...   One or more job ids to cancel.
      --all      Cancel every job you own.
      --pending  Cancel only your pending jobs.
      -y, --yes  Skip the confirmation prompt.
    """
    if jobids and (all_jobs or pending):
        raise click.UsageError("Give JOBIDs, or --all / --pending, not both.")
    if all_jobs and pending:
        raise click.UsageError("Give --all or --pending, not both.")
    if jobids:
        cmd = ["scancel", *jobids]
    elif all_jobs or pending:
        owner = os.environ.get("USER", "")
        if not owner:
            raise click.ClickException(
                "cannot tell whose jobs to cancel: $USER is not set. Name the JOBIDs instead"
            )
        scope = "pending jobs" if pending else "jobs"
        if not yes:
            click.confirm(f"Cancel every one of your {scope}?", abort=True)
        cmd = ["scancel", "-u", owner]
        if pending:
            cmd += ["-t", "PENDING"]
    else:
        raise click.UsageError("Give one or more JOBIDs, or --all / --pending.")
    if process.stream(cmd):
        raise click.ClickException("scancel failed")
