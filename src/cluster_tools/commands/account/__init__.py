"""Account commands."""

import click

from cluster_tools.commands.account.members import members


@click.group()
def account() -> None:
    """Inspect Slurm accounts."""


account.add_command(members)
