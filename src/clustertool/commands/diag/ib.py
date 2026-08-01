"""diag ib command."""

import concurrent.futures

import click

from clustertool import completion, process, slurm
from clustertool.grouping import admin, keywords

_SSH_OPTS = [
    "-o",
    "StrictHostKeyChecking=accept-new",
    "-o",
    "LogLevel=ERROR",
    "-o",
    "ConnectTimeout=5",
]
_IB_CHECK = "ip link show | grep -E 'ib[0-9]' | grep DOWN"


def _host_ib_down(host: str) -> str:
    """Return DOWN InfiniBand port lines for a host (empty if none or unreachable)."""
    return process.run(["ssh", *_SSH_OPTS, host, _IB_CHECK]).strip()


@admin
@keywords("infiniband", "network", "fabric")
@click.command("ib")
@click.argument(
    "partitions",
    nargs=-1,
    required=True,
    metavar="PARTITION...",
    shell_complete=completion.complete_partitions,
)
@click.option("--parallel", default=24, show_default=True, help="Maximum parallel ssh checks.")
def ib(partitions: tuple[str, ...], parallel: int) -> None:
    """Report nodes with InfiniBand ports DOWN in one or more partitions.

    For each partition, ssh to its nodes in parallel and flag any host whose
    'ip link show' reports an ib[0-9] interface in state DOWN. Unreachable hosts
    are skipped.

    Needs ssh to every node in the partition, not just the ones running your
    jobs. Where node login is gated on having an allocation, as pam_slurm_adopt
    does, only staff can reach the whole partition and an ordinary user sees
    every host skipped.

    \b
    Use cases:
      - Find nodes with a downed IB link before scheduling a large job.
      - Spot-check fabric health across a partition.

    \b
    Inputs:
      PARTITION...  One or more Slurm partition names (e.g. kempner_h100).
    """
    for partition in partitions:
        nodes = [name for name, _ in slurm.partition_nodes(partition)]
        click.echo(f"== {partition} ({len(nodes)} node(s)) ==")
        if not nodes:
            click.echo("  (no nodes; unknown or empty partition)")
            click.echo()
            continue
        down = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(parallel, 1)) as pool:
            for host, status in zip(nodes, pool.map(_host_ib_down, nodes), strict=True):
                if status:
                    down[host] = status
        if not down:
            click.echo("  all IB ports up")
        for host in sorted(down):
            click.echo(f"  {host}:")
            for line in down[host].splitlines():
                click.echo(f"    {line.strip()}")
        click.echo(f"  >>> {len(down)} host(s) with IB ports DOWN")
        click.echo()
