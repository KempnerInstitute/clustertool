"""jobs script command."""

import click

from clustertool import completion, process
from clustertool.grouping import keywords


@keywords("sbatch", "submission", "batch", "source")
@click.command("script")
@click.argument("jobid", shell_complete=completion.complete_job_ids)
def script(jobid: str) -> None:
    """Print the batch script a job was submitted with.

    Reads the accounting record first, which needs the cluster to store scripts
    (AccountingStoreFlags=job_script in slurm.conf), and falls back to asking the
    controller. The controller still holds the script for a queued or running
    job, including an array element that has not started and so has no accounting
    record yet.

    \b
    Use cases:
      - Recover or reproduce exactly how a job was submitted.

    \b
    Inputs:
      JOBID  A Slurm job id, or an array element such as 12345_0.
    """
    code, out, _ = process.probe(["sacct", "-j", jobid, "--batch-script"])
    if code == 0 and out.strip() and out.strip() != "NONE":
        click.echo(out.rstrip())
        return
    code, out, err = process.probe(["scontrol", "write", "batch_script", jobid, "-"])
    if code == 0 and out.strip():
        click.echo(out.rstrip())
        return
    raise click.ClickException(
        f"no batch script for job {jobid}: it may not exist, may belong to another "
        "user, may have been an interactive job, or the cluster may not store "
        f"scripts. Slurm said: {err.strip() or 'nothing'}"
    )
