"""jobs script command."""

import click

from clustertool import completion, process
from clustertool.grouping import keywords

_NO_SCRIPT = "Job script not specified"
_DENIED = "Access/permission denied"


def _script_body(out: str) -> tuple[str, str]:
    """Return (status, script) from sacct --batch-script output.

    sacct heads each record with a title and a rule, and answers a whole array
    with one such block per element, so only the first block is a script: the
    later titles would otherwise be read as script lines. Every element of an
    array shares one script. Status is 'script' when a script was found, 'none'
    when the record exists but sacct printed its NONE sentinel, and 'absent' when
    there was no record at all.
    """
    lines = out.splitlines()
    rules = [i for i, line in enumerate(lines) if line.strip() and set(line.strip()) == {"-"}]
    if not rules:
        body = out.strip("\n")
        if not body.strip():
            return "absent", ""
        return ("none", "") if body.strip() == "NONE" else ("script", body)
    end = rules[1] - 1 if len(rules) > 1 else len(lines)
    body = "\n".join(lines[rules[0] + 1 : end]).strip("\n")
    if not body.strip():
        return "absent", ""
    return ("none", "") if body.strip() == "NONE" else ("script", body)


@keywords("sbatch", "submission", "batch", "source")
@click.command("script")
@click.argument("jobid", shell_complete=completion.complete_job_ids)
def script(jobid: str) -> None:
    """Print the batch script a job was submitted with.

    Reads the accounting record first, which needs the cluster to store scripts
    (AccountingStoreFlags=job_script in slurm.conf), and falls back to asking the
    controller. The controller still holds the script for a queued or running
    job, including an array element that has not started and so has no accounting
    record yet. Only the job's owner, an account coordinator, or a Slurm admin can
    read a script, per man scontrol.

    \b
    Use cases:
      - Recover or reproduce exactly how a job was submitted.

    \b
    Inputs:
      JOBID  A Slurm job id, or an array element such as 12345_0.
    """
    code, out, _ = process.probe(["sacct", "-j", jobid, "--batch-script"])
    status, body = _script_body(out) if code == 0 else ("absent", "")
    if status == "script":
        click.echo(body)
        return

    code, out, err = process.probe(["scontrol", "write", "batch_script", jobid, "-"])
    if code == 0 and out.strip():
        click.echo(out.rstrip())
        return

    detail = err.strip()
    if status == "none" or _NO_SCRIPT in detail:
        raise click.ClickException(
            f"job {jobid} ran without a batch script: it was an interactive srun or "
            "salloc allocation, or the cluster was not storing scripts when it was "
            "submitted (AccountingStoreFlags=job_script)"
        )
    if _DENIED in detail:
        raise click.ClickException(
            f"job {jobid} belongs to another user: Slurm lets only the owner, an "
            "account coordinator, or an admin read a batch script"
        )
    raise click.ClickException(
        f"no job {jobid} on this cluster, or it has aged out of both the scheduler "
        f"and accounting. Slurm said: {detail or 'nothing'}"
    )
