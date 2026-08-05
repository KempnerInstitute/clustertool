"""account fairshare command."""

import os
import pwd

import click

from clustertool import completion, process, slurm
from clustertool.grouping import keywords

_FORMAT = "Account%-24,User%-20,Partition%-24,RawShares,NormShares,RawUsage,EffectvUsage,FairShare"
"""Widths wide enough for real names, since sshare's defaults clip at 10 and 12.

Two partitions whose names agree in their first twelve characters, such as
kempner_h100_priority and kempner_h100_priority3, are otherwise printed
identically, which defeats the -m flag that asks for them.
"""


@keywords("share", "rank", "weight")
@click.command("fairshare")
@click.argument("account", required=False, shell_complete=completion.complete_accounts)
@click.option("-u", "--user", default=None, help="User to look up (default: you).")
def fairshare(account: str | None, user: str | None) -> None:
    """Show fairshare standing and priority (via sshare).

    With an ACCOUNT, show every member's shares and usage for that account.
    Otherwise show your own fairshare across the accounts you belong to.

    FairShare is the factor the priority plugin multiplies in, from 0 to 1, and
    higher means higher priority. It is not the adjacent EffectvUsage column,
    which is the usage that produced it. RawUsage is billing-TRES-seconds and
    decays with the site's PriorityDecayHalfLife, so it is a recent-use figure
    rather than a lifetime total and is not comparable between two clusters.

    A partition row whose RawShares reads parent inherits the account's shares,
    and its FairShare is what governs jobs on that partition. Under Slurm's
    default fair-tree the NormShares and EffectvUsage columns are normalized
    within each level rather than against the root, so the same table means
    something different at a site that has not set NO_FAIR_TREE.

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
        cmd = ["sshare", "--account=" + account, "-a", "-m", "-o", _FORMAT]
    else:
        target = user or pwd.getpwuid(os.getuid()).pw_name
        if not slurm.user_exists(target):
            raise click.ClickException(f"no such user on this host: {target}")
        cmd = ["sshare", "-U", "-u", target, "-m", "-o", _FORMAT]
    process.passthrough(cmd, "'sshare' failed")
