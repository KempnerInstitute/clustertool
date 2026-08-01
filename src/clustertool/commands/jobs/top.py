"""jobs top command."""

import click

from clustertool import completion, process, slurm
from clustertool.grouping import keywords

_FORMAT = "JobID,AveCPU,AveRSS,MaxRSS,AveVMSize,NTasks"


@keywords("monitor", "live", "watch", "resources")
@click.command("top")
@click.argument("jobid", shell_complete=completion.complete_job_ids)
def top(jobid: str) -> None:
    """Show live resource use of a running job's steps (via sstat).

    Reports current CPU and memory (AveRSS/MaxRSS) for an in-flight job, which
    sacct and jobstats cannot until the job finishes. Only jobs with an active
    step report data (a bare interactive allocation with no running step shows
    none), so a job that is pending or already finished is an error rather than
    an empty table: sstat exits 0 either way. For an array, name one element.

    \b
    Use cases:
      - Watch a running job's memory before it hits the limit.

    \b
    Inputs:
      JOBID  A running Slurm job id.
    """
    record = slurm.job_accounting(jobid)
    if not record:
        raise click.ClickException(f"no accounting record for job {jobid}")
    states = record.get("states") or {record.get("state", "").split()[0]: 1}
    if "RUNNING" not in states:
        listed = ", ".join(sorted(states)) or "unknown"
        raise click.ClickException(
            f"job {jobid} is not running ({listed}); sstat reads live steps only. "
            f"Use 'clustertool jobs stats {jobid}' for a finished job"
        )
    process.passthrough(
        ["sstat", "-a", "-j", jobid, "--format", _FORMAT], f"'sstat' failed for job {jobid}"
    )
