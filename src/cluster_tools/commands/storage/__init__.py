"""Storage commands."""

import click

from cluster_tools.commands.storage.home import home
from cluster_tools.commands.storage.lfs_inodes import lfs_inodes
from cluster_tools.commands.storage.lfs_stripe import lfs_stripe
from cluster_tools.commands.storage.quota import quota
from cluster_tools.commands.storage.scratch import scratch
from cluster_tools.commands.storage.usage import usage
from cluster_tools.grouping import SectionedGroup


@click.group(cls=SectionedGroup)
def storage() -> None:
    """Storage quotas, usage, and Lustre striping."""


storage.add_command(quota)
storage.add_command(home)
storage.add_command(usage)
storage.add_command(scratch)
storage.add_command(lfs_stripe)
storage.add_command(lfs_inodes)
