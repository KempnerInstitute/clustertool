"""qos retire command."""

import re

import click

from clustertool import qos as qoslib
from clustertool.commands.qos import _gate
from clustertool.grouping import admin, keywords


@admin
@keywords("remove", "delete", "decommission", "priority", "retire")
@click.command("retire")
@click.argument("qos_name")
@click.option("-p", "--partition", required=True, help="Partition to clear the QoS from, or 'all'.")
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
def retire(
    qos_name: str,
    partition: str,
    cluster: str | None,
    account_regex: str,
    execute: bool,
    yes: bool,
) -> None:
    """Remove a QoS from all its holders on a partition, then delete it.

    Revokes the QoS from every holder on the partition (or all partitions), then
    deletes the QoS definition. The delete runs only if every revoke succeeded,
    so a QoS still held elsewhere (an account-level or out-of-scope association)
    is left in place. Dry run by default; re-run with --execute to apply,
    confirming unless --yes. Slurm or system admin only.

    \b
    Use cases:
      - Fully decommission a priority QoS in one step.

    \b
    Inputs:
      QOS_NAME            The QoS to retire.
      -p, --partition     Partition to clear, or 'all'.
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
        click.echo(f"QoS {qos_name} does not exist; nothing to do.")
        return
    plan = qoslib.revoke_targets_plan(
        qos_name, ["all"], partition, cluster=cluster, account_regex=account_regex
    )
    plan.append(["sacctmgr", "-i", "delete", "qos", qos_name])
    summary = f"Revoke QoS {qos_name} from all holders on {partition} and delete it?"
    if _gate.apply(plan, execute, yes, summary):
        raise SystemExit(1)
