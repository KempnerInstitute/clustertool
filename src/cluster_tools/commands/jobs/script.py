"""jobs script command."""

import click

from cluster_tools import process


@click.command("script")
@click.argument("jobid")
def script(jobid: str) -> None:
    """Print the batch script a job was submitted with (via sacct).

    \b
    Use cases:
      - Recover or reproduce exactly how a job was submitted.

    \b
    Inputs:
      JOBID  A Slurm job id.
    """
    code = process.stream(["sacct", "-j", jobid, "--batch"])
    if code:
        raise SystemExit(code)
