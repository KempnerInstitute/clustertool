"""nodes frag command."""

import click

from clustertool import completion, slurm
from clustertool.grouping import keywords

_SHAPES = (1, 2, 4)
_FALLBACK_SHAPE = (8, 65536)


@keywords("fragmentation", "fit", "capacity", "schedulable", "free")
@click.command("frag")
@click.option(
    "-p",
    "--partition",
    shell_complete=completion.complete_partitions,
    help="Limit to one partition.",
)
@click.option(
    "--cpus-per-gpu",
    type=click.IntRange(min=1),
    default=None,
    help="CPUs per GPU in the hypothetical job shape.",
)
@click.option(
    "--mem-per-gpu",
    type=click.IntRange(min=1),
    default=None,
    help="Memory per GPU in MiB in the hypothetical job shape.",
)
def frag(partition: str | None, cpus_per_gpu: int | None, mem_per_gpu: int | None) -> None:
    """Show free GPU shards per partition and how many N-GPU jobs could start now.

    Reads one scontrol pass, over the GPU nodes only. A node that cannot take a
    new job is excluded: down, drained, reserved, in maintenance, completing,
    failing, powered down, not responding, or registered with invalid resources.
    A node the backfill scheduler has planned for a higher-priority job is kept,
    though its free capacity may only admit a job short enough to finish first.
    For each partition it prints the free-GPU distribution (0/1/2/3/4+ per node)
    and how many 1-, 2-, and 4-GPU jobs of the given shape could start right now.

    With --partition, the job shape defaults to that partition's per-GPU CPU and
    memory policy from [partitions.limits] in the site config, so the fit counts
    describe a job that partition would actually accept. Across partitions, or for
    a partition with no configured ratio, it falls back to 8 CPU and 65536 MiB per
    GPU. Either value can be overridden. The header states the shape in force.

    \b
    Use cases:
      - See where a multi-GPU job can actually land.
      - Spot fragmentation: many free GPUs but few whole-node slots.

    \b
    Inputs:
      -p, --partition  Limit to one partition.
      --cpus-per-gpu   CPUs per GPU in the job shape.
      --mem-per-gpu    Memory per GPU in MiB in the job shape.
    """
    limits = slurm.PARTITION_LIMITS.get(partition) if partition else None
    from_policy = limits is not None and cpus_per_gpu is None and mem_per_gpu is None
    if cpus_per_gpu is None:
        cpus_per_gpu = limits[0] if limits else _FALLBACK_SHAPE[0]
    if mem_per_gpu is None:
        mem_per_gpu = limits[1] if limits else _FALLBACK_SHAPE[1]

    nodes = [row for row in slurm.node_capacity() if row["gpu_tot"]]
    if partition:
        nodes = [n for n in nodes if partition in n["partitions"]]
        if not nodes:
            if not slurm.partition_exists(partition):
                raise click.ClickException(f"partition '{partition}' does not exist")
            raise click.ClickException(f"partition '{partition}' has no GPU nodes")

    per_part: dict[str, dict] = {}
    for node in nodes:
        if not node["available"]:
            continue
        for part in node["partitions"] or ["(none)"]:
            if partition and part != partition:
                continue
            stats = per_part.setdefault(
                part,
                {"nodes": 0, "dist": {0: 0, 1: 0, 2: 0, 3: 0, "4+": 0}, "fit": {1: 0, 2: 0, 4: 0}},
            )
            stats["nodes"] += 1
            free = node["gpu_free"]
            stats["dist"][free if free < 4 else "4+"] += 1
            for shape in _SHAPES:
                fits = min(
                    free // shape,
                    node["cpu_free"] // (shape * cpus_per_gpu),
                    node["mem_free_mb"] // (shape * mem_per_gpu),
                )
                stats["fit"][shape] += max(0, fits)

    unavailable = [n for n in nodes if not n["available"]]
    source = f", the {partition} per-GPU policy" if from_policy else ""
    click.echo(
        f"Free GPU shards and N-GPU-job fit  "
        f"(job shape: {cpus_per_gpu} CPU + {mem_per_gpu} MiB per GPU{source})"
    )
    click.echo()
    width = max(24, *(len(part) for part in per_part)) + 1 if per_part else 24
    click.echo(
        f"  {'Partition':<{width}}{'Nodes':>6}  {'FreeGPUs(0/1/2/3/4+)':<22}"
        f"{'Fit1':>6}{'Fit2':>6}{'Fit4':>6}"
    )
    for part in sorted(per_part):
        stats = per_part[part]
        dist = "/".join(str(stats["dist"][k]) for k in (0, 1, 2, 3, "4+"))
        click.echo(
            f"  {part:<{width}}{stats['nodes']:>6}  {dist:<22}"
            f"{stats['fit'][1]:>6}{stats['fit'][2]:>6}{stats['fit'][4]:>6}"
        )
    if not per_part:
        click.echo("  (no available nodes)")
    if unavailable:
        click.echo()
        click.echo(f"  {len(unavailable)} GPU node(s) not accepting new work, excluded")
        for node in unavailable[:10]:
            click.echo(f"    {node['name']} ({node['state']})")
        if len(unavailable) > 10:
            click.echo(f"    ... and {len(unavailable) - 10} more")
