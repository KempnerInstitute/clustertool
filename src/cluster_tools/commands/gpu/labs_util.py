"""gpu labs-util command."""

import click

from cluster_tools import slurm


@click.command("labs-util")
def labs_util() -> None:
    """Rank every account by live base-partition GPU usage, highest first.

    Only base-partition usage is shown, which is the usage that counts toward
    each account's GPU cap.

    \b
    Use cases:
      - See which labs are the heaviest GPU users right now.
      - Get a cluster-wide view of base-partition GPU allocation.

    \b
    Inputs:
      none
    """
    cap = slurm.account_cap()
    totals = slurm.gpu_by_account(slurm.BASE_PARTITIONS)

    click.echo(
        f"Base-partition GPU usage by account (counts toward the {cap}-GPU cap) -- highest first"
    )
    click.echo()
    if not totals:
        click.echo("  (no running GPU jobs on the base partitions)")
        return

    for account, gpus in sorted(totals.items(), key=lambda item: item[1], reverse=True):
        click.echo(f"  {account:<28} {gpus:3d}/{cap}")
    total = sum(totals.values())
    click.echo(f"  {'':<28} ----")
    click.echo(f"  {'TOTAL':<28} {total:3d} GPU in use across {len(totals)} account(s)")
