"""jobs set-priority command."""

import os
import pwd

import click

from clustertool import completion, process, slurm
from clustertool.grouping import admin, keywords


@admin
@keywords("priority", "boost", "bump", "pin", "setprio")
@click.command("set-priority")
@click.argument("jobid", shell_complete=completion.complete_job_ids)
@click.argument("priority", type=click.IntRange(0, 4294967293))
@click.option("-y", "--yes", is_flag=True, help="Skip the confirmation prompt.")
def set_priority(jobid: str, priority: int, yes: bool) -> None:
    """Set a job's scheduling priority (via scontrol update). Operator or admin.

    Per man scontrol, once a privileged user sets a priority explicitly it is
    fixed and the priority plugin stops modifying it; hold and then release the
    job to hand it back to the multifactor plugin. A priority of zero holds the
    job. man scontrol gives the requirement as Privileged or Effective Owner: an
    AdminLevel of Operator or Administrator, root or SlurmUser, or the job's own
    owner or an account coordinator, who can only lower a priority and whose
    lowered value the priority plugin may still manage. A priority of zero holds
    the job, and from a privileged user that is an admin-hold; 'jobs release'
    lifts it, and so does setting a non-zero priority. Priority orders pending
    jobs, so setting it on a running job has no effect on that run. To
    deprioritize your own job, raise its Nice value with scontrol update
    jobid=X nice=N.

    The id must name one job. man scontrol reads JobId as a comma-separated list,
    and an array's own id as every element of it, so a list would be held or
    boosted wholesale behind a prompt naming one job. The owner is checked for
    the same reason 'jobs hold' checks it: a mistyped but valid id would
    otherwise strand a stranger's job. Prompts for confirmation unless -y.

    \b
    Use cases:
      - Boost a specific job ahead of the queue.

    \b
    Inputs:
      JOBID      A Slurm job id.
      PRIORITY   The integer priority to set.
      -y, --yes  Skip the confirmation prompt.
    """
    if not jobid.strip():
        raise click.ClickException("give a job id")
    owner = slurm.job_owner(jobid)
    me = pwd.getpwuid(os.getuid()).pw_name
    if owner and owner != me:
        raise click.ClickException(
            f"job {jobid} belongs to {owner}, not you. Setting a priority on someone "
            "else's job is an admin action; name your own job, or use scontrol "
            "directly if you mean to"
        )
    if not yes:
        summary = f"Set priority of job {jobid} to {priority}?"
        if priority == 0:
            summary = (
                f"Set priority of job {jobid} to 0? That holds the job; "
                "'jobs release' or a non-zero priority lifts it"
            )
        click.confirm(summary, abort=True)
    process.passthrough(
        ["scontrol", "update", f"jobid={jobid}", f"priority={priority}"],
        f"failed to set the priority of job {jobid}",
    )
