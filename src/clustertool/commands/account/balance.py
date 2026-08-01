"""account balance command."""

import click

from clustertool import completion, slurm
from clustertool.grouping import keywords


@keywords("fairshare", "over-served", "under-served", "usage", "share")
@click.command("balance")
@click.argument("account", required=False, shell_complete=completion.complete_accounts)
@click.option(
    "-n",
    "--top",
    type=click.IntRange(min=1),
    default=10,
    show_default=True,
    help="Rows per ranking.",
)
def balance(account: str | None, top: int) -> None:
    """Rank accounts by fairshare balance: effective usage vs normalized share.

    A ratio of effective usage to normalized share above 1 means an account is
    over-served (drawing more than its share); below 1 means under-served. Shows
    the most over- and under-served accounts. An account with shares and no usage
    is the most under-served there is, so it ranks at a ratio of zero rather than
    being left out. Point-in-time only, since sshare keeps no history.

    The ranking compares accounts against each other, which holds where shares are
    normalized cluster-wide. Under Slurm's default PriorityFlags=FAIR_TREE those
    figures are normalized within each level instead, so at a site with nested
    accounts compare siblings rather than the whole list.

    \b
    Use cases:
      - See which labs are drawing more than their fair share right now.
      - Find under-served accounts that are due more scheduling priority.

    \b
    Inputs:
      ACCOUNT    Narrow to one account subtree (optional).
      -n, --top  Rows to show per ranking (default 10).
    """
    if account and not slurm.account_exists(account):
        raise click.ClickException(f"account '{account}' not found")
    accounts = slurm.account_shares(account)
    ranked = [a for a in accounts if a["norm_shares"] and a["norm_shares"] > 0]
    for entry in ranked:
        entry["ratio"] = entry["effectv_usage"] / entry["norm_shares"]
    if not ranked:
        raise click.ClickException("no accounts with shares to rank")
    over = sorted(ranked, key=lambda a: a["ratio"], reverse=True)[:top]
    under = sorted(ranked, key=lambda a: a["ratio"])[:top]
    with_usage = sum(1 for entry in ranked if entry["raw_usage"] > 0)

    click.echo(f"Fairshare balance: {len(ranked)} account(s) with shares, {with_usage} with usage")

    def table(title: str, rows: list) -> None:
        if not rows:
            return
        click.echo()
        click.echo(f"{title}:")
        click.echo(f"  {'Account':<28}{'NormShare':>12}{'EffUsage':>12}{'Ratio':>9}")
        for entry in rows:
            click.echo(
                f"  {entry['account']:<28}{entry['norm_shares']:>12.6f}"
                f"{entry['effectv_usage']:>12.6f}{entry['ratio']:>9.2f}"
            )

    table("most over-served (usage above share)", over)
    if len(ranked) > 1:
        table("most under-served (usage below share)", under)
    click.echo()
    click.echo("note: point-in-time snapshot; sshare keeps no history")
