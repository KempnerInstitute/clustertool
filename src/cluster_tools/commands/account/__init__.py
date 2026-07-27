"""Account commands."""

import click

from cluster_tools.commands.account.fairshare import fairshare
from cluster_tools.commands.account.limits import limits
from cluster_tools.commands.account.members import members
from cluster_tools.commands.account.usage import usage


@click.group()
def account() -> None:
    """Inspect Slurm accounts."""


account.add_command(members)
account.add_command(fairshare)
account.add_command(usage)
account.add_command(limits)
