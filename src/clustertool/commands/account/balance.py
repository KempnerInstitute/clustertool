"""account balance command."""

import click

from clustertool import completion, slurm
from clustertool.grouping import keywords


@keywords("fairshare", "over-served", "under-served", "usage", "share")
@click.command("balance")
@click.argument("account", required=False, shell_complete=completion.complete_accounts)
@click.option("-n", "--top", type=int, default=10, show_default=True, help="Rows per ranking.")
def balance(account: str | None, top: int) -> None:
    """Rank accounts by fairshare balance: effective usage vs normalized share.

    A ratio of effective usage to normalized share above 1 means an account is
    over-served (drawing more than its share); below 1 means under-served. Shows
    the most over- and under-served accounts. Point-in-time only, since sshare
    keeps no history.

    \b
    Use cases:
      - See which labs are drawing more than their fair share right now.
      - Find under-served accounts that are due more scheduling priority.

    \b
    Inputs:
      ACCOUNT    Narrow to one account subtree (optional).
      -n, --top  Rows to show per ranking (default 10).
    """
    accounts = slurm.account_shares(account)
    usable = [a for a in accounts if a["norm_shares"] and a["norm_shares"] > 0]
    ranked = []
    for entry in usable:
        usage = entry["effectv_usage"]
        if usage and usage > 0:
            entry["ratio"] = usage / entry["norm_shares"]
            ranked.append(entry)
    over = sorted(ranked, key=lambda a: a["ratio"], reverse=True)[:top]
    under = sorted(ranked, key=lambda a: a["ratio"])[:top]

    click.echo(f"Fairshare balance: {len(usable)} account(s) with shares, {len(ranked)} with usage")

    def table(title: str, rows: list) -> None:
        if not rows:
            return
        click.echo()
        click.echo(f"{title}:")
        click.echo(
            f"  {'Account':<24}{'NormShare':>12}{'EffUsage':>12}{'Ratio':>9}{'FairShare':>11}"
        )
        for entry in rows:
            share = f"{entry['fairshare']:.4f}" if entry["fairshare"] is not None else "-"
            click.echo(
                f"  {entry['account']:<24}{entry['norm_shares']:>12.6f}"
                f"{entry['effectv_usage']:>12.6f}{entry['ratio']:>9.2f}{share:>11}"
            )

    table("most over-served (usage above share)", over)
    table("most under-served (usage below share)", under)
    click.echo()
    click.echo("note: point-in-time snapshot; sshare keeps no history")
