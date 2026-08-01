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
    shares. This changes the user's base association in the account, and their
    partition-scoped associations inherit it where they are set to parent. Prompts
    for confirmation unless -y.

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
    _write.check_names(user=user, account=account)
    _write.check_fairshare(share)
    if not yes:
        click.confirm(f"Set {user} fairshare to {share} in account {account}?", abort=True)
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
    if process.stream(cmd):
        raise click.ClickException(f"failed to set {user} fairshare in {account}")
