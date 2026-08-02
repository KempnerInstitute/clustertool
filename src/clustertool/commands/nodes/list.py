"""nodes list command."""

import click

from clustertool import completion, slurm
from clustertool.grouping import keywords

_FLAGS = {
    "*": "not responding, takes no new work",
    "~": "powered off",
    "#": "powering up",
    "!": "pending power down",
    "%": "powering down",
    "$": "in a maintenance reservation, takes no new work",
    "@": "pending reboot",
    "^": "reboot issued",
    "-": "planned by backfill for a higher-priority job",
}
"""The trailing state flags man sinfo documents, in its own words."""


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
    for a higher-priority job. A flag can follow, and man sinfo documents nine;
    each is spelled out beside the node, since several of them mean the node
    cannot take work whatever its base state reads.

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
        if not rows and not slurm.partition_exists(partition):
            raise click.ClickException(f"partition '{partition}' does not exist")
        click.echo(f"== {partition} ==")
        if not rows:
            click.echo("  (no nodes)")
            click.echo()
            continue
        for node, state in rows:
            flag = _FLAGS.get(state[-1:], "")
            note = f"  ({flag})" if flag else ""
            click.echo(f"  {node:<20} {state:<8}{note}".rstrip())
        click.echo(f"  ({len({node for node, _ in rows})} node(s))")
        click.echo()
