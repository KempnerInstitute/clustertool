"""jobs top command."""

import click

from clustertool import completion, process
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
    none).

    \b
    Use cases:
      - Watch a running job's memory before it hits the limit.

    \b
    Inputs:
      JOBID  A running Slurm job id.
    """
    code = process.stream(["sstat", "-a", "-j", jobid, "--format", _FORMAT])
    if code:
        raise SystemExit(code)
