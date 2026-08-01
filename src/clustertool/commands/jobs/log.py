"""jobs log command."""

import re

import click

from clustertool import completion, process, slurm
from clustertool.grouping import keywords

_FIELD = re.compile(r"(StdOut|StdErr)=(\S+)")
_UNSTARTED = "4294967294"


def _unique(values) -> list[str]:
    """Return the distinct values in order, so an array's elements are all seen."""
    seen: list[str] = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return seen


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
    drops a job MinJobAge seconds after it ends, so for an older one the path
    comes from accounting instead, which stores the pattern rather than the
    expanded name. With --follow, tails the stdout file live (Ctrl+C to stop).

    \b
    Use cases:
      - Find where a job is writing its output.
      - Watch a running job's log in real time.

    \b
    Inputs:
      JOBID         A Slurm job id.
      -f, --follow  Tail the stdout file live.
    """
    code, out, err = process.probe(["scontrol", "show", "job", jobid])
    if code:
        recorded = slurm.job_output_path(jobid)
        if recorded:
            _report(recorded, "", follow)
            return
        if slurm.job_accounting(jobid):
            raise click.ClickException(
                f"no output path recorded for job {jobid}: an interactive job writes to "
                "your terminal, not to a file"
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
            f"job {jobid} is an array with {len(stdouts)} elements, each writing its "
            f"own file. Name one, for example '{jobid}_0'"
        )

    stdout = stdouts[0]
    if _UNSTARTED in stdout:
        raise click.ClickException(
            f"job {jobid} is an array whose elements have not started, so Slurm has "
            f"not filled in the task id ({_UNSTARTED} stands for none). Name an "
            f"element once one starts, for example '{jobid}_0'"
        )
    _report(stdout, stderrs[0] if stderrs else "", follow)
