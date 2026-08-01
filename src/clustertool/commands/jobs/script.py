"""jobs script command."""

import click

from clustertool import completion, process
from clustertool.grouping import keywords


@keywords("sbatch", "submission", "batch", "source")
@click.command("script")
@click.argument("jobid", shell_complete=completion.complete_job_ids)
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
