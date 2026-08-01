"""qos revoke command."""

import re

import click

from clustertool import qos as qoslib
from clustertool.commands.qos import _gate
from clustertool.grouping import admin, keywords


@admin
@keywords("remove", "unassign", "take", "priority", "user")
@click.command("revoke")
@click.argument("qos_name")
@click.option(
    "-u",
    "--users",
    multiple=True,
    required=True,
    help="Users, or 'all' (repeatable, comma-separated).",
)
@click.option("-p", "--partition", required=True, help="Partition, or 'all'.")
@click.option("-c", "--cluster", default=None, help="Slurm cluster (default: the site cluster).")
@click.option(
    "-r",
    "--account-regex",
    default="^",
    show_default=True,
    help="Only accounts matching this regex.",
)
@click.option("-x", "--execute", is_flag=True, help="Apply the change (default: dry run).")
@click.option("-y", "--yes", is_flag=True, help="Skip the confirmation prompt.")
def revoke(
    qos_name: str,
    users: tuple[str, ...],
    partition: str,
    cluster: str | None,
    account_regex: str,
    execute: bool,
    yes: bool,
) -> None:
    """Remove a priority QoS from users on a partition.

    Removes the QoS from each matching association, moving the default off it
    first when needed and deleting the association if the QoS was its only entry.
    Pass 'all' for --users or --partition to act on every current holder. Dry run
    by default; re-run with --execute to apply, confirming unless --yes.
    Slurm operator, or a coordinator of the account; a site that sets
    DisableCoordDBD in slurmdbd.conf restricts this to operators.

    \b
    Use cases:
      - Revoke a priority QoS from users who no longer need it.
      - Clear a QoS off every holder with -u all -p all.

    \b
    Inputs:
      QOS_NAME            The QoS to remove.
      -u, --users         Users, or 'all' (repeatable, comma-separated).
      -p, --partition     Partition, or 'all'.
      -c, --cluster       Slurm cluster (default: the site cluster).
      -r, --account-regex Only accounts matching this regex (default: all).
      -x, --execute       Apply the change instead of previewing it.
      -y, --yes           Skip the confirmation prompt.
    """
    try:
        re.compile(account_regex)
    except re.error as exc:
        raise click.ClickException(f"invalid --account-regex: {exc}") from exc
    if not qoslib.qos_exists(qos_name):
        raise click.ClickException(f"QoS {qos_name} is not defined")
    user_list = qoslib.flatten_users(users)
    for name in user_list:
        if name != "all" and not qoslib.valid_name(name):
            raise click.ClickException(f"invalid --users {name!r}: a name cannot contain a comma")
    if partition != "all" and not qoslib.valid_name(partition):
        raise click.ClickException(
            f"invalid --partition {partition!r}: a name cannot contain a comma"
        )
    if "all" in user_list and len(user_list) > 1:
        raise click.UsageError("-u all must be used on its own")
    if partition != "all" and not qoslib.partition_known(partition, cluster=cluster):
        raise click.ClickException(f"no such partition: {partition}, and no association carries it")
    plan = qoslib.revoke_targets_plan(
        qos_name, user_list, partition, cluster=cluster, account_regex=account_regex
    )
    if not plan:
        click.echo("Nothing to change.")
        return
    summary = f"Revoke QoS {qos_name} on {partition} ({len(plan)} command(s))?"
    if _gate.apply(plan, execute, yes, summary):
        raise SystemExit(1)
