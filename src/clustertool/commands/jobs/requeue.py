"""jobs requeue command."""

import click

from clustertool import completion, jobaction, process
from clustertool.grouping import keywords


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
    planned = jobaction.plan("requeue", list(jobids))
    if planned.running and not yes:
        for jobid, elapsed in planned.running:
            click.echo(f"  {jobid} has been running for {elapsed}; that work will be discarded")
        click.confirm(f"Requeue {len(jobids)} job(s), restarting them from the start?", abort=True)
    process.passthrough(planned.cmd, planned.failure)
