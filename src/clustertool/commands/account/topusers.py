"""account top-users command."""

import click

from clustertool import completion, process, slurm
from clustertool.grouping import keywords


@keywords("heaviest", "hogs", "leaderboard", "biggest")
@click.command("top-users")
@click.argument("account", shell_complete=completion.complete_accounts)
def top_users(account: str) -> None:
    """Rank an account's members by raw usage (via sshare).

    Shows each member's RawUsage (the fairshare usage counter), highest first.

    \b
    Use cases:
      - See who in a lab has consumed the most recently.

    RAWUSAGE is TRES-seconds, or CPU-seconds where the cluster sets no
    TRESBillingWeights, summed over the user's associations in the account. It
    decays with the cluster's PriorityDecayHalfLife, so it reflects recent use
    rather than all time.

    \b
    Inputs:
      ACCOUNT  Slurm account.
    """
    if not slurm.account_exists(account):
        raise click.ClickException(f"account '{account}' not found")
    code, out, err = process.probe(
        ["sshare", "-h", "-P", "-o", "User,RawUsage", f"--account={account}", "--all"]
    )
    if code:
        raise click.ClickException(f"'sshare' failed for {account}: {err.strip() or code}")

    usage: dict[str, int] = {}
    for line in out.splitlines():
        parts = line.split("|")
        if len(parts) != 2:
            continue
        user, raw = parts[0].strip(), parts[1].strip()
        if user and raw.isdigit():
            usage[user] = usage.get(user, 0) + int(raw)
    if not usage:
        click.echo(f"No usage rows for account '{account}'.")
        return
    width = max(len("USER"), *(len(user) for user in usage)) + 2
    click.echo(f"{'USER':<{width}}{'RAWUSAGE':>16}")
    for user, raw in sorted(usage.items(), key=lambda kv: kv[1], reverse=True):
        click.echo(f"{user:<{width}}{raw:>16}")
