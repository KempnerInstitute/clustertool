"""gpu util command."""

import click

from cluster_tools import completion, slurm
from cluster_tools.grouping import keywords


@keywords("busy", "occupancy", "load")
@click.command("util")
@click.argument(
    "partitions",
    nargs=-1,
    metavar="[PARTITION...]",
    shell_complete=completion.complete_partitions,
)
def util(partitions: tuple[str, ...]) -> None:
    """Show GPU occupancy per partition: total, down, available, used, and percent.

    Utilization is used / available GPUs, where available excludes GPUs on down
    or drained nodes. With no PARTITION, reports the Kempner base partitions.

    \b
    Use cases:
      - See how full each Kempner GPU partition is right now.

    \b
    Inputs:
      PARTITION...  One or more partitions (default: the Kempner base partitions).
    """
    targets = list(partitions) or list(slurm.BASE_PARTITIONS)
    click.echo(f"{'Partition':<16}{'Total':>7}{'Down':>7}{'Avail':>7}{'Used':>7}{'Util':>8}")
    for partition in targets:
        total, down, avail, used, pct = slurm.partition_gpu_util(partition)
        click.echo(f"{partition:<16}{total:>7}{down:>7}{avail:>7}{used:>7}{pct:>7.1f}%")
