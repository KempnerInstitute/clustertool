"""account limits command."""

import os

import click

from clustertool import completion, process, slurm
from clustertool.grouping import keywords

_FORMAT = "Account%-30,User%-24,Partition%-30,QOS%-70,Priority,GrpTRES%-26,MaxTRES%-26"


@keywords("cap", "quota", "restrictions", "maximum")
@click.command("limits")
@click.argument("account", required=False, shell_complete=completion.complete_accounts)
@click.option("-u", "--user", default=None, help="User to look up (default: you).")
def limits(account: str | None, user: str | None) -> None:
    """Show account associations: QoS, partitions, and limits (via sacctmgr).

    With an ACCOUNT, show that account's associations; otherwise show yours.

    \b
    Use cases:
      - See which QoS and partitions an account may use.
      - Check configured TRES limits for a lab.

    \b
    Inputs:
      ACCOUNT      Slurm account. Omit to show your own associations.
      -u, --user   User to look up (default: current user).
    """
    if account and user:
        raise click.UsageError("give either ACCOUNT or --user, not both")
    if account:
        if not slurm.account_exists(account):
            raise click.ClickException(f"account '{account}' not found")
        where = f"account={account}"
    else:
        target = user or os.environ.get("USER", "")
        if not target:
            raise click.ClickException("no user to look up: give --user, or set $USER")
        where = f"user={target}"
    cmd = ["sacctmgr", "show", "assoc", where, "format=" + _FORMAT]
    process.passthrough(cmd, "'sacctmgr show assoc' failed")
