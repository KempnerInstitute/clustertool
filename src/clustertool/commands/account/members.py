"""account members command."""

import click

from clustertool import completion, site, slurm
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
    help="List every lab account and its members as CSV.",
)
def members(account_name: str | None, all_accounts: bool) -> None:
    """List the users in a Slurm fairshare account.

    With --all, list every lab account and its members as CSV:
    account,username,full_name. Lab accounts are the ones allowed on the site's
    roster partition whose name carries the site's lab prefix, both set under
    [accounts] in the site config.

    \b
    Use cases:
      - See who belongs to a lab's Slurm account.
      - Export a full account/user/name roster with --all.

    \b
    Inputs:
      ACCOUNT  Slurm account name (e.g. kempner_dev). Omit when using --all.
      --all    List all lab accounts and members as CSV.
    """
    if all_accounts:
        roster = site.roster_partition()
        prefix = site.lab_account_prefix()
        accounts = [a for a in slurm.partition_accounts(roster) if a.startswith(prefix)]
        if not accounts:
            raise click.ClickException(
                f"could not determine lab accounts from the '{roster}' partition"
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
