"""jobs hold command."""

import click

from clustertool import completion, jobaction, process
from clustertool.grouping import keywords


@keywords("block", "prevent", "unschedule")
@click.command("hold")
@click.argument(
    "jobids",
    nargs=-1,
    required=True,
    metavar="JOBID...",
    shell_complete=completion.complete_job_ids,
)
def hold(jobids: tuple[str, ...]) -> None:
    """Prevent pending jobs from starting (via scontrol hold).

    Held jobs stay in the queue but are not scheduled until released with
    'jobs release'. Holding a running job does not suspend or cancel it: per man
    scontrol it only sets the priority to 0, which keeps the job held if it is
    later requeued.

    A job owned by someone else is refused. man scontrol records an admin-hold
    rather than a user-hold when a privileged user holds a job, and its owner
    cannot lift that with 'jobs release', so a mistyped id would otherwise strand
    a stranger's job.

    \b
    Use cases:
      - Pause a pending job you are not ready to run.
      - Hold a set of jobs before adjusting them.

    \b
    Inputs:
      JOBID...  One or more Slurm job ids.
    """
    if any(not jobid.strip() for jobid in jobids):
        raise click.UsageError("JOBID may not be empty.")
    planned = jobaction.plan("hold", list(jobids))
    process.passthrough(planned.cmd, planned.failure)
