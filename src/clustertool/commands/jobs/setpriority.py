"""jobs set-priority command."""

import click

from clustertool import completion, process
from clustertool.grouping import admin, keywords


@admin
@keywords("priority", "boost", "bump", "pin", "setprio")
@click.command("set-priority")
@click.argument("jobid", shell_complete=completion.complete_job_ids)
@click.argument("priority", type=int)
@click.option("-y", "--yes", is_flag=True, help="Skip the confirmation prompt.")
def set_priority(jobid: str, priority: int, yes: bool) -> None:
    """Set a job's scheduling priority (via scontrol update). Operator or admin.

    Per man scontrol, once a privileged user sets a priority explicitly it is
    fixed and the priority plugin stops modifying it; hold and then release the
    job to hand it back to the multifactor plugin. A priority of zero holds the
    job. man scontrol gives the requirement as Privileged or Effective Owner: an
    AdminLevel of Operator or Administrator, root or SlurmUser, or the job's own
    owner or an account coordinator, who can only lower a priority. To
    deprioritize your own job, raise its Nice value instead. Prompts for
    confirmation unless -y.

    \b
    Use cases:
      - Boost a specific job ahead of the queue.

    \b
    Inputs:
      JOBID      A Slurm job id.
      PRIORITY   The integer priority to set.
      -y, --yes  Skip the confirmation prompt.
    """
    if not yes:
        click.confirm(f"Set priority of job {jobid} to {priority}?", abort=True)
    process.passthrough(
        ["scontrol", "update", f"jobid={jobid}", f"priority={priority}"],
        f"failed to set the priority of job {jobid}",
    )
