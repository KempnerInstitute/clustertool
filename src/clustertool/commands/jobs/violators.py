"""jobs violators command."""

import click

from clustertool import completion, slurm
from clustertool.grouping import keywords


@keywords("abuse", "overuse", "hogs", "greedy")
@click.command("violators")
@click.argument("partition", shell_complete=completion.complete_partitions)
@click.option(
    "--cpus-per-gpu", type=int, default=None, help="CPU-per-GPU norm (overrides the default)."
)
@click.option(
    "--mem-per-gpu",
    type=int,
    default=None,
    help="Memory-per-GPU norm in MiB, Slurm's own unit (overrides the default).",
)
def violators(partition: str, cpus_per_gpu: int | None, mem_per_gpu: int | None) -> None:
    """List running jobs requesting more CPU or memory per GPU than the norm.

    Norms default to the per-partition policy your site sets under
    [partitions.limits]. For a partition with no configured policy, pass
    --cpus-per-gpu and --mem-per-gpu. Jobs with no GPUs are not evaluated.

    Memory is in MiB throughout, which is what Slurm reports and what --mem takes
    by default, so --mem=360G and --mem=368640 are the same request. The OVER
    column gives each job's overage as a ratio, so a job a few percent past the
    norm does not read like one at ten times it. Slurm itself enforces none of
    this; the norms are the site's own, and a site may enforce them separately
    through a job_submit plugin.

    \b
    Use cases:
      - Find jobs hoarding CPU or memory relative to their GPU count.
      - Spot over-requests that block other jobs from a lab's GPUs.

    \b
    Inputs:
      PARTITION       Slurm partition name.
      --cpus-per-gpu  CPU-per-GPU norm (default: per-partition policy).
      --mem-per-gpu   Memory-per-GPU norm in MiB (default: per-partition policy).
    """
    default = slurm.PARTITION_LIMITS.get(partition)
    if cpus_per_gpu is None:
        cpus_per_gpu = default[0] if default else None
    if mem_per_gpu is None:
        mem_per_gpu = default[1] if default else None
    if cpus_per_gpu is None or mem_per_gpu is None:
        if not slurm.partition_nodes(partition):
            raise click.ClickException(f"partition '{partition}' does not exist, or has no nodes")
        known = ", ".join(sorted(slurm.PARTITION_LIMITS)) or "(none)"
        raise click.ClickException(
            f"no per-GPU policy configured for partition '{partition}'; partitions "
            f"with a policy: {known}. Pass --cpus-per-gpu and --mem-per-gpu for others."
        )

    rows = []
    for jobid, user, cpu, gpu, mem_mb in slurm.running_jobs_reqtres(partition):
        if gpu <= 0:
            continue
        over = max((cpu / gpu) / cpus_per_gpu, (mem_mb / gpu) / mem_per_gpu)
        if over > 1:
            rows.append((jobid, cpu, gpu, mem_mb, user, over))
    rows.sort(key=lambda row: row[5], reverse=True)

    click.echo(
        f"Jobs over the per-GPU norm on '{partition}' "
        f"(> {cpus_per_gpu} CPU/GPU or > {mem_per_gpu} MiB/GPU), worst first"
    )
    click.echo()
    if not rows:
        click.echo("  (no jobs over the norm)")
        return
    click.echo(
        f"  {'JOBID':<14} {'#CPU':>5} {'#GPU':>5} {'MEMORY(MiB)':>13} {'OVER':>6}  {'USER':<16}"
    )
    for jobid, cpu, gpu, mem_mb, user, over in rows:
        click.echo(f"  {jobid:<14} {cpu:>5} {gpu:>5} {mem_mb:>13} {over:>5.2f}x  {user:<16}")
