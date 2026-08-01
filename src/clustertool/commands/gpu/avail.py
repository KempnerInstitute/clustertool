"""gpu avail command."""

import click

from clustertool import completion, qos, slurm
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
    and memory support at the per-GPU ratio your site enforces for that
    partition, from [partitions.limits] in the site config. A partition with no
    configured ratio shows raw free GPUs unless --cpus-per-gpu / --mem-per-gpu
    are given. Run 'nodes partitions' to see the configured ratios.

    Only schedulable nodes are listed: a node that is down, draining, reserved, in
    maintenance, completing, failing, powered down, not responding, or registered
    with invalid resources keeps its free GPUs but cannot take a new job. A node
    the backfill scheduler has planned for a higher-priority job is still listed,
    since a job that fits before that one is due to start can run on it.

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

    nodes = [node for node in slurm.node_capacity() if partition in node["partitions"]]
    if not nodes:
        if not qos.partition_exists(partition):
            raise click.ClickException(f"partition '{partition}' does not exist")
        raise click.ClickException(f"partition '{partition}' has no nodes")

    rows = []
    for node in nodes:
        if not node["available"]:
            continue
        free_gpu, free_cpu = node["gpu_free"], node["cpu_free"]
        free_mem = node["mem_free_mb"]
        avail_gpu = free_gpu
        if cpus_per_gpu:
            avail_gpu = min(avail_gpu, free_cpu // cpus_per_gpu)
        if mem_per_gpu:
            avail_gpu = min(avail_gpu, int(free_mem // mem_per_gpu))
        if avail_gpu > 0:
            rows.append((node["name"], avail_gpu, free_gpu, free_cpu, round(free_mem / 1024)))
    rows.sort(key=lambda row: row[1], reverse=True)

    caps = []
    if cpus_per_gpu:
        caps.append(f"{cpus_per_gpu} CPU")
    if mem_per_gpu:
        caps.append(f"{mem_per_gpu} MiB")
    limit = f"capped by {' / '.join(caps)} per GPU" if caps else "raw free; no per-GPU ratio known"
    click.echo(f"Allocatable GPUs on '{partition}' ({limit}), most first")
    click.echo()
    if not rows:
        click.echo("  (no nodes with allocatable GPUs)")
        return
    click.echo(
        f"  {'NODE':<20} {'AVAIL_GPU':>9} {'FREE_GPU':>8} {'FREE_CPU':>8} {'FREE_MEM_GB':>12}"
    )
    for node, avail_gpu, free_gpu, free_cpu, free_mem_gb in rows:
        click.echo(f"  {node:<20} {avail_gpu:>9} {free_gpu:>8} {free_cpu:>8} {free_mem_gb:>12}")
