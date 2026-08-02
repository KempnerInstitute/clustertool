"""account add-user command."""

import click

from clustertool import completion, process, site, slurm
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

    The user and the account are both checked first. sacctmgr does warn about a
    name with no uid, but only at the confirmation prompt that -i skips, and it
    reports an account that does not exist and a user who is already a member
    with the same text, so a typo would otherwise create a junk association or
    read as a missing account.

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
    _write.check_names(user=user, account=account, cluster=cluster)
    share = fairshare if fairshare is not None else site.qos_grant_fairshare()
    _write.check_fairshare(share)
    if not slurm.user_exists(user):
        raise click.ClickException(
            f"no such user on this host: {user}. sacctmgr would create an association "
            "for a name with no uid, and the person would still have no access"
        )
    if not slurm.account_exists(account):
        raise click.ClickException(f"account '{account}' does not exist")
    if _write.associations(user, account, cluster):
        raise click.ClickException(
            f"{user} is already a member of account {account}. To change their "
            f"fairshare, use 'clustertool account set-fairshare {user} {account}'"
        )
    scope = _write.cluster_scope(cluster)
    where = scope.split("=", 1)[1]
    if not yes:
        click.confirm(
            f"Add user {user} to account {account} on {where} (fairshare={share})?", abort=True
        )
    cmd = [
        "sacctmgr",
        "-i",
        "add",
        "user",
        f"name={user}",
        f"account={account}",
        scope,
        f"fairshare={share}",
    ]
    process.passthrough(cmd, f"failed to add {user} to {account}")
