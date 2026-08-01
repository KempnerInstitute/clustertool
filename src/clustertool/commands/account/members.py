"""account members command."""

import click

from clustertool import completion, slurm
from clustertool.grouping import keywords


@keywords("who", "roster", "people")
@click.command("members")
@click.argument(
    "account_name",
    metavar="ACCOUNT",
    required=False,
    shell_complete=completion.complete_accounts,
)
@click.option(
    "--all",
    "all_accounts",
    is_flag=True,
    help="List every Kempner lab account and its members as CSV.",
)
def members(account_name: str | None, all_accounts: bool) -> None:
    """List the users in a Slurm fairshare account.

    With --all, list every Kempner lab account (from the kempner partition's
    allowed accounts) and its members as CSV: account,username,full_name.

    \b
    Use cases:
      - See who belongs to a lab's Slurm account.
      - Export a full account/user/name roster with --all.

    \b
    Inputs:
      ACCOUNT  Slurm account name (e.g. kempner_dev). Omit when using --all.
      --all    List all Kempner lab accounts and members as CSV.
    """
    if all_accounts:
        accounts = [a for a in slurm.partition_accounts("kempner") if a.startswith("kempner_")]
        if not accounts:
            raise click.ClickException(
                "could not determine lab accounts from the kempner partition"
            )
        pairs = []
        users = set()
        for account in sorted(accounts):
            for user in slurm.account_members(account):
                pairs.append((account, user))
                users.add(user)
        full_names = slurm.user_fullnames(sorted(users))
        click.echo("account,username,full_name")
        for account, user in pairs:
            click.echo(f"{account},{user},{full_names.get(user, '')}")
        return

    if not account_name:
        raise click.ClickException("give an ACCOUNT or use --all")
    if not slurm.account_exists(account_name):
        raise click.ClickException(f"account '{account_name}' not found")
    names = slurm.account_members(account_name)
    click.echo(f"Members of {account_name} ({len(names)}):")
    for name in names:
        click.echo(f"  {name}")
