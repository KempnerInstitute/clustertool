"""qos grant command."""

import re

import click

from clustertool import qos as qoslib
from clustertool.commands.qos import _gate
from clustertool.grouping import admin, keywords


def _check_names(**values: str) -> None:
    """Reject a name sacctmgr would read as a list, which would widen the change."""
    for label, value in values.items():
        if not qoslib.valid_name(value):
            raise click.ClickException(
                f"invalid --{label.replace('_', '-')} {value!r}: a name cannot contain "
                "a comma or whitespace, which sacctmgr would read as a list"
            )


@admin
@keywords("assign", "add", "priority", "give", "user")
@click.command("grant")
@click.argument("qos_name")
@click.option(
    "-u", "--users", multiple=True, required=True, help="Users (repeatable, comma-separated)."
)
@click.option("-p", "--partition", required=True, help="Partition to grant the QoS on.")
@click.option(
    "-d", "--default-qos", default=None, help="Default QoS to set (default: the granted QoS)."
)
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
def grant(
    qos_name: str,
    users: tuple[str, ...],
    partition: str,
    default_qos: str | None,
    cluster: str | None,
    account_regex: str,
    execute: bool,
    yes: bool,
) -> None:
    """Grant a priority QoS to users across their matching accounts on a partition.

    For each user, adds the QoS to every association whose account matches the
    regex, sets the default QoS, and strips the catch-all and partition-named
    QoS so the granted one takes effect. Missing associations are created. Dry
    run by default; re-run with --execute to apply, confirming unless --yes.
    Slurm operator, or a coordinator of the account; a site that sets
    DisableCoordDBD in slurmdbd.conf restricts this to operators.

    \b
    Use cases:
      - Give a set of users a priority QoS on a GPU partition.

    \b
    Inputs:
      QOS_NAME            The QoS to grant.
      -u, --users         Users (repeatable, comma-separated).
      -p, --partition     Partition to grant the QoS on.
      -d, --default-qos   Default QoS to set (default: the granted QoS).
      -c, --cluster       Slurm cluster (default: the site cluster).
      -r, --account-regex Only accounts matching this regex (default: all).
      -x, --execute       Apply the change instead of previewing it.
      -y, --yes           Skip the confirmation prompt.
    """
    default_qos = default_qos or qos_name
    _check_names(partition=partition)
    for user in qoslib.flatten_users(users):
        _check_names(users=user)
    try:
        re.compile(account_regex)
    except re.error as exc:
        raise click.ClickException(f"invalid --account-regex: {exc}") from exc
    if not qoslib.qos_exists(qos_name):
        raise click.ClickException(f"QoS {qos_name} is not defined")
    if not qoslib.partition_exists(partition, cluster=cluster):
        raise click.ClickException(f"no such partition: {partition}")
    if default_qos != qos_name and not qoslib.qos_exists(default_qos):
        raise click.ClickException(f"default QoS {default_qos} is not defined")
    plan = []
    for user in qoslib.flatten_users(users):
        accounts = qoslib.get_accounts(user, cluster=cluster, account_regex=account_regex)
        if not accounts:
            click.echo(f"# {user}: no matching accounts; skipping", err=True)
            continue
        for account in accounts:
            plan += qoslib.grant_plan(user, account, partition, qos_name, default_qos, cluster)
    if not plan:
        click.echo("Nothing to change.")
        return
    summary = f"Grant QoS {qos_name} on {partition} ({len(plan)} command(s))?"
    if _gate.apply(plan, execute, yes, summary):
        raise SystemExit(1)
