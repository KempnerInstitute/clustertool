"""account top-users command."""

import click

from cluster_tools import process
from cluster_tools.grouping import keywords


@keywords("heaviest", "hogs", "leaderboard", "biggest")
@click.command("top-users")
@click.argument("account")
def top_users(account: str) -> None:
    """Rank an account's members by raw usage (via sshare).

    Shows each member's RawUsage (the fairshare usage counter), highest first.

    \b
    Use cases:
      - See who in a lab has consumed the most recently.

    \b
    Inputs:
      ACCOUNT  Slurm account (e.g. kempner_dev).
    """
    usage: dict[str, int] = {}
    for line in process.run(["sshare", "-h", "--account=" + account, "--all"]).splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[4].isdigit():
            user, raw = parts[1], int(parts[4])
            usage[user] = max(usage.get(user, 0), raw)
    if not usage:
        click.echo(f"No usage rows for account '{account}'.")
        return
    click.echo(f"{'User':<18}{'RawUsage':>16}")
    for user, raw in sorted(usage.items(), key=lambda kv: kv[1], reverse=True):
        click.echo(f"{user:<18}{raw:>16}")
