"""gpu monitor-partition command."""

import click

from clustertool import completion, monitor, qos, slurm
from clustertool.grouping import admin, keywords


@admin
@keywords("watch", "live", "realtime", "dashboard")
@click.command("monitor-partition")
@click.argument("partition", shell_complete=completion.complete_partitions)
@click.option(
    "--interval",
    type=click.IntRange(min=1),
    default=5,
    show_default=True,
    help="Seconds to wait between rounds of samples.",
)
@click.option(
    "--filter", "prefix", default="", help="Only nodes whose name starts with this prefix."
)
def monitor_partition(partition: str, interval: int, prefix: str) -> None:
    """Live GPU/CPU/memory/InfiniBand monitor for a partition's nodes.

    Refreshes a colored per-node table in place until Ctrl+C. Requires
    passwordless ssh to the nodes, which must expose nvidia-smi.

    That means ssh to every node in the partition, not only the ones running
    your jobs. Where node login requires an allocation on that node, as
    pam_slurm_adopt enforces, use 'gpu monitor-job JOBID' instead.

    \b
    Use cases:
      - Watch utilization across a partition during a large run.
      - Spot idle or network-starved nodes live.

    \b
    Inputs:
      PARTITION   Slurm partition name (e.g. kempner_h100).
      --interval  Seconds to wait between rounds (default 5). A round itself
                  takes a few seconds, so the period is longer than this.
      --filter    Only include nodes whose name starts with this prefix.
    """
    rows = slurm.partition_nodes(partition)
    if not rows:
        if not qos.partition_exists(partition):
            raise click.ClickException(f"partition '{partition}' does not exist")
        raise click.ClickException(f"partition '{partition}' has no nodes")
    nodes = [name for name, state in rows if slurm.is_schedulable_state(state)]
    skipped = len(rows) - len(nodes)
    if not nodes:
        raise click.ClickException(
            f"every node in partition '{partition}' is down, drained, or reserved, "
            "so there is nothing running to watch"
        )
    hosts = [name for name in nodes if name.startswith(prefix)]
    if not hosts:
        raise click.ClickException(
            f"no node in partition '{partition}' starts with '{prefix}' "
            f"({len(nodes)} node(s) before the filter)"
        )
    if skipped:
        click.echo(
            f"skipping {skipped} node(s) that cannot take work (down, drained, or reserved)",
            err=True,
        )
    monitor.run_monitor(f"GPU/CPU/MEM/NET Monitor for Partition: {partition}", hosts, interval)
