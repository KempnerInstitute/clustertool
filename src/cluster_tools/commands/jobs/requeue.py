"""jobs requeue command."""

import click

from cluster_tools import process
from cluster_tools.grouping import keywords


@keywords("restart", "rerun", "resubmit")
@click.command("requeue")
@click.argument("jobids", nargs=-1, required=True, metavar="JOBID...")
def requeue(jobids: tuple[str, ...]) -> None:
    """Cancel and re-queue jobs (via scontrol requeue).

    The jobs return to the pending queue and run again from the start.

    \b
    Use cases:
      - Restart a running or failed job without resubmitting it.

    \b
    Inputs:
      JOBID...  One or more Slurm job ids.
    """
    code = process.stream(["scontrol", "requeue", ",".join(jobids)])
    if code:
        raise SystemExit(code)
