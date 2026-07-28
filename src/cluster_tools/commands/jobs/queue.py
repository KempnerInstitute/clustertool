"""jobs queue command."""

import click

from cluster_tools import process


@click.command("queue")
@click.argument("partition")
def queue(partition: str) -> None:
    """Show a partition's pending jobs in priority order (via showq).

    Lists who is waiting and where you sit, ordered by priority. Unlike
    'jobs list' (your jobs) this is the whole partition's pending queue.

    \b
    Use cases:
      - See how far back your pending job is in a partition.
      - Gauge contention before submitting.

    \b
    Inputs:
      PARTITION  Slurm partition name (e.g. kempner_h100).
    """
    code = process.stream(["showq", "-o", "-p", partition])
    if code:
        raise SystemExit(code)
