"""gpu avail command."""

import click

from cluster_tools import slurm


@click.command("avail")
@click.argument("partition")
def avail(partition: str) -> None:
    """List nodes in a partition that have free GPUs, most free first.

    Free resources are the configured TRES minus the allocated TRES on each
    node. Only nodes with at least one free GPU are shown.

    \b
    Use cases:
      - Find where there are idle GPUs to target a job.
      - See spare CPU and memory alongside free GPUs.

    \b
    Inputs:
      PARTITION  Slurm partition name (e.g. kempner_h100).
    """
    nodes = [name for name, _ in slurm.partition_nodes(partition)]
    if not nodes:
        raise click.ClickException(f"no nodes found in partition '{partition}'")

    rows = []
    for node in nodes:
        free_gpu, free_cpu, free_mem = slurm.node_free_resources(node)
        if free_gpu > 0:
            rows.append((node, free_gpu, free_cpu, free_mem))
    rows.sort(key=lambda row: row[1], reverse=True)

    click.echo(f"Free resources on '{partition}' (nodes with free GPUs, most first)")
    click.echo()
    if not rows:
        click.echo("  (no nodes with free GPUs)")
        return
    click.echo(f"  {'Node':<20} {'Free_GPU':>8} {'Free_CPU':>8} {'Free_Mem_GB':>12}")
    for node, free_gpu, free_cpu, free_mem in rows:
        click.echo(f"  {node:<20} {free_gpu:>8} {free_cpu:>8} {free_mem:>12.0f}")
