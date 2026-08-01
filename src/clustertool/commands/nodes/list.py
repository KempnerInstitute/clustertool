"""nodes list command."""

import click

from clustertool import completion, qos, slurm
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
    alloc is full, comp is finishing a job, resv is held by a reservation, drain
    and drng take no new work, down is offline, inval registered resources that do
    not match its configuration, and plnd is reserved by the backfill scheduler
    for a higher-priority job. Two flags can follow: * means the node is not
    responding, and - that backfill has planned it for a higher-priority job.

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
            if not qos.partition_exists(partition):
                raise click.ClickException(f"partition '{partition}' does not exist")
            click.echo("  (no nodes)")
            click.echo()
            continue
        for node, state in rows:
            notes = []
            if state.endswith("*"):
                notes.append("not responding")
            if state.endswith("-"):
                notes.append("planned by backfill")
            note = f"  ({', '.join(notes)})" if notes else ""
            click.echo(f"  {node:<20} {state:<8}{note}".rstrip())
        click.echo(f"  ({len(rows)} node(s))")
        click.echo()
