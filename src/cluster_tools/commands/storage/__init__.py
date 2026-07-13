"""Storage commands."""

import click

from cluster_tools.commands.storage.quota import quota


@click.group()
def storage() -> None:
    """Inspect storage quotas."""


storage.add_command(quota)
