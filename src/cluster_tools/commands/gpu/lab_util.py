"""gpu lab-util command."""

import click

from cluster_tools import slurm


@click.command("lab-util")
@click.argument("account")
def lab_util(account: str) -> None:
    """Show one account's live GPU usage, by user and partition.

    Base-partition usage counts toward the per-account GPU cap. Priority and
    kempner_requeue usage is additive and does not count toward the cap.

    \b
    Use cases:
      - See who in a lab is consuming the shared GPU cap.
      - Check how close an account is to its cap and why jobs are pending.

    \b
    Inputs:
      ACCOUNT  Slurm account name (e.g. kempner_sham_lab).
    """
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
