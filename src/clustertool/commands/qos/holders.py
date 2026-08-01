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
    carry it, and on which partitions. Use --by to collapse the output to just
    the distinct users or partitions (handy for scripting a grant or revoke).

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
    if not qoslib.qos_exists(qos_name):
        raise click.ClickException(f"QoS {qos_name} is not defined")
    if partition and not qoslib.partition_exists(partition, cluster=cluster):
        raise click.ClickException(f"no such partition: {partition}")
    try:
        rows = qoslib.holder_rows(
            qos_name, cluster=cluster, partition=partition, account_regex=account_regex
        )
    except re.error as exc:
        raise click.ClickException(f"invalid --account-regex: {exc}") from exc
    if not rows:
        click.echo(f"No user holds QoS {qos_name}.")
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
