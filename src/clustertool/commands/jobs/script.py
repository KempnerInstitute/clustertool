"""jobs script command."""

import click

from clustertool import completion, process
from clustertool.grouping import keywords


def _script_body(out: str) -> str:
    """Return the script from sacct --batch-script, without its two-line header.

    sacct prefixes the script with a title and a rule, so the sentinel NONE it
    prints for a job with no stored script is never the whole output.
    """
    lines = out.splitlines()
    for index, line in enumerate(lines):
        if set(line.strip()) == {"-"} and line.strip():
            body = "\n".join(lines[index + 1 :]).strip("\n")
            return "" if body.strip() in ("", "NONE") else body
    body = out.strip("\n")
    return "" if body.strip() in ("", "NONE") else body


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
    body = _script_body(out) if code == 0 else ""
    if body:
        click.echo(body)
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
