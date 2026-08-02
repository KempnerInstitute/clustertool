"""jobs violators command."""

import click

from clustertool import completion, slurm
from clustertool.grouping import keywords


@keywords("abuse", "overuse", "hogs", "greedy")
@click.command("violators")
@click.argument("partition", shell_complete=completion.complete_partitions)
@click.option(
    "--cpus-per-gpu",
    type=click.IntRange(min=1),
    default=None,
    help="CPU-per-GPU norm (overrides the default).",
)
@click.option(
    "--mem-per-gpu",
    type=click.IntRange(min=1),
    default=None,
    help="Memory-per-GPU norm in MiB, Slurm's own unit (overrides the default).",
)
def violators(partition: str, cpus_per_gpu: int | None, mem_per_gpu: int | None) -> None:
    """List running jobs holding more CPU or memory per GPU than the norm.

    Norms default to the per-partition policy your site sets under
    [partitions.limits]. For a partition with no configured policy, pass
    --cpus-per-gpu and --mem-per-gpu. Jobs with no GPUs are not evaluated. The
    partition is checked first whether or not norms were given, so a typo is an
    error rather than a partition where nothing is over the norm.

    Memory is in MiB throughout, which is what Slurm reports and what --mem takes
    by default, so --mem=360G and --mem=368640 are the same request. The OVER
    column gives each job's overage as a ratio, so a job a few percent past the
    norm does not read like one at ten times it. Slurm's scheduler has no per-GPU
    ratio of its own, so these norms are your site's. Where a site does enforce
    them, it is at submission through a job_submit plugin, and a job listed here
    then either predates the current policy or was shaped in a way that check did
    not catch.

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
    if not slurm.partition_nodes(partition):
        raise click.ClickException(f"partition '{partition}' does not exist, or has no nodes")
    default = slurm.PARTITION_LIMITS.get(partition)
    if cpus_per_gpu is None:
        cpus_per_gpu = default[0] if default else None
    if mem_per_gpu is None:
        mem_per_gpu = default[1] if default else None
    if (cpus_per_gpu is not None and cpus_per_gpu < 1) or (
        mem_per_gpu is not None and mem_per_gpu < 1
    ):
        raise click.ClickException(
            f"partition '{partition}' has a per-GPU policy of {cpus_per_gpu} CPU and "
            f"{mem_per_gpu} MiB, which cannot be a norm; fix [partitions.limits] in "
            "the site config, or pass --cpus-per-gpu and --mem-per-gpu"
        )
    if cpus_per_gpu is None or mem_per_gpu is None:
        known = ", ".join(sorted(slurm.PARTITION_LIMITS)) or "(none)"
        raise click.ClickException(
            f"no per-GPU policy configured for partition '{partition}'; partitions "
            f"with a policy: {known}. Pass --cpus-per-gpu and --mem-per-gpu for others."
        )

    rows = []
    for jobid, user, cpu, gpu, mem_mb in slurm.running_jobs_alloctres(partition):
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
