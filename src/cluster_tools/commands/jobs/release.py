"""jobs release command."""

import click

from cluster_tools import completion, process
from cluster_tools.grouping import keywords


@keywords("unhold", "unblock", "resume", "unfreeze")
@click.command("release")
@click.argument(
    "jobids",
    nargs=-1,
    required=True,
    metavar="JOBID...",
    shell_complete=completion.complete_job_ids,
)
def release(jobids: tuple[str, ...]) -> None:
    """Release held jobs so they can be scheduled (via scontrol release).

    Undoes 'jobs hold'.

    \b
    Use cases:
      - Let a previously held job start.

    \b
    Inputs:
      JOBID...  One or more Slurm job ids.
    """
    code = process.stream(["scontrol", "release", ",".join(jobids)])
    if code:
        raise SystemExit(code)
