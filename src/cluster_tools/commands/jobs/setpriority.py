"""jobs set-priority command."""

import click

from cluster_tools import completion, process
from cluster_tools.grouping import admin, keywords


@admin
@keywords("priority", "boost", "bump", "pin", "setprio")
@click.command("set-priority")
@click.argument("jobid", shell_complete=completion.complete_job_ids)
@click.argument("priority", type=int)
def set_priority(jobid: str, priority: int) -> None:
    """Set a job's scheduling priority (via scontrol update). Operator only.

    For an operator the priority is fixed, overriding fairshare until the job
    runs. A job's own owner can only lower it, and the multifactor plugin keeps
    recomputing the value; raise Nice instead to deprioritize your own job.

    \b
    Use cases:
      - Boost a specific job ahead of the queue.

    \b
    Inputs:
      JOBID     A Slurm job id.
      PRIORITY  The integer priority to set.
    """
    code = process.stream(["scontrol", "update", f"jobid={jobid}", f"priority={priority}"])
    if code:
        raise SystemExit(code)
