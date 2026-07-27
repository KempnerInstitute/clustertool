"""Storage commands."""

import click

from cluster_tools.commands.storage.home import home
from cluster_tools.commands.storage.quota import quota
from cluster_tools.commands.storage.scratch import scratch
from cluster_tools.commands.storage.stripe import stripe
from cluster_tools.commands.storage.usage import usage


@click.group()
def storage() -> None:
    """Inspect storage quotas and usage."""


storage.add_command(quota)
storage.add_command(home)
storage.add_command(usage)
storage.add_command(scratch)
storage.add_command(stripe)
