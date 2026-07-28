"""jobs setprio command."""

import click

from cluster_tools import process


@click.command("setprio")
@click.argument("jobid")
@click.argument("priority", type=int)
def setprio(jobid: str, priority: int) -> None:
    """Set a job's scheduling priority (via scontrol update). Operator only.

    Pins the job to the given priority, overriding fairshare until the job runs.

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
