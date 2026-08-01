"""jobs priorities command."""

import click

from clustertool import completion, process, slurm
from clustertool.grouping import keywords


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
      PARTITION  Slurm partition name.
    """
    if not slurm.partition_nodes(partition):
        raise click.ClickException(f"partition '{partition}' does not exist, or has no nodes.")
    code = process.stream(["sprio", "-p", partition])
    if code:
        raise SystemExit(code)
