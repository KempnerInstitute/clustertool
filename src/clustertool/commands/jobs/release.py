"""jobs release command."""

import click

from clustertool import completion, process
from clustertool.grouping import keywords


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

    Undoes 'jobs hold'. You can release your own hold, but a hold placed by an
    operator or admin needs one of them to lift it.

    \b
    Use cases:
      - Let a previously held job start.

    \b
    Inputs:
      JOBID...  One or more Slurm job ids.
    """
    if process.stream(["scontrol", "release", ",".join(jobids)]):
        raise click.ClickException(f"failed to release {', '.join(jobids)}")
