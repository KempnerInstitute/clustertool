"""nodes list command."""

import click

from clustertool import completion, slurm
from clustertool.grouping import keywords


@keywords("hosts", "machines", "state")
@click.command("list")
@click.argument(
    "partitions",
    nargs=-1,
    required=True,
    metavar="PARTITION...",
    shell_complete=completion.complete_partitions,
)
def list_nodes(partitions: tuple[str, ...]) -> None:
    """List node names and states for one or more partitions.

    States are Slurm's own short codes: idle is free, mix is partly allocated,
    alloc is full, resv is held by a reservation, drain and drng take no new work,
    and down is offline. A trailing * means the node is not responding.

    \b
    Use cases:
      - See which nodes make up a partition.
      - Check node states before targeting a node for a job.

    \b
    Inputs:
      PARTITION...  One or more Slurm partition names (e.g. kempner_h100).
    """
    for partition in partitions:
        rows = slurm.partition_nodes(partition)
        click.echo(f"== {partition} ==")
        if not rows:
            click.echo("  (no nodes; unknown or empty partition)")
            click.echo()
            continue
        for node, state in rows:
            note = "  (not responding)" if state.endswith("*") else ""
            click.echo(f"  {node:<20} {state}{note}")
        click.echo(f"  ({len(rows)} node(s))")
        click.echo()
