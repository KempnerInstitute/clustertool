"""qos sync command."""

import re

import click

from cluster_tools import qos as qoslib
from cluster_tools.commands.qos import _gate
from cluster_tools.grouping import admin, keywords


@admin
@keywords("reconcile", "membership", "align", "priority", "account")
@click.command("sync")
@click.argument("qos_name")
@click.option("-a", "--account", required=True, help="Account whose membership drives the QoS.")
@click.option("-p", "--partition", required=True, help="Partition to reconcile on.")
@click.option("-c", "--cluster", default=None, help="Slurm cluster (default: the site cluster).")
@click.option("-x", "--execute", is_flag=True, help="Apply the change (default: dry run).")
@click.option("-y", "--yes", is_flag=True, help="Skip the confirmation prompt.")
def sync(
    qos_name: str,
    account: str,
    partition: str,
    cluster: str | None,
    execute: bool,
    yes: bool,
) -> None:
    """Reconcile a QoS's holders to an account's current membership (via sacctmgr).

    Grants the QoS to account members who lack it and revokes it from holders no
    longer in the account, on the given partition. Idempotent and cron-friendly.
    Dry run by default; re-run with --execute to apply, confirming unless --yes.
    Operator only.

    \b
    Use cases:
      - Keep a lab's priority QoS aligned with its Slurm account membership.

    \b
    Inputs:
      QOS_NAME         The QoS to reconcile.
      -a, --account    Account whose membership drives the QoS.
      -p, --partition  Partition to reconcile on.
      -c, --cluster    Slurm cluster (default: the site cluster).
      -x, --execute    Apply the change instead of previewing it.
      -y, --yes        Skip the confirmation prompt.
    """
    if not qoslib.qos_exists(qos_name):
        raise click.ClickException(f"QoS {qos_name} is not defined")
    if not qoslib.account_exists(account, cluster=cluster):
        raise click.ClickException(f"account {account} has no associations on this cluster")
    members = set(qoslib.account_members(account, cluster=cluster))
    account_regex = f"^{re.escape(account)}$"
    holders = {
        row[0]
        for row in qoslib.holder_rows(
            qos_name, cluster=cluster, partition=partition, account_regex=account_regex
        )
    }
    to_add = sorted(members - holders)
    to_del = sorted(holders - members)
    if not to_add and not to_del:
        click.echo(f"QoS {qos_name} is already in sync with {account} on {partition}.")
        return
    plan = []
    for user in to_add:
        plan += qoslib.grant_plan(user, account, partition, qos_name, qos_name, cluster)
    for user in to_del:
        plan += qoslib.revoke_plan(user, account, partition, qos_name, cluster)
    summary = f"Sync QoS {qos_name} on {partition}: +{len(to_add)} / -{len(to_del)} user(s)?"
    if _gate.apply(plan, execute, yes, summary):
        raise SystemExit(1)
