"""jobs cancel command."""

import os
import pwd

import click

from clustertool import completion, jobaction, process, slurm
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

    Naming job ids cancels them immediately. A job owned by someone else is
    refused: man scancel lets an operator, admin or account coordinator signal
    another user's job, so without this check a mistyped digit would kill a
    stranger's work without a prompt. The bulk forms --all and --pending act on
    every job the calling account owns rather than a list you named, so they
    prompt for confirmation unless -y, and their count is of array elements,
    which is what scancel acts on.

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
    me = pwd.getpwuid(os.getuid()).pw_name
    if jobids:
        cmd = jobaction.plan("cancel", list(jobids)).cmd
    elif all_jobs or pending:
        scope = "pending jobs" if pending else "jobs"
        counts = slurm.job_state_counts(me, pending_only=pending)
        if not counts:
            click.echo(f"{me} has no {scope} to cancel.")
            return
        total = sum(counts.values())
        breakdown = ", ".join(f"{n} {state.lower()}" for state, n in sorted(counts.items()))
        if not yes:
            click.confirm(f"Cancel all {total} {scope} owned by {me} ({breakdown})?", abort=True)
        cmd = ["scancel", "-u", me]
        if pending:
            cmd += ["-t", "PENDING"]
    else:
        raise click.UsageError("Give one or more JOBIDs, or --all / --pending.")
    process.passthrough(cmd, "scancel failed")
