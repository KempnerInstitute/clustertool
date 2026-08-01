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
def util(partitions: tuple[str, ...]) -> None:
    """Show GPU occupancy per partition: total, unavailable, used, free, and percent.

    Every column is measured on the partition's nodes, read in one scontrol pass.
    UNAVAIL is the GPUs on nodes that cannot take a new job (down, drained,
    reserved, or in maintenance). USED is the GPUs Slurm has allocated on those
    nodes, and FREE the unallocated ones on nodes that can still take work, so
    USED plus FREE need not reach TOTAL. Where partitions share nodes, as a
    requeue or priority partition does with a base partition, USED counts the
    neighbors' jobs too, because a job on a shared node occupies the same GPU
    either way. UTIL is used over total. With no PARTITION, reports the site base
    partitions.

    \b
    Use cases:
      - See how full each GPU partition is right now.

    \b
    Inputs:
      PARTITION...  One or more partitions (default: the site base partitions).
    """
    targets = list(partitions) or list(slurm.BASE_PARTITIONS)
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
    click.echo(f"{'PARTITION':<{width}}{'TOTAL':>7}{'UNAVAIL':>8}{'USED':>7}{'FREE':>7}{'UTIL':>8}")
    for partition in targets:
        total, unavailable, used, free, pct = slurm.partition_gpu_util(partition, nodes)
        click.echo(f"{partition:<{width}}{total:>7}{unavailable:>8}{used:>7}{free:>7}{pct:>7.1f}%")
