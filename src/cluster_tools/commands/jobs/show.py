"""jobs show command."""

import click

from cluster_tools import process


@click.command("show")
@click.argument("jobids", nargs=-1, required=True, metavar="JOBID...")
def show(jobids: tuple[str, ...]) -> None:
    """Show live detail for one or more jobs, including the pending reason (via scontrol).

    \b
    Use cases:
      - Inspect a running job's allocation (nodes, GPUs, TRES).
      - See exactly why a job is still pending (the Reason field).

    \b
    Inputs:
      JOBID...  One or more Slurm job ids.
    """
    code = process.stream(["scontrol", "show", "job", "-dd", ",".join(jobids)])
    if code:
        raise SystemExit(code)
