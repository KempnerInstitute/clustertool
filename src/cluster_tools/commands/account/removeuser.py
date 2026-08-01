"""account remove-user command."""

import click

from cluster_tools import completion, process
from cluster_tools.grouping import admin, keywords


@admin
@keywords("revoke", "kick", "delete", "unenroll")
@click.command("remove-user")
@click.argument("user")
@click.argument("account", shell_complete=completion.complete_accounts)
@click.option("-y", "--yes", is_flag=True, help="Skip the confirmation prompt.")
def remove_user(user: str, account: str, yes: bool) -> None:
    """Remove a user's association with an account (via sacctmgr). Operator or coordinator only.

    Removes only the USER and ACCOUNT association, not the user's other accounts.
    Prompts for confirmation unless -y.

    \b
    Use cases:
      - Remove a former member from a lab's Slurm account.

    \b
    Inputs:
      USER       Username to remove.
      ACCOUNT    Slurm account to remove them from.
      -y, --yes  Skip the confirmation prompt.
    """
    if not yes:
        click.confirm(f"Remove user {user} from account {account}?", abort=True)
    code = process.stream(["sacctmgr", "-i", "remove", "user", user, f"account={account}"])
    if code:
        raise SystemExit(code)
