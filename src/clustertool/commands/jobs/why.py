"""jobs why command."""

import click

from clustertool import completion, process
from clustertool.grouping import keywords


@keywords("pending", "waiting", "stuck", "blocked")
@click.command("why")
@click.argument("jobid", shell_complete=completion.complete_job_ids)
def why(jobid: str) -> None:
    """Explain a job's priority and, if pending, why it is waiting.

    Prints the job state and pending reason (from squeue), then the priority
    factor breakdown (from sprio): fairshare, age, partition, QoS, and so on.
    This is for a job that has not started yet. For one that already failed,
    use 'jobs debug'.

    \b
    Use cases:
      - Understand what is holding a pending job back.
      - Compare fairshare and age contributions to a job's priority.

    \b
    Inputs:
      JOBID  A Slurm job id.
    """
    reason = process.run(["squeue", "-j", jobid, "-h", "-o", "%T %r"]).strip()
    if not reason:
        raise click.ClickException(
            f"job {jobid} is not in the queue. It may have finished, in which case "
            f"'jobs debug {jobid}' explains how it ended."
        )
    click.echo(f"State and reason: {reason}")
    code, out, err = process.probe(["sprio", "-j", jobid, "-l"])
    if code:
        raise click.ClickException(f"'sprio' failed for job {jobid}: {err.strip() or code}")
    rows = [line for line in out.splitlines() if line.strip()]
    if len(rows) <= 1:
        click.echo()
        click.echo(
            "sprio has no priority record for this job. It ranks only pending jobs "
            "the scheduler is weighing, so a running, held, or dependency-blocked "
            "job has none; the state and reason above are the explanation."
        )
        return
    for line in rows:
        click.echo(line)
