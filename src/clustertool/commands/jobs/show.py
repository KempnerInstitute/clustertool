"""jobs show command."""

import re

import click

from clustertool import completion, process
from clustertool.grouping import keywords

_JOB_ID = re.compile(r"^\d+(_(\d+|\[[\d,\-]+\]))?(\.[\w+]+)?$")


def _in_accounting(jobid: str) -> bool:
    """Return True if accounting holds the job, so it ran and has since aged out."""
    code, out, _ = process.probe(["sacct", "-j", jobid, "-X", "-n", "-P", "-o", "JobID"])
    return code == 0 and bool(out.strip())


@keywords("detail", "info", "inspect", "describe")
@click.command("show")
@click.argument(
    "jobids",
    nargs=-1,
    required=True,
    metavar="JOBID...",
    shell_complete=completion.complete_job_ids,
)
def show(jobids: tuple[str, ...]) -> None:
    """Show live detail for one or more jobs, including the pending reason (via scontrol).

    Queries one job per scontrol call: man scontrol takes a single job id for
    show, and reads a comma-separated list as one malformed id. An argument that
    is not a job id is refused rather than passed on, since scontrol left with no
    id prints every job on the cluster.

    \b
    Use cases:
      - Inspect a running job's allocation (nodes, GPUs, TRES).
      - See exactly why a job is still pending (the Reason field).

    \b
    Inputs:
      JOBID...  One or more Slurm job ids.
    """
    for jobid in jobids:
        if not _JOB_ID.match(jobid):
            raise click.ClickException(
                f"not a job id: {jobid!r}. Give a job id such as 1234567, an array "
                "element such as 1234567_0, or a step such as 1234567.batch"
            )

    failures = []
    shown = 0
    for jobid in jobids:
        code, out, err = process.probe(["scontrol", "show", "job", "-dd", jobid])
        if code:
            failures.append((jobid, err.strip() or out.strip()))
            continue
        if shown:
            click.echo()
        click.echo(out.rstrip())
        shown += 1

    for jobid, detail in failures:
        if _in_accounting(jobid):
            click.echo(
                f"job {jobid} has finished and is no longer held by the scheduler; "
                f"try 'clustertool jobs debug {jobid}'",
                err=True,
            )
        else:
            click.echo(f"job {jobid}: {detail or 'not found'}", err=True)
    if failures:
        raise SystemExit(1)
