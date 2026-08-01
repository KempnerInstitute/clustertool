"""jobs why command."""

import click

from clustertool import completion, process
from clustertool.grouping import keywords


def _missing_code(text: str) -> bool:
    """Return True if squeue's own message is that the job id is not one it knows."""
    return "invalid job id" in text.lower()


@keywords("pending", "waiting", "stuck", "blocked")
@click.command("why")
@click.argument("jobid", shell_complete=completion.complete_job_ids)
def why(jobid: str) -> None:
    """Explain a job's priority and, if pending, why it is waiting.

    Prints the job state and pending reason (from squeue), then the priority
    factor breakdown (from sprio), which covers whichever factors your cluster
    gives a non-zero weight. This is for a job that has not started yet. For one
    that already failed, use 'jobs debug'.

    An array is reported one line per state group, since its elements can be in
    different states.

    \b
    Use cases:
      - Understand what is holding a pending job back.
      - Compare fairshare and age contributions to a job's priority.

    \b
    Inputs:
      JOBID  A Slurm job id.
    """
    code, out, err = process.probe(["squeue", "-t", "all", "-j", jobid, "-h", "-o", "%i %T %r"])
    if code != 0:
        if _missing_code(out + err):
            raise click.ClickException(
                f"job {jobid} is not a job id this cluster knows. Only running or "
                f"recent jobs are in the queue; for an older one try 'jobs debug {jobid}'"
            )
        raise click.ClickException(
            f"could not query job {jobid}: {err.strip() or out.strip() or code}"
        )
    rows = [line for line in out.splitlines() if line.strip()]
    if not rows:
        raise click.ClickException(
            f"job {jobid} is no longer in the queue. The controller drops a job "
            f"MinJobAge seconds after it ends, so 'jobs debug {jobid}' explains how it ended."
        )
    for line in rows:
        click.echo(f"State and reason: {line}")

    code, out, err = process.probe(["sprio", "-j", jobid])
    if code == 127:
        raise click.ClickException(
            "'sprio' not found on this host. It ships with the multifactor priority "
            "plugin, so a cluster using priority/basic does not have it"
        )
    if code:
        raise click.ClickException(f"'sprio' failed for job {jobid}: {err.strip() or code}")
    priority_rows = [line for line in out.splitlines() if line.strip()]
    if len(priority_rows) <= 1:
        click.echo()
        click.echo(
            "sprio has no priority record for this job. It ranks only the pending "
            "jobs the scheduler is weighing, so a job that is running, held, waiting "
            "on a dependency, or not yet eligible has none; the state and reason "
            "above are the explanation."
        )
        return
    click.echo()
    for line in priority_rows:
        click.echo(line)
