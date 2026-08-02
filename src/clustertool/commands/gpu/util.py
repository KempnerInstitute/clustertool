"""gpu util command."""

import click

from clustertool import completion, slurm
from clustertool.grouping import keywords


@keywords("busy", "occupancy", "load")
@click.command("util")
@click.argument(
    "partitions",
    nargs=-1,
    metavar="[PARTITION...]",
    shell_complete=completion.complete_partitions,
)
@click.option(
    "-p",
    "--partition",
    "named",
    multiple=True,
    help="Partition to report (repeatable; same as naming it as an argument).",
    shell_complete=completion.complete_partitions,
)
def util(partitions: tuple[str, ...], named: tuple[str, ...]) -> None:
    """Show GPU occupancy per partition: total, unavailable, used, other, free, percent.

    USED is the GPUs held by jobs submitted to that partition. TOTAL, UNAVAIL and
    FREE describe the partition's nodes, read in one scontrol pass: the GPUs those
    nodes have, the unallocated ones on nodes that cannot take a new job (down,
    drained, reserved, in maintenance, blocked, or not responding), and those
    still unallocated on nodes that can. A busy GPU on a drained node is counted
    in USED or OTHER, not in UNAVAIL.

    OTHER is what jobs from partitions sharing the same nodes hold, which is why
    USED plus FREE need not reach TOTAL. On a cluster where a requeue or priority
    partition overlaps a base partition, that column is where the rest of the
    hardware went. UTIL is USED over TOTAL, so it answers how much of the
    partition's hardware its own jobs hold, not how busy the nodes are: add
    OTHER for that.

    With no PARTITION, reports the site base partitions.

    \b
    Use cases:
      - See how full each GPU partition is right now.
      - See how much of a partition's hardware its neighbors are holding.

    \b
    Inputs:
      PARTITION...     One or more partitions (default: the site base partitions).
      -p, --partition  Same, as an option rather than an argument.
    """
    targets = list(partitions) + list(named) or list(slurm.BASE_PARTITIONS)
    if not targets:
        raise click.ClickException(
            "no partitions given and no base partitions configured "
            "([partitions].base in the site config)"
        )
    nodes = slurm.node_capacity()
    known = {name for row in nodes for name in row["partitions"]}
    for partition in targets:
        if partition not in known:
            raise click.ClickException(f"partition '{partition}' does not exist, or has no nodes")

    width = max(9, *(len(partition) for partition in targets)) + 2
    click.echo(
        f"{'PARTITION':<{width}}{'TOTAL':>7}{'UNAVAIL':>8}{'USED':>7}"
        f"{'OTHER':>7}{'FREE':>7}{'UTIL':>8}"
    )
    for partition in targets:
        total, unavailable, used, other, free, pct = slurm.partition_gpu_util(partition, nodes)
        click.echo(
            f"{partition:<{width}}{total:>7}{unavailable:>8}{used:>7}"
            f"{other:>7}{free:>7}{pct:>7.1f}%"
        )
