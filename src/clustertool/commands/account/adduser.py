"""account add-user command."""

import click

from clustertool import completion, process
from clustertool.grouping import admin, keywords


@admin
@keywords("grant", "join", "access", "enroll")
@click.command("add-user")
@click.argument("user")
@click.argument("account", shell_complete=completion.complete_accounts)
@click.option("--fairshare", default="parent", show_default=True, help="Fairshare value.")
@click.option("-y", "--yes", is_flag=True, help="Skip the confirmation prompt.")
def add_user(user: str, account: str, fairshare: str, yes: bool) -> None:
    """Add a user to a fairshare account (via sacctmgr). Operator or coordinator only.

    Prompts for confirmation unless -y is given.

    \b
    Use cases:
      - Grant a new lab member access to the lab's Slurm account.

    \b
    Inputs:
      USER         Username to add.
      ACCOUNT      Slurm account to add them to.
      --fairshare  Fairshare value (default parent).
      -y, --yes    Skip the confirmation prompt.
    """
    if not yes:
        click.confirm(f"Add user {user} to account {account} (fairshare={fairshare})?", abort=True)
    code = process.stream(
        [
            "sacctmgr",
            "-i",
            "add",
            "user",
            f"name={user}",
            f"account={account}",
            f"fairshare={fairshare}",
        ]
    )
    if code:
        raise SystemExit(code)
