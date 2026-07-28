"""jobs hold command."""

import click

from cluster_tools import completion, process
from cluster_tools.grouping import keywords


@keywords("pause", "suspend", "block", "freeze")
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
    'jobs release'.

    \b
    Use cases:
      - Pause a pending job you are not ready to run.
      - Hold a set of jobs before adjusting them.

    \b
    Inputs:
      JOBID...  One or more Slurm job ids.
    """
    code = process.stream(["scontrol", "hold", ",".join(jobids)])
    if code:
        raise SystemExit(code)
