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
    change; a value of -1 clears one. With --per-user-only the gres/gpu entry of
    MaxTRESPA, GrpTRES and MaxTRES is cleared. Per man sacctmgr a -1 removes only
    the named TRES, so other TRES components of those limits, and every non-TRES
    limit such as MaxJobsPA or MaxWall, are left alone. An explicit -A, -G or -j
    overrides the clear for that one cap.
    Needs AdminLevel=Administrator, or root/SlurmUser. slurmdbd gates a QoS
    object at its super-user level, unlike an association, which an Operator may
    write: that is why qos grant and qos revoke ask for less than this does.

    \b
    Use cases:
      - Raise or lower a QoS's per-user GPU cap.
      - Reduce a QoS to per-user caps only with --per-user-only.
      - Set the per-account GPU cap, with -A. When QOS_NAME is the site base
        QoS, that is the cap 'gpu usage' reports each account against.

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
    summary = f"Modify QoS {qos_name}: {', '.join(specs)}?"
    if _gate.apply(plan, execute, yes, summary):
        raise SystemExit(1)
    if execute:
        _limits.report(qos_name)
