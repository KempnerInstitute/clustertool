"""jobs violators command."""

import click

from cluster_tools import slurm
from cluster_tools.grouping import keywords


@keywords("abuse", "overuse", "hogs", "greedy")
@click.command("violators")
@click.argument("partition")
@click.option(
    "--cpu-per-gpu", type=int, default=None, help="CPU-per-GPU norm (overrides the default)."
)
@click.option(
    "--mem-per-gpu",
    type=int,
    default=None,
    help="Memory-per-GPU norm in MB (overrides the default).",
)
def violators(partition: str, cpu_per_gpu: int | None, mem_per_gpu: int | None) -> None:
    """List running jobs requesting more CPU or memory per GPU than the norm.

    Norms default to the per-partition policy (kempner_h100: 24 CPU / 360000 MB
    per GPU; kempner: 16 CPU / 240000 MB per GPU). For other partitions, pass
    --cpu-per-gpu and --mem-per-gpu. Jobs with no GPUs are not evaluated.

    \b
    Use cases:
      - Find jobs hoarding CPU or memory relative to their GPU count.
      - Spot over-requests that block other jobs from a lab's GPUs.

    \b
    Inputs:
      PARTITION      Slurm partition name (e.g. kempner_h100).
      --cpu-per-gpu  CPU-per-GPU norm (default: per-partition policy).
      --mem-per-gpu  Memory-per-GPU norm in MB (default: per-partition policy).
    """
    default = slurm.PARTITION_LIMITS.get(partition)
    if cpu_per_gpu is None:
        cpu_per_gpu = default[0] if default else None
    if mem_per_gpu is None:
        mem_per_gpu = default[1] if default else None
    if cpu_per_gpu is None or mem_per_gpu is None:
        known = ", ".join(sorted(slurm.PARTITION_LIMITS))
        raise click.ClickException(
            f"unknown partition '{partition}'; known partitions: {known}. "
            "Pass --cpu-per-gpu and --mem-per-gpu for others."
        )

    rows = []
    for jobid, user, cpu, gpu, mem_mb in slurm.running_jobs_reqtres(partition):
        if gpu <= 0:
            continue
        if cpu / gpu > cpu_per_gpu or mem_mb / gpu > mem_per_gpu:
            rows.append((jobid, cpu, gpu, mem_mb, user))
    rows.sort(key=lambda row: row[2], reverse=True)

    click.echo(
        f"Jobs over the per-GPU norm on '{partition}' "
        f"(> {cpu_per_gpu} CPU/GPU or > {mem_per_gpu} MB/GPU)"
    )
    click.echo()
    if not rows:
        click.echo("  (no jobs over the norm)")
        return
    click.echo(f"  {'JobID':<14} {'#CPU':>5} {'#GPU':>5} {'Memory(MB)':>12} {'User':<16}")
    for jobid, cpu, gpu, mem_mb, user in rows:
        click.echo(f"  {jobid:<14} {cpu:>5} {gpu:>5} {mem_mb:>12} {user:<16}")
