"""gpu status command."""

import click

from cluster_tools import slurm

_LABELS = {
    "idle": "Idle",
    "mixed": "Mixed",
    "alloc": "Alloc",
    "resv": "Resv",
    "drain": "Drain",
    "down": "Down",
}


@click.command("status")
def status() -> None:
    """Show Kempner GPU node status by type and state (via sinfo).

    Reads kempner_requeue, which spans every Kempner GPU node, and breaks the
    nodes down by GPU type (A100, H100, H200, RTX) and state. Idle, Mixed, and
    Alloc nodes are up; Resv is reserved; Drain is draining; Down is offline.

    \b
    Use cases:
      - See how many nodes of each GPU type are up, drained, or down.
      - Spot fleet health problems before submitting or debugging jobs.
    """
    rows = slurm.kempner_gpu_node_status()
    if not rows:
        click.echo("No GPU nodes found in kempner_requeue.")
        return
    buckets = slurm.GPU_STATUS_BUCKETS
    grand = sum(sum(counts.values()) for _, counts in rows)
    click.echo(f"Kempner GPU node status  (kempner_requeue, {grand} nodes)")
    click.echo("")
    click.echo(f"{'GPU type':<10}{'Total':>7}" + "".join(f"{_LABELS[b]:>7}" for b in buckets))
    totals = dict.fromkeys(buckets, 0)
    for gtype, counts in rows:
        n = sum(counts.values())
        for bucket in buckets:
            totals[bucket] += counts[bucket]
        click.echo(f"{gtype:<10}{n:>7}" + "".join(f"{counts[b]:>7}" for b in buckets))
    click.echo(f"{'Total':<10}{grand:>7}" + "".join(f"{totals[b]:>7}" for b in buckets))
    click.echo("")
    click.echo("Up = Idle + Mixed + Alloc.  Resv reserved, Drain draining, Down offline.")
