"""account fairshare command."""

import os

import click

from clustertool import completion, process, slurm
from clustertool.grouping import keywords


@keywords("share", "rank", "weight")
@click.command("fairshare")
@click.argument("account", required=False, shell_complete=completion.complete_accounts)
@click.option("-u", "--user", default=None, help="User to look up (default: you).")
def fairshare(account: str | None, user: str | None) -> None:
    """Show fairshare standing and priority (via sshare).

    With an ACCOUNT, show every member's shares and usage for that account.
    Otherwise show your own fairshare across the accounts you belong to. The
    FairShare column is the effective score (higher means higher priority).

    \b
    Use cases:
      - See your priority standing and why jobs may be deprioritized.
      - Compare members' usage within a lab account.

    \b
    Inputs:
      ACCOUNT      Slurm account (e.g. kempner_dev). Omit for your own standing.
      -u, --user   User to look up (default: current user).
    """
    if account and user:
        raise click.UsageError("give either ACCOUNT or --user, not both")
    if account:
        if not slurm.account_exists(account):
            raise click.ClickException(f"account '{account}' not found")
        cmd = ["sshare", "--account=" + account, "-a", "-m"]
    else:
        target = user or os.environ.get("USER", "")
        if not target:
            raise click.ClickException("no user to look up: give --user, or set $USER")
        cmd = ["sshare", "-U", "-u", target, "-m"]
    if process.stream(cmd):
        raise click.ClickException("'sshare' failed")
