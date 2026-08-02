"""qos holders command."""

import re

import click

from clustertool import qos as qoslib
from clustertool.grouping import keywords


@keywords("who", "assigned", "priority", "users", "membership")
@click.command("holders")
@click.argument("qos_name")
@click.option("-p", "--partition", default=None, help="Restrict to one partition.")
@click.option("-c", "--cluster", default=None, help="Slurm cluster (default: the site cluster).")
@click.option(
    "-r",
    "--account-regex",
    default="^",
    show_default=True,
    help="Only accounts matching this regex.",
)
@click.option(
    "--by",
    type=click.Choice(["all", "user", "partition"]),
    default="all",
    show_default=True,
    help="Show full rows, or just the distinct users or partitions.",
)
def holders(
    qos_name: str, partition: str | None, cluster: str | None, account_regex: str, by: str
) -> None:
    """List the users and partitions that hold a QoS (via sacctmgr).

    Answers the inverse of account limits: given a QoS, which user associations
    carry it, and on which partitions. Use --by to collapse the output to just the
    distinct users or partitions (handy for scripting a grant or revoke).

    A QoS can also be held without a partition, on an account's or a user's base
    association. Those do not appear in the table, so when no partition-scoped
    holder exists the command falls back to listing them; --by still collapses
    that list, and the explanatory line goes to stderr so a pipe stays clean.

    \b
    Use cases:
      - See who currently holds a priority QoS before changing it.
      - List the partitions a QoS is attached to.

    \b
    Inputs:
      QOS_NAME            The QoS to look up.
      -p, --partition     Restrict to one partition.
      -c, --cluster       Slurm cluster (default: the site cluster).
      -r, --account-regex Only accounts matching this regex (default: all).
      --by                all rows, or distinct user or partition.
    """
    if cluster and not qoslib.cluster_exists(cluster):
        raise click.ClickException(f"no such cluster: {cluster}")
    if not qoslib.qos_exists(qos_name):
        raise click.ClickException(f"QoS {qos_name} is not defined")
    if partition and not qoslib.partition_known(partition, cluster=cluster):
        raise click.ClickException(f"no such partition: {partition}, and no association carries it")
    try:
        rows = qoslib.holder_rows(
            qos_name, cluster=cluster, partition=partition, account_regex=account_regex
        )
    except re.error as exc:
        raise click.ClickException(f"invalid --account-regex: {exc}") from exc
    if not rows:
        narrowed = [
            label
            for label, value in (
                ("--cluster", cluster),
                ("--partition", partition),
                ("--account-regex", account_regex if account_regex != "^" else None),
            )
            if value
        ]
        where = f" matching {', '.join(narrowed)}" if narrowed else ""
        others = qoslib.any_holders(qos_name)
        if not others:
            click.echo(f"Nothing holds QoS {qos_name}.")
            return
        click.echo(
            f"No user holds QoS {qos_name} on a partition-scoped association{where}. "
            f"Elsewhere {len(others)} association(s) do carry it, which the flags you "
            "gave do not select, so they are listed on stderr rather than as a result "
            "(Cluster|Account|User|Partition):",
            err=True,
        )
        for line in others[:20]:
            click.echo(f"  {line}", err=True)
        if len(others) > 20:
            click.echo(f"  ... and {len(others) - 20} more", err=True)
        return
    if by == "user":
        for user in sorted({r[0] for r in rows}):
            click.echo(user)
        return
    if by == "partition":
        for part in sorted({r[2] for r in rows}):
            click.echo(part)
        return
    user_w = max(len("USER"), max(len(r[0]) for r in rows))
    acct_w = max(len("ACCOUNT"), max(len(r[1]) for r in rows))
    click.echo(f"{'USER':<{user_w}}  {'ACCOUNT':<{acct_w}}  PARTITION")
    for user, account, part in sorted(rows):
        click.echo(f"{user:<{user_w}}  {account:<{acct_w}}  {part}")
