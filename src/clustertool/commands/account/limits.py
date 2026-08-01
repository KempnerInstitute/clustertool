"""account limits command."""

import os

import click

from clustertool import completion, process, slurm
from clustertool.grouping import keywords

_COLUMNS = (
    ("Account", 30),
    ("User", 24),
    ("Partition", 30),
    ("QOS", 70),
    ("Priority", 0),
    ("GrpTRES", 26),
    ("MaxTRES", 26),
)
_WIDENED = "QOS"


def _format(where: str) -> str:
    """Return the sacctmgr format string, widening QOS to fit the longest list.

    sacctmgr truncates a column to the width it is given without marking that it
    did, so a user holding many QoS would silently see only the first few.
    """
    widest = 0
    code, out, _ = process.probe(["sacctmgr", "-n", "-P", "show", "assoc", where, "format=QOS"])
    if code == 0:
        widest = max((len(line.strip()) for line in out.splitlines()), default=0)
    return ",".join(
        name if not width else f"{name}%-{max(width, widest) if name == _WIDENED else width}"
        for name, width in _COLUMNS
    )


@keywords("cap", "quota", "restrictions", "maximum")
@click.command("limits")
@click.argument("account", required=False, shell_complete=completion.complete_accounts)
@click.option("-u", "--user", default=None, help="User to look up (default: you).")
def limits(account: str | None, user: str | None) -> None:
    """Show account associations: QoS, partitions, and limits (via sacctmgr).

    With an ACCOUNT, show that account's associations; otherwise show yours. The
    QoS column is widened to the longest list in the result, since sacctmgr
    truncates a column silently rather than marking that it did.

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
    cmd = ["sacctmgr", "show", "assoc", where, "format=" + _format(where)]
    process.passthrough(cmd, "'sacctmgr show assoc' failed")
