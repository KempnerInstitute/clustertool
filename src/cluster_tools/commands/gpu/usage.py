"""gpu usage command."""

import click

from cluster_tools import slurm


@click.command("usage")
@click.argument("account", required=False)
def usage(account: str | None) -> None:
    """Show live base-partition GPU usage, for all labs or one lab.

    Without ACCOUNT, rank every account by base-partition GPU usage (the usage
    that counts toward each account's cap), highest first. With ACCOUNT, break
    that account's usage down by user and partition, plus additive priority and
    kempner_requeue usage that does not count toward the cap.

    \b
    Use cases:
      - See which labs are the heaviest GPU users right now (no argument).
      - See who in a lab is using its cap and why jobs pend (with ACCOUNT).

    \b
    Inputs:
      ACCOUNT  Slurm account name (e.g. kempner_sham_lab). Omit for all labs.
    """
    if account is None:
        _all_labs()
    else:
        _one_lab(account)


def _all_labs() -> None:
    """Rank every account by base-partition GPU usage, highest first."""
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


def _one_lab(account: str) -> None:
    """Show one account's usage by user and partition."""
    if not slurm.account_exists(account):
        raise click.ClickException(f"account '{account}' not found")

    cap = slurm.account_cap()
    click.echo(f"Lab GPU usage (running jobs) -- account: {account}")
    click.echo()
    _section(
        f"Base partitions -- COUNT toward the {cap}-GPU account cap",
        account,
        slurm.BASE_PARTITIONS,
        in_cap=True,
        cap=cap,
    )
    _section(
        "Priority partitions -- additive (outside the cap)",
        account,
        slurm.priority_partitions(),
        in_cap=False,
        cap=cap,
    )
    _section(
        "kempner_requeue -- additive (outside the cap)",
        account,
        [slurm.REQUEUE_PARTITION],
        in_cap=False,
        cap=cap,
    )


def _section(title: str, account: str, partitions, in_cap: bool, cap: int) -> None:
    """Print one usage section for an account on a set of partitions."""
    rows = slurm.gpu_rows(account, partitions)
    click.echo(f"== {title} ==")
    if not rows:
        click.echo("  (no running GPU jobs)")
        click.echo()
        return

    by_user: dict[str, int] = {}
    by_partition: dict[str, int] = {}
    for user, partition, gpus in rows:
        by_user[user] = by_user.get(user, 0) + gpus
        by_partition[partition] = by_partition.get(partition, 0) + gpus

    click.echo("  by user:")
    for user, gpus in sorted(by_user.items(), key=lambda item: item[1], reverse=True):
        click.echo(f"    {user:<18} {gpus:4d} GPU")
    click.echo("  by partition:")
    for partition, gpus in sorted(by_partition.items()):
        click.echo(f"    {partition:<24} {gpus:4d} GPU")

    total = sum(by_user.values())
    if in_cap:
        percent = total * 100 // cap if cap else 0
        click.echo(f"  ACCOUNT TOTAL: {total} / {cap} GPU  ({percent}% of the cap)")
        pending = slurm.pending_at_cap(account, partitions)
        if pending:
            click.echo(
                f"  note: {pending} job(s) pending because the lab is at the cap "
                "(MaxGRESPerAccount)"
            )
    else:
        click.echo(f"  ACCOUNT TOTAL: {total} GPU  (additive -- NOT counted toward the {cap} cap)")
    click.echo()
