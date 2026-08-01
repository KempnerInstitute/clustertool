"""qos modify command."""

import click

from clustertool import qos as qoslib
from clustertool.commands.qos import _gate, _limits
from clustertool.grouping import admin, keywords


@admin
@keywords("change", "tune", "limits", "tres", "cap")
@click.command("modify")
@click.argument("qos_name")
@_limits.limit_options
@click.option(
    "--per-user-only",
    is_flag=True,
    help="Also clear the per-account, group, and per-job GPU caps.",
)
@click.option("-x", "--execute", is_flag=True, help="Apply the change (default: dry run).")
@click.option("-y", "--yes", is_flag=True, help="Skip the confirmation prompt.")
def modify(
    qos_name: str,
    gpu_per_user: int | None,
    node_per_user: int | None,
    group_gpu: int | None,
    job_gpu: int | None,
    jobs_per_user: int | None,
    account_gpu: int | None,
    per_user_only: bool,
    execute: bool,
    yes: bool,
) -> None:
    """Change an existing QoS's limits (via sacctmgr).

    Dry run by default: prints the sacctmgr command and changes nothing. Re-run
    with --execute to apply, confirming unless --yes. Only the limits you pass
    change; a value of -1 clears one. With --per-user-only the per-account, group,
    and per-job GPU caps are all cleared, so only the per-user caps remain.
    Slurm or system admin only.

    \b
    Use cases:
      - Raise or lower a QoS's per-user GPU cap.
      - Reduce a QoS to per-user caps only with --per-user-only.
      - Set the per-account GPU cap that 'gpu usage' reports against, with -A.

    \b
    Inputs:
      QOS_NAME        Name of an existing QoS.
      -g/-n/-A/-G/-j/-J
                      Limit caps (see each option; -1 clears).
      --per-user-only Also clear the per-account, group, and per-job GPU caps.
      -x, --execute   Apply the change instead of previewing it.
      -y, --yes       Skip the confirmation prompt.
    """
    if per_user_only:
        if group_gpu is None:
            group_gpu = -1
        if job_gpu is None:
            job_gpu = -1
        if account_gpu is None:
            account_gpu = -1
    specs = _limits.resolve_specs(
        gpu_per_user, node_per_user, group_gpu, job_gpu, jobs_per_user, account_gpu
    )
    if not qoslib.qos_exists(qos_name):
        raise click.ClickException(f"QoS {qos_name} does not exist; use 'qos create' to add it")
    plan = [["sacctmgr", "-i", "modify", "qos", qos_name, "set", *specs]]
    summary = f"Modify QoS {qos_name} ({len(specs)} limit change(s))?"
    if _gate.apply(plan, execute, yes, summary):
        raise SystemExit(1)
