"""gpu status command."""

import click

from clustertool import qos, site, slurm
from clustertool.grouping import keywords

_LABELS = {
    "idle": "IDLE",
    "mixed": "MIXED",
    "alloc": "ALLOC",
    "resv": "RESV",
    "drain": "DRAIN",
    "down": "DOWN",
}


@keywords("health", "fleet", "broken")
@click.command("status")
def status() -> None:
    """Show GPU node status by type and state (via sinfo).

    Reads the site's requeue partition, which spans every GPU node, and breaks the
    nodes down by GPU type and state. Idle, Mixed, and Alloc nodes are up; Resv is
    reserved; Drain is draining; Down is offline. Each column aggregates the
    related Slurm states: a node planned by the backfill scheduler counts as Idle,
    one still completing a job as Alloc, one held for maintenance as Resv,
    and one with invalid registered resources as Down.

    \b
    Use cases:
      - See how many nodes of each GPU type are up, drained, or down.
      - Spot fleet health problems before submitting or debugging jobs.
    """
    partition = site.requeue_partition()
    if not partition:
        raise click.ClickException(
            "no requeue partition configured; set [partitions].requeue in your site config"
        )
    rows = slurm.gpu_node_status()
    if not rows:
        if not qos.partition_exists(partition):
            raise click.ClickException(
                f"partition '{partition}' does not exist; check [partitions].requeue "
                "in your site config"
            )
        click.echo(f"No GPU nodes found in {partition}.")
        return
    buckets = slurm.GPU_STATUS_BUCKETS
    grand = sum(sum(counts.values()) for _, counts in rows)
    click.echo(f"GPU node status  ({partition}, {grand} nodes)")
    click.echo("")
    width = max(10, *(len(gtype) for gtype, _ in rows)) + 1
    click.echo(f"{'GPU TYPE':<{width}}{'TOTAL':>7}" + "".join(f"{_LABELS[b]:>7}" for b in buckets))
    totals = dict.fromkeys(buckets, 0)
    for gtype, counts in rows:
        n = sum(counts.values())
        for bucket in buckets:
            totals[bucket] += counts[bucket]
        click.echo(f"{gtype:<{width}}{n:>7}" + "".join(f"{counts[b]:>7}" for b in buckets))
    click.echo(f"{'TOTAL':<{width}}{grand:>7}" + "".join(f"{totals[b]:>7}" for b in buckets))
    click.echo("")
    click.echo("Up = IDLE + MIXED + ALLOC.  RESV reserved, DRAIN draining, DOWN offline.")
