"""account add-user command."""

import click

from clustertool import completion, process, site
from clustertool.commands.account import _write
from clustertool.grouping import admin, keywords


@admin
@keywords("grant", "join", "access", "enroll")
@click.command("add-user")
@click.argument("user")
@click.argument("account", shell_complete=completion.complete_accounts)
@click.option(
    "--fairshare",
    default=None,
    help="Fairshare value (default: the site's grant_fairshare).",
)
@click.option("-c", "--cluster", default=None, help="Slurm cluster (default: the site cluster).")
@click.option("-y", "--yes", is_flag=True, help="Skip the confirmation prompt.")
def add_user(
    user: str, account: str, fairshare: str | None, cluster: str | None, yes: bool
) -> None:
    """Add a user to a fairshare account (via sacctmgr).

    Creates the account's base association for the user. The fairshare value
    defaults to [qos].grant_fairshare from the site config, the same value that
    'qos grant' gives the associations it creates. Prompts for confirmation unless
    -y.

    Slurm operator, or a coordinator of the account; a site that sets
    DisableCoordDBD in slurmdbd.conf restricts this to operators.

    \b
    Use cases:
      - Grant a new lab member access to the lab's Slurm account.

    \b
    Inputs:
      USER           Username to add.
      ACCOUNT        Slurm account to add them to.
      --fairshare    Fairshare value (default: the site's grant_fairshare).
      -c, --cluster  Slurm cluster (default: the site cluster).
      -y, --yes      Skip the confirmation prompt.
    """
    _write.check_names(user=user, account=account)
    share = fairshare or site.qos_grant_fairshare()
    _write.check_fairshare(share)
    if not yes:
        click.confirm(f"Add user {user} to account {account} (fairshare={share})?", abort=True)
    cmd = [
        "sacctmgr",
        "-i",
        "add",
        "user",
        f"name={user}",
        f"account={account}",
        _write.cluster_scope(cluster),
        f"fairshare={share}",
    ]
    process.passthrough(cmd, f"failed to add {user} to {account}")
