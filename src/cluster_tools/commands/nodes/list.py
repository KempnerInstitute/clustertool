"""nodes list command."""

import click

from cluster_tools import slurm


@click.command("list")
@click.argument("partitions", nargs=-1, required=True, metavar="PARTITION...")
def list_nodes(partitions: tuple[str, ...]) -> None:
    """List node names and states for one or more partitions.

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
            click.echo(f"  {node:<20} {state}")
        click.echo(f"  ({len(rows)} node(s))")
        click.echo()
