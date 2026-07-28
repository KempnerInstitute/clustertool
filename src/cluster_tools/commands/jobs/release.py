"""jobs release command."""

import click

from cluster_tools import process


@click.command("release")
@click.argument("jobids", nargs=-1, required=True, metavar="JOBID...")
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
