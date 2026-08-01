"""account set-fairshare command."""

import click

from clustertool import completion, process
from clustertool.grouping import admin, keywords


@admin
@keywords("share", "adjust", "priority", "modify")
@click.command("set-fairshare")
@click.argument("user")
@click.argument("account", shell_complete=completion.complete_accounts)
@click.argument("share")
@click.option("-y", "--yes", is_flag=True, help="Skip the confirmation prompt.")
def set_fairshare(user: str, account: str, share: str, yes: bool) -> None:
    """Set a user's fairshare in an account (via sacctmgr). Operator or coordinator only.

    SHARE is an integer number of raw shares, or 'parent' to inherit the
    account's shares. Prompts for confirmation unless -y.

    \b
    Use cases:
      - Adjust a member's fairshare weight within a lab.

    \b
    Inputs:
      USER       Username.
      ACCOUNT    Slurm account.
      SHARE      Raw shares (integer) or 'parent'.
      -y, --yes  Skip the confirmation prompt.
    """
    if not yes:
        click.confirm(f"Set {user} fairshare to {share} in account {account}?", abort=True)
    code = process.stream(
        [
            "sacctmgr",
            "-i",
            "modify",
            "user",
            "where",
            f"name={user}",
            f"account={account}",
            "set",
            f"fairshare={share}",
        ]
    )
    if code:
        raise SystemExit(code)
