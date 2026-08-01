"""jobs top command."""

import click

from clustertool import completion, process, site, slurm
from clustertool.grouping import keywords

_FORMAT = "JobID%-20,AveCPU,AveRSS,MaxRSS,AveVMSize,NTasks"
_EXTERN = ".extern"


def _finished_hint(jobid: str) -> str:
    """Return the command to reach for once a job has ended.

    jobs stats wraps a site tool that need not be installed, so it is only
    offered where the site config names one that is.
    """
    if site.tool_available("job_stats"):
        return f"'clustertool jobs stats {jobid}'"
    return f"'clustertool jobs debug {jobid}'"


def _data_rows(out: str) -> list[str]:
    """Return sstat's rows without its two header lines or the extern step.

    The extern step carries Slurm's unset AveCPU sentinel and no memory, so on a
    bare allocation it would be the whole answer and would read as a real figure.
    The JobID column is widened in the format so the step name is not truncated
    past the point where it can be recognized.
    """
    lines = [line for line in out.splitlines() if line.strip()]
    body = lines[2:] if len(lines) >= 2 else []
    return [line for line in body if _EXTERN not in line.split()[0]]


@keywords("monitor", "live", "watch", "resources")
@click.command("top")
@click.argument("jobid", shell_complete=completion.complete_job_ids)
def top(jobid: str) -> None:
    """Show live resource use of a running job's steps (via sstat).

    Reports current CPU and memory (AveRSS/MaxRSS) for an in-flight job, which
    sacct does not record until the job finishes. Only jobs with an active step
    report data, so a job that is pending, already finished, or holding a bare
    allocation with no step is an error rather than an empty table: sstat exits 0
    either way, and per man sstat a non-root user cannot read another user's
    steps at all. Naming an array element reads that element, since sstat matches
    the element's own job id rather than the array's.

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
        if "PENDING" in states:
            raise click.ClickException(
                f"job {jobid} has not started ({listed}); 'clustertool jobs why "
                f"{jobid}' explains the wait"
            )
        raise click.ClickException(
            f"job {jobid} is not running ({listed}); sstat reads live steps only. "
            f"Use {_finished_hint(jobid)} for a finished job"
        )

    target = record.get("first_element") or jobid
    code, out, err = process.probe(["sstat", "-a", "-j", target, "--format", _FORMAT])
    rows = _data_rows(out) if code == 0 else []
    if not rows:
        detail = err.strip().splitlines()[0] if err.strip() else ""
        raise click.ClickException(
            f"no live step data for job {jobid}"
            + (f": {detail}" if detail else "")
            + ". A job holding an allocation with no step running has none, and per "
            "man sstat only root can read another user's steps"
        )
    click.echo("\n".join(out.splitlines()[:2] + rows))
