"""gpu avail command."""

import click

from clustertool import completion, slurm
from clustertool.grouping import keywords


@keywords("free", "available", "empty", "where")
@click.command("avail")
@click.argument("partition", shell_complete=completion.complete_partitions)
@click.option(
    "--cpus-per-gpu",
    type=int,
    default=None,
    help="Cores per GPU (overrides the partition default).",
)
@click.option(
    "--mem-per-gpu",
    type=int,
    default=None,
    help="Memory per GPU in MB (overrides the partition default).",
)
def avail(partition: str, cpus_per_gpu: int | None, mem_per_gpu: int | None) -> None:
    """List nodes with GPUs you can actually allocate, most first.

    Available GPUs per node are the free GPUs, capped by how many the free CPU
    and memory support at the enforced per-GPU ratio (kempner: 16 CPU / 240 GB;
    kempner_h100: 24 / 360; kempner_h200: 16 / 360; kempner_rtx: 16 / 180). Other
    partitions show raw free GPUs unless --cpus-per-gpu / --mem-per-gpu are given.

    \b
    Use cases:
      - Find where you can actually place a GPU job.
      - See spare CPU and memory alongside usable GPUs.

    \b
    Inputs:
      PARTITION       Slurm partition name (e.g. kempner_h100).
      --cpus-per-gpu  Cores per GPU (overrides the per-partition default).
      --mem-per-gpu   Memory per GPU in MB (overrides the per-partition default).
    """
    default = slurm.PARTITION_LIMITS.get(partition)
    if cpus_per_gpu is None and default:
        cpus_per_gpu = default[0]
    if mem_per_gpu is None and default:
        mem_per_gpu = default[1]

    nodes = [name for name, _ in slurm.partition_nodes(partition)]
    if not nodes:
        raise click.ClickException(f"no nodes found in partition '{partition}'")

    rows = []
    for node in nodes:
        free_gpu, free_cpu, free_mem = slurm.node_free_resources(node)
        avail_gpu = free_gpu
        if cpus_per_gpu:
            avail_gpu = min(avail_gpu, free_cpu // cpus_per_gpu)
        if mem_per_gpu:
            avail_gpu = min(avail_gpu, int(free_mem // mem_per_gpu))
        if avail_gpu > 0:
            rows.append((node, avail_gpu, free_gpu, free_cpu, round(free_mem / 1024)))
    rows.sort(key=lambda row: row[1], reverse=True)

    if cpus_per_gpu and mem_per_gpu:
        limit = f"capped by {cpus_per_gpu} CPU / {mem_per_gpu // 1000} GB per GPU"
    else:
        limit = "raw free; no per-GPU ratio known"
    click.echo(f"Allocatable GPUs on '{partition}' ({limit}), most first")
    click.echo()
    if not rows:
        click.echo("  (no nodes with allocatable GPUs)")
        return
    click.echo(
        f"  {'Node':<20} {'Avail_GPU':>9} {'Free_GPU':>8} {'Free_CPU':>8} {'Free_Mem_GB':>12}"
    )
    for node, avail_gpu, free_gpu, free_cpu, free_mem_gb in rows:
        click.echo(f"  {node:<20} {avail_gpu:>9} {free_gpu:>8} {free_cpu:>8} {free_mem_gb:>12}")
