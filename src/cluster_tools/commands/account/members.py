"""account members command."""

import click

from cluster_tools import slurm


@click.command("members")
@click.argument("account_name", metavar="ACCOUNT")
def members(account_name: str) -> None:
    """List the users in a Slurm fairshare account.

    \b
    Use cases:
      - See who belongs to a lab's Slurm account.
      - Audit account membership.

    \b
    Inputs:
      ACCOUNT  Slurm account name (e.g. kempner_dev).
    """
    if not slurm.account_exists(account_name):
        raise click.ClickException(f"account '{account_name}' not found")
    names = slurm.account_members(account_name)
    click.echo(f"Members of {account_name} ({len(names)}):")
    for name in names:
        click.echo(f"  {name}")
