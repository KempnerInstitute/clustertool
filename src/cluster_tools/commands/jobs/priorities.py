"""jobs priorities command."""

import click

from cluster_tools import completion, process
from cluster_tools.grouping import keywords


@keywords("priority", "ranking", "factors", "order")
@click.command("priorities")
@click.argument("partition", shell_complete=completion.complete_partitions)
def priorities(partition: str) -> None:
    """Show priority factors for pending jobs in a partition (via sprio).

    Lists each pending job's total priority and its fairshare, age, and other
    factor contributions, so you can compare where jobs rank.

    \b
    Use cases:
      - Compare pending jobs' priorities across a partition.

    \b
    Inputs:
      PARTITION  Slurm partition name (e.g. kempner_h100).
    """
    code = process.stream(["sprio", "-p", partition])
    if code:
        raise SystemExit(code)
