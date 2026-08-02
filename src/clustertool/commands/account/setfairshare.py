"""account set-fairshare command."""

import click

from clustertool import completion, process
from clustertool.commands.account import _write
from clustertool.grouping import admin, keywords


@admin
@keywords("share", "adjust", "priority", "modify")
@click.command("set-fairshare")
@click.argument("user")
@click.argument("account", shell_complete=completion.complete_accounts)
@click.argument("share")
@click.option("-c", "--cluster", default=None, help="Slurm cluster (default: the site cluster).")
@click.option("-y", "--yes", is_flag=True, help="Skip the confirmation prompt.")
def set_fairshare(user: str, account: str, share: str, cluster: str | None, yes: bool) -> None:
    """Set a user's fairshare in an account (via sacctmgr).

    SHARE is an integer number of raw shares, or 'parent' to inherit the account's
    shares. man sacctmgr identifies an association by account, cluster, partition
    and user, so a condition naming three of those matches every value of the
    fourth: this sets the shares on the user's base association in the account and
    on every partition-scoped one they hold there, overwriting a partition
    association currently set to parent rather than leaving it to inherit. Each is
    listed with its current shares before you confirm. Prompts unless -y.

    Slurm operator, or a coordinator of the account; a site that sets
    DisableCoordDBD in slurmdbd.conf restricts this to operators.

    \b
    Use cases:
      - Adjust a member's fairshare weight within a lab.

    \b
    Inputs:
      USER           Username.
      ACCOUNT        Slurm account.
      SHARE          Raw shares (integer) or 'parent'.
      -c, --cluster  Slurm cluster (default: the site cluster).
      -y, --yes      Skip the confirmation prompt.
    """
    _write.check_names(user=user, account=account, cluster=cluster)
    _write.check_fairshare(share)
    rows = _write.associations(user, account, cluster)
    if not rows:
        raise click.ClickException(f"{user} has no association with account {account}")
    click.echo(f"Associations to set to fairshare {share} for {user} in {account}:")
    for partition, current_qos in rows:
        click.echo(f"  {partition or '(no partition)':<28} QoS: {current_qos or '-'}")
    if not yes:
        click.confirm(f"Set fairshare on {len(rows)} association(s)?", abort=True)
    cmd = [
        "sacctmgr",
        "-i",
        "modify",
        "user",
        "where",
        f"name={user}",
        f"account={account}",
        _write.cluster_scope(cluster),
        "set",
        f"fairshare={share}",
    ]
    process.passthrough(cmd, f"failed to set {user} fairshare in {account}")
