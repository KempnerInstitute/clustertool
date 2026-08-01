"""qos delete command."""

import click

from clustertool import qos as qoslib
from clustertool.commands.qos import _gate
from clustertool.grouping import admin, keywords


@admin
@keywords("remove", "drop", "retire", "definition")
@click.command("delete")
@click.argument("qos_name")
@click.option("-x", "--execute", is_flag=True, help="Apply the change (default: dry run).")
@click.option("-y", "--yes", is_flag=True, help="Skip the confirmation prompt.")
def delete(qos_name: str, execute: bool, yes: bool) -> None:
    """Delete a QoS definition, refusing while it is still referenced (via sacctmgr).

    Dry run by default: prints the sacctmgr command and changes nothing. Re-run
    with --execute to apply, confirming unless --yes. Refuses while the QoS is
    still in force: if any association on any cluster lists it, if any partition's
    QoS, AllowQos, or DenyQos setting names it, or if any queued or running job
    carries it. Clear those first.
    Needs AdminLevel=Operator or above, or
    root/SlurmUser: SchedMD documents an operator as able to add, modify and
    remove any database object, and a QoS is one.

    \b
    Use cases:
      - Retire a QoS definition that is no longer assigned to anyone.

    \b
    Inputs:
      QOS_NAME       Name of the QoS to delete.
      -x, --execute  Apply the change instead of previewing it.
      -y, --yes      Skip the confirmation prompt.
    """
    if not qoslib.qos_exists(qos_name):
        click.echo(f"QoS {qos_name} does not exist; nothing to do.")
        return
    holders = qoslib.any_holders(qos_name)
    if holders:
        raise click.ClickException(
            f"QoS {qos_name} is still held by {len(holders)} association(s); "
            "remove it from those associations first"
        )
    partitions = qoslib.partitions_referencing(qos_name)
    if partitions:
        raise click.ClickException(
            f"QoS {qos_name} is configured on partition(s) {', '.join(partitions)}; "
            "deleting it would drop the limits those partitions apply. Remove it "
            "from the partition configuration first"
        )
    live = qoslib.jobs_using(qos_name)
    if live:
        raise click.ClickException(
            f"QoS {qos_name} is carried by {live} queued or running job(s); "
            "let them finish or cancel them first"
        )
    plan = [["sacctmgr", "-i", "delete", "qos", qos_name]]
    if _gate.apply(plan, execute, yes, f"Delete QoS {qos_name}?"):
        raise SystemExit(1)
