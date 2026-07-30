"""jobs stats command."""

import click

from cluster_tools import completion, process, site
from cluster_tools.grouping import ToolCommand, keywords


@keywords("efficiency", "utilization", "performance")
@click.command("stats", cls=ToolCommand, tool_key="job_stats")
@click.argument(
    "jobids",
    nargs=-1,
    required=True,
    metavar="JOBID...",
    shell_complete=completion.complete_job_ids,
)
def stats(jobids: tuple[str, ...]) -> None:
    """Show utilization for one or more jobs (via jobstats).

    \b
    Use cases:
      - Check a job's CPU, memory, and GPU utilization.
      - Review the efficiency of a finished job.

    \b
    Inputs:
      JOBID...  One or more Slurm job ids (e.g. 1234567).
    """
    code = process.stream([site.tool("job_stats"), *jobids])
    if code:
        raise SystemExit(code)
