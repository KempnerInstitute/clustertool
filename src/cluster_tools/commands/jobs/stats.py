"""jobs stats command."""

import click

from cluster_tools import process


@click.command("stats")
@click.argument("jobids", nargs=-1, required=True, metavar="JOBID...")
def stats(jobids: tuple[str, ...]) -> None:
    """Show utilization for one or more jobs (via jobstats).

    \b
    Use cases:
      - Check a job's CPU, memory, and GPU utilization.
      - Review the efficiency of a finished job.

    \b
    Inputs:
      JOBID...  One or more Slurm job ids (e.g. 1234567).
    """
    code = process.stream(["jobstats", *jobids])
    if code:
        raise SystemExit(code)
