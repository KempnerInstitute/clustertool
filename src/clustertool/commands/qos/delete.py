"""qos delete command."""

import click

from clustertool import qos as qoslib
from clustertool.commands.qos import _gate
from clustertool.grouping import admin, keywords


def _describe(references: dict[str, list[str]]) -> str:
    """Return 'part (QoS)' for each partition, naming the setting that references it.

    QoS and AllowQos let jobs use the QoS while DenyQos bars them, so which
    setting names it decides what deleting it would do.
    """
    return ", ".join(f"{name} ({'/'.join(settings)})" for name, settings in references.items())


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
    carries it. Clear those first. The refusal names which setting, since QoS and
    AllowQos let jobs use it while DenyQos bars them, and an association that sets
    no QoS list of its own inherits its parent's.
    Needs AdminLevel=Administrator, or root/SlurmUser. slurmdbd gates a QoS
    object at its super-user level, unlike an association, which an Operator may
    write: that is why qos grant and qos revoke ask for less than this does.

    \b
    Use cases:
      - Retire a QoS definition that is no longer assigned to anyone.

    \b
    Inputs:
      QOS_NAME       Name of the QoS to delete.
      -x, --execute  Apply the change instead of previewing it.
      -y, --yes      Skip the confirmation prompt.
    """
    if not qoslib.valid_name(qos_name):
        raise click.ClickException(
            f"invalid QoS name {qos_name!r}: use letters, digits, and . _ - only"
        )
    if not qoslib.qos_exists(qos_name):
        click.echo(f"QoS {qos_name} does not exist; nothing to do.")
        return
    holders = qoslib.any_holders(qos_name)
    if holders:
        accounts = {line.split("|")[1] for line in holders if len(line.split("|")) > 1}
        raise click.ClickException(
            f"QoS {qos_name} is still held by {len(holders)} association(s) across "
            f"{len(accounts)} account(s); an association that sets no QoS list of its "
            "own inherits its parent's, so a count this large usually means one "
            "parent sets it. Clear it there first"
        )
    references = qoslib.partition_references(qos_name)
    if references:
        raise click.ClickException(
            f"QoS {qos_name} is configured on partition(s) {_describe(references)}; "
            "deleting it would change what those partitions allow. Remove it from "
            "the partition configuration first"
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
