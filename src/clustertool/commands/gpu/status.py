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
    reserved; Drain is drained or draining; Down is offline. Nodes with no GPU are
    skipped, since the requeue partition is configured rather than guaranteed to
    hold only GPU nodes. Each column aggregates the related Slurm states: an idle
    node the backfill scheduler has planned counts as Idle and a partly busy one
    stays Mixed,
    one still completing a job as Alloc, one held for maintenance as Resv, and one
    with invalid registered resources as Down. A node not responding counts as
    Down whatever its base state, since man sinfo says it will not be allocated
    any new work; one already drained or reserved keeps that column instead, which
    says the same about availability and names the reason.

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
    click.echo(
        "Up = IDLE + MIXED + ALLOC.  RESV reserved, DRAIN drained or draining, DOWN offline."
    )
