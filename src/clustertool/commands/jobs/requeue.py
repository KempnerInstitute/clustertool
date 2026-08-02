"""jobs requeue command."""

import os
import pwd

import click

from clustertool import completion, process
from clustertool.grouping import keywords


def _describe(jobid: str) -> tuple[str, str, str]:
    """Return (state, owner, elapsed) for a job, with empty fields when unknown."""
    code, out, _ = process.probe(
        ["squeue", "-t", "all", "-h", "-j", jobid, "-O", "State:32,UserName:64,TimeUsed:32"]
    )
    if code != 0:
        return "", "", ""
    row = next((line.split() for line in out.splitlines() if line.strip()), [])
    return tuple(row[:3]) if len(row) >= 3 else ("", "", "")


@keywords("restart", "rerun", "resubmit")
@click.command("requeue")
@click.argument(
    "jobids",
    nargs=-1,
    required=True,
    metavar="JOBID...",
    shell_complete=completion.complete_job_ids,
)
@click.option("-y", "--yes", is_flag=True, help="Skip the confirmation prompt.")
def requeue(jobids: tuple[str, ...], yes: bool) -> None:
    """Cancel and re-queue batch jobs (via scontrol requeue).

    The jobs return to the pending queue and run again from the start, so a
    running job's work so far is discarded. That is confirmed first unless -y,
    and a job owned by someone else is refused. man scontrol limits this to batch
    jobs, so an salloc or srun allocation cannot be requeued, and a job submitted
    with --no-requeue refuses too. The requirement is Privileged or Effective
    Owner: an AdminLevel of Operator or Administrator, root or SlurmUser, or the
    job's own owner or an account coordinator.

    \b
    Use cases:
      - Restart a running or failed job without resubmitting it.

    \b
    Inputs:
      JOBID...   One or more Slurm job ids.
      -y, --yes  Skip the confirmation prompt.
    """
    me = pwd.getpwuid(os.getuid()).pw_name
    described = {jobid: _describe(jobid) for jobid in jobids}
    missing = [jobid for jobid, (state, _, _) in described.items() if not state]
    if missing:
        raise click.ClickException(
            f"not in the queue: {', '.join(missing)}. The id may be mistyped, or the "
            "job may have finished and been dropped by the controller MinJobAge "
            "seconds later, in which case resubmit it rather than requeueing"
        )
    others = {jobid: owner for jobid, (_, owner, _) in described.items() if owner and owner != me}
    if others:
        listed = ", ".join(f"{jobid} ({owner})" for jobid, owner in sorted(others.items()))
        raise click.ClickException(
            f"these jobs belong to another user: {listed}. Requeue only your own"
        )

    running = [
        (jobid, elapsed) for jobid, (state, _, elapsed) in described.items() if state == "RUNNING"
    ]
    if running and not yes:
        for jobid, elapsed in running:
            click.echo(f"  {jobid} has been running for {elapsed}; that work will be discarded")
        click.confirm(f"Requeue {len(jobids)} job(s), restarting them from the start?", abort=True)

    process.passthrough(
        ["scontrol", "requeue", ",".join(jobids)],
        f"could not requeue one or more of {', '.join(jobids)}. man scontrol requeues "
        "batch jobs only, and a job submitted with --no-requeue refuses; the messages "
        "above name which id failed",
    )
