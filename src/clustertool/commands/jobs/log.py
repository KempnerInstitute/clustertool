"""jobs log command."""

import re

import click

from clustertool import completion, process, slurm
from clustertool.grouping import keywords

_FIELD = re.compile(r"(StdOut|StdErr)=(\S+)")
_ARRAY_TASK = re.compile(r"ArrayTaskId=(\S+)")
_UNSTARTED = "4294967294"


def _unique(values) -> list[str]:
    """Return the distinct values in order, so an array's elements are all seen."""
    seen: list[str] = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return seen


def _first_task(text: str) -> str:
    """Return an array task id from scontrol's output, for use in an example."""
    for task in _ARRAY_TASK.findall(text):
        first = task.split("-")[0].split(",")[0]
        if first.isdigit():
            return first
    return "0"


def _report(stdout: str, stderr: str, follow: bool) -> None:
    """Print the paths, or tail stdout when following."""
    if follow:
        process.passthrough(["tail", "-f", stdout], f"cannot tail {stdout}")
        return
    click.echo(f"StdOut: {stdout}")
    if stderr and stderr != stdout:
        click.echo(f"StdErr: {stderr}")


@keywords("output", "stdout", "stderr", "tail")
@click.command("log")
@click.argument("jobid", shell_complete=completion.complete_job_ids)
@click.option("-f", "--follow", is_flag=True, help="Tail the stdout file live.")
def log(jobid: str, follow: bool) -> None:
    """Show a job's stdout and stderr paths, or tail its output (via scontrol).

    Reads the StdOut and StdErr paths Slurm recorded for the job. The controller
    drops a job MinJobAge seconds after it ends, so for an older one the paths
    come from accounting instead, which stores the pattern rather than the
    expanded name. A pattern that cannot be expanded without the running job, such
    as one naming the node with %N, yields no path rather than a guess. With
    --follow, tails the stdout file live (Ctrl+C to stop).

    \b
    Use cases:
      - Find where a job is writing its output.
      - Watch a running job's log in real time.

    \b
    Inputs:
      JOBID         A Slurm job id.
      -f, --follow  Tail the stdout file live.
    """
    if "." in jobid:
        raise click.ClickException(
            f"{jobid} names a step, which has no output file of its own. "
            f"Give the job id, {jobid.split('.')[0]}"
        )

    code, out, err = process.probe(["scontrol", "show", "job", jobid])
    if code:
        stdout_path, stderr_path = slurm.job_output_paths(jobid)
        if stdout_path:
            _report(stdout_path, stderr_path, follow)
            return
        if slurm.job_accounting(jobid):
            raise click.ClickException(
                f"no output path could be resolved for job {jobid}. An interactive "
                "job writes to your terminal and has none; an array needs an element "
                f"named, such as '{jobid}_0'; and a name Slurm filled in only at run "
                "time, such as one using %N, cannot be reconstructed from accounting"
            )
        raise click.ClickException(
            f"job {jobid} not found: {err.strip() or out.strip() or code}. Only running "
            "or recent jobs are in scontrol, and a job you do not own may be hidden"
        )

    found = _FIELD.findall(out)
    stdouts = _unique(name for key, name in found if key == "StdOut")
    stderrs = _unique(name for key, name in found if key == "StdErr")
    if not stdouts:
        raise click.ClickException(f"no output path for job {jobid}: interactive jobs have none")
    if len(stdouts) > 1:
        raise click.ClickException(
            f"job {jobid} is an array whose elements each write their own file. "
            f"Name one, for example '{jobid}_{_first_task(out)}'"
        )

    stdout = stdouts[0]
    if _UNSTARTED in stdout:
        if _ARRAY_TASK.search(out):
            raise click.ClickException(
                f"job {jobid} is an array whose elements have not started, so Slurm "
                f"has not filled in the task id ({_UNSTARTED} stands for none). Name "
                f"an element once one starts, for example '{jobid}_{_first_task(out)}'"
            )
        raise click.ClickException(
            f"job {jobid} is not an array, but its output pattern uses %a, which "
            f"Slurm leaves as {_UNSTARTED}. Resubmit with a pattern that does not "
            "name an array task, or read the file that name produced"
        )
    _report(stdout, stderrs[0] if stderrs else "", follow)
