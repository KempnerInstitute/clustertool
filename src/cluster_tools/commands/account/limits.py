"""account limits command."""

import os

import click

from cluster_tools import process
from cluster_tools.grouping import keywords

_FORMAT = "Account,User,Partition,QOS,Priority,GrpTRES,MaxTRES"


@keywords("cap", "quota", "restrictions", "maximum")
@click.command("limits")
@click.argument("account", required=False)
@click.option("-u", "--user", default=None, help="User to look up (default: you).")
def limits(account: str | None, user: str | None) -> None:
    """Show account associations: QOS, partitions, and limits (via sacctmgr).

    With an ACCOUNT, show that account's associations; otherwise show yours.

    \b
    Use cases:
      - See which QOS and partitions an account may use.
      - Check configured TRES limits for a lab.

    \b
    Inputs:
      ACCOUNT      Slurm account. Omit to show your own associations.
      -u, --user   User to look up (default: current user).
    """
    where = f"account={account}" if account else f"user={user or os.environ.get('USER', '')}"
    cmd = ["sacctmgr", "show", "assoc", where, "format=" + _FORMAT]
    code = process.stream(cmd)
    if code:
        raise SystemExit(code)
