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
    deletes the QoS definition. Where the QoS is an association's only one, the
    revoke deletes that association outright rather than editing it, which drops
    its recorded usage. Refuses up front if the QoS is named in any partition's
    configuration, if any queued or running job carries it, or if any association
    still holding it would not be revoked by this sweep, such as an account-level
    one, one with no partition, or one on another cluster; it lists them. The
    delete runs only after every revoke in the plan succeeded. Dry run by default;
    re-run with --execute to apply, confirming unless --yes.
    Needs AdminLevel=Administrator, or root/SlurmUser. slurmdbd gates a QoS
    object at its super-user level, unlike an association, which an Operator may
    write: that is why qos grant and qos revoke ask for less than this does.

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
    if partition != "all" and not qoslib.partition_known(partition, cluster=cluster):
        raise click.ClickException(f"no such partition: {partition}, and no association carries it")
    if not qoslib.qos_exists(qos_name):
        click.echo(f"QoS {qos_name} does not exist; nothing to do.")
        return
    references = qoslib.partition_references(qos_name, cluster=cluster)
    if references:
        listed = ", ".join(f"{name} ({'/'.join(kinds)})" for name, kinds in references.items())
        raise click.ClickException(
            f"QoS {qos_name} is configured on partition(s) {listed}; deleting it "
            "would change what those partitions allow. Remove it from the partition "
            "configuration first"
        )
    live = qoslib.jobs_using(qos_name, cluster=cluster)
    if live:
        raise click.ClickException(
            f"QoS {qos_name} is carried by {live} queued or running job(s); "
            "let them finish or cancel them first"
        )
    plan = qoslib.revoke_targets_plan(
        qos_name, ["all"], partition, cluster=cluster, account_regex=account_regex
    )
    uncovered = qoslib.uncovered_holders(qos_name, plan)
    if uncovered:
        shown = "\n".join(f"  {row}" for row in uncovered[:10])
        more = f"\n  ... and {len(uncovered) - 10} more" if len(uncovered) > 10 else ""
        raise click.ClickException(
            f"QoS {qos_name} is held by {len(uncovered)} association(s) that this sweep "
            f"would not revoke (Cluster|Account|User|Partition):\n{shown}{more}\n"
            "Revoke those first, or widen --partition and --account-regex"
        )
    plan.append(["sacctmgr", "-i", "delete", "qos", qos_name])
    summary = f"Revoke QoS {qos_name} from all holders on {partition} and delete it?"
    if _gate.apply(plan, execute, yes, summary):
        raise SystemExit(1)
