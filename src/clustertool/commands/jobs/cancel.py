"""jobs cancel command."""

import getpass

import click

from clustertool import completion, process, slurm
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
        unknown = [jid for jid in jobids if not slurm.job_exists(jid)]
        if unknown:
            raise click.ClickException(
                f"no such job: {', '.join(unknown)}. scancel treats an unknown id as "
                "nothing to do, so this would have exited cleanly having cancelled nothing"
            )
        cmd = ["scancel", *jobids]
    elif all_jobs or pending:
        owner = getpass.getuser()
        scope = "pending jobs" if pending else "jobs"
        counts = slurm.job_state_counts(owner, pending_only=pending)
        if not counts:
            click.echo(f"You have no {scope} to cancel.")
            return
        total = sum(counts.values())
        breakdown = ", ".join(f"{n} {state.lower()}" for state, n in sorted(counts.items()))
        if not yes:
            click.confirm(f"Cancel all {total} of your {scope} ({breakdown})?", abort=True)
        cmd = ["scancel", "-u", owner]
        if pending:
            cmd += ["-t", "PENDING"]
    else:
        raise click.UsageError("Give one or more JOBIDs, or --all / --pending.")
    if process.stream(cmd):
        raise click.ClickException("scancel failed")
