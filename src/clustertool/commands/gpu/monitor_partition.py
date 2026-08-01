"""gpu monitor-partition command."""

import click

from clustertool import completion, monitor, slurm
from clustertool.grouping import admin, keywords


@admin
@keywords("watch", "live", "realtime", "dashboard")
@click.command("monitor-partition")
@click.argument("partition", shell_complete=completion.complete_partitions)
@click.option("--interval", default=5, show_default=True, help="Refresh interval in seconds.")
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
      --interval  Refresh interval in seconds (default 5).
      --filter    Only include nodes whose name starts with this prefix.
    """
    hosts = [name for name, _ in slurm.partition_nodes(partition) if name.startswith(prefix)]
    if not hosts:
        raise click.ClickException(f"no nodes matched in partition '{partition}'")
    monitor.run_monitor(f"GPU/CPU/MEM/NET Monitor for Partition: {partition}", hosts, interval)
