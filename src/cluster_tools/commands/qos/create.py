"""qos create command."""

import click

from cluster_tools import qos as qoslib
from cluster_tools.commands.qos import _gate, _limits
from cluster_tools.grouping import admin, keywords


@admin
@keywords("add", "provision", "limits", "tres", "cap")
@click.command("create")
@click.argument("qos_name")
@_limits.limit_options
@click.option("-x", "--execute", is_flag=True, help="Apply the change (default: dry run).")
@click.option("-y", "--yes", is_flag=True, help="Skip the confirmation prompt.")
def create(
    qos_name: str,
    gpu_per_user: int | None,
    node_per_user: int | None,
    group_gpu: int | None,
    job_gpu: int | None,
    jobs_per_user: int | None,
    execute: bool,
    yes: bool,
) -> None:
    """Create a QoS with the given limits, updating it if it already exists.

    Dry run by default: prints the sacctmgr commands and changes nothing. Re-run
    with --execute to apply, confirming unless --yes. Give at least one limit; a
    value of -1 clears that limit. Slurm or system admin only.

    \b
    Use cases:
      - Provision a new priority QoS with per-user and total GPU caps.

    \b
    Inputs:
      QOS_NAME       Name of the QoS to create or update.
      -g/-n/-G/-j/-J Limit caps (see each option; -1 clears).
      -x, --execute  Apply the change instead of previewing it.
      -y, --yes      Skip the confirmation prompt.
    """
    specs = _limits.resolve_specs(gpu_per_user, node_per_user, group_gpu, job_gpu, jobs_per_user)
    if not qoslib.valid_name(qos_name):
        raise click.ClickException(
            f"invalid QoS name {qos_name!r}: use letters, digits, and . _ - only"
        )
    plan = []
    if not qoslib.qos_exists(qos_name):
        plan.append(["sacctmgr", "-i", "add", "qos", qos_name])
    plan.append(["sacctmgr", "-i", "modify", "qos", qos_name, "set", *specs])
    summary = f"Create or update QoS {qos_name} with {len(specs)} limit(s)?"
    if _gate.apply(plan, execute, yes, summary):
        raise SystemExit(1)
