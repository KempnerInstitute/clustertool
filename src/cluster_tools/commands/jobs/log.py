"""jobs log command."""

import re

import click

from cluster_tools import completion, process
from cluster_tools.grouping import keywords

_FIELD = re.compile(r"(StdOut|StdErr)=(\S+)")


@keywords("output", "stdout", "stderr", "tail")
@click.command("log")
@click.argument("jobid", shell_complete=completion.complete_job_ids)
@click.option("-f", "--follow", is_flag=True, help="Tail the stdout file live.")
def log(jobid: str, follow: bool) -> None:
    """Show a job's stdout and stderr paths, or tail its output (via scontrol).

    Reads the StdOut and StdErr paths Slurm recorded for the job. With --follow,
    tails the stdout file live (Ctrl+C to stop).

    \b
    Use cases:
      - Find where a job is writing its output.
      - Watch a running job's log in real time.

    \b
    Inputs:
      JOBID         A Slurm job id.
      -f, --follow  Tail the stdout file live.
    """
    paths = dict(_FIELD.findall(process.run(["scontrol", "show", "job", jobid])))
    stdout = paths.get("StdOut")
    if not stdout:
        raise click.ClickException(
            f"no output path for job {jobid}: interactive jobs have none, and only "
            "running or recent jobs are in scontrol"
        )
    if follow:
        code = process.stream(["tail", "-f", stdout])
        if code:
            raise SystemExit(code)
        return
    click.echo(f"StdOut: {stdout}")
    stderr = paths.get("StdErr")
    if stderr and stderr != stdout:
        click.echo(f"StdErr: {stderr}")
