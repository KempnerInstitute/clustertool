"""jobs why command."""

import click

from cluster_tools import process
from cluster_tools.grouping import keywords


@keywords("pending", "waiting", "stuck", "blocked")
@click.command("why")
@click.argument("jobid")
def why(jobid: str) -> None:
    """Explain a job's priority and, if pending, why it is waiting.

    Prints the job state and pending reason (from squeue), then the priority
    factor breakdown (from sprio): fairshare, age, partition, QOS, and so on.

    \b
    Use cases:
      - Understand what is holding a pending job back.
      - Compare fairshare and age contributions to a job's priority.

    \b
    Inputs:
      JOBID  A Slurm job id.
    """
    reason = process.run(["squeue", "-j", jobid, "-h", "-o", "%T %r"]).strip()
    if reason:
        click.echo(f"State and reason: {reason}")
    code = process.stream(["sprio", "-j", jobid, "-l"])
    if code:
        raise SystemExit(code)
