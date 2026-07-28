"""Storage commands."""

import click

from cluster_tools.commands.storage.home import home
from cluster_tools.commands.storage.inodes import inodes
from cluster_tools.commands.storage.quota import quota
from cluster_tools.commands.storage.scratch import scratch
from cluster_tools.commands.storage.stripe import stripe
from cluster_tools.commands.storage.usage import usage
from cluster_tools.grouping import SectionedGroup


@click.group(cls=SectionedGroup)
def storage() -> None:
    """Storage quotas, usage, and Lustre striping."""


storage.add_command(quota)
storage.add_command(home)
storage.add_command(usage)
storage.add_command(scratch)
storage.add_command(stripe)
storage.add_command(inodes)
