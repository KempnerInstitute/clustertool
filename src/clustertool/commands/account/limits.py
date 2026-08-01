"""account limits command."""

import os
import pwd

import click

from clustertool import completion, process, slurm
from clustertool.grouping import keywords

_COLUMNS = (
    ("Account", 30),
    ("User", 24),
    ("Partition", 30),
    ("QOS", 70),
    ("DefaultQOS", 20),
    ("Priority", 0),
    ("GrpTRES", 26),
    ("MaxTRES", 26),
)


def _widths(where: str) -> dict[str, int]:
    """Return the longest value each column holds in this result, or {} if unknown.

    One parsable query answers for every column at once, so a value wider than a
    default cannot be clipped. A failed or empty query yields nothing and leaves
    the defaults in force.
    """
    sized = [name for name, width in _COLUMNS if width]
    code, out, _ = process.probe(
        ["sacctmgr", "-n", "-P", "show", "assoc", where, "format=" + ",".join(sized)]
    )
    if code != 0:
        return {}
    widest: dict[str, int] = {}
    for line in out.splitlines():
        for name, value in zip(sized, line.split("|"), strict=False):
            widest[name] = max(widest.get(name, 0), len(value.strip()))
    return widest


def _format(where: str) -> str:
    """Return the sacctmgr format string, widened to fit this result's values.

    sacctmgr clips a column to the width it is given and marks the cut with a
    trailing plus, so an over-long QoS list or a typed GRES limit would be shown
    unusable rather than wrong. A column is only ever widened, never narrowed.
    """
    widest = _widths(where)
    return ",".join(
        name if not width else f"{name}%-{max(width, widest.get(name, 0))}"
        for name, width in _COLUMNS
    )


@keywords("cap", "quota", "restrictions", "maximum")
@click.command("limits")
@click.argument("account", required=False, shell_complete=completion.complete_accounts)
@click.option("-u", "--user", default=None, help="User to look up (default: you).")
def limits(account: str | None, user: str | None) -> None:
    """Show account associations: QoS, partitions, and limits (via sacctmgr).

    With an ACCOUNT, show that account's associations; otherwise show yours.
    DefaultQOS is listed alongside QOS, since which of several a job gets without
    --qos is not derivable from the list. Every column is widened to fit the
    values in the result, because sacctmgr otherwise clips at its stated width
    and marks the cut with a trailing plus.

    \b
    Use cases:
      - See which QoS and partitions an account may use.
      - Check configured TRES limits for a lab.

    \b
    Inputs:
      ACCOUNT      Slurm account. Omit to show your own associations.
      -u, --user   User to look up (default: current user).
    """
    account = account.strip() if account is not None else None
    user = user.strip() if user is not None else None
    if account is not None and user is not None:
        raise click.UsageError("give either ACCOUNT or --user, not both")
    if account is not None:
        if not slurm.account_exists(account):
            raise click.ClickException(f"account {account!r} not found")
        where = f"account={account}"
    else:
        target = user if user is not None else pwd.getpwuid(os.getuid()).pw_name
        if user is not None and not slurm.user_exists(user):
            raise click.ClickException(f"no such user: {user!r}")
        where = f"user={target}"
    cmd = ["sacctmgr", "show", "assoc", where, "format=" + _format(where)]
    process.passthrough(cmd, "'sacctmgr show assoc' failed")
