"""Storage commands."""

import click

from clustertool.commands.storage.home import home
from clustertool.commands.storage.lfs_inodes import lfs_inodes
from clustertool.commands.storage.lfs_stripe import lfs_stripe
from clustertool.commands.storage.quota import quota
from clustertool.commands.storage.scratch import scratch
from clustertool.commands.storage.vast_usage import vast_usage
from clustertool.grouping import SectionedGroup


@click.group(cls=SectionedGroup)
def storage() -> None:
    """Storage quotas, usage, and Lustre striping."""


storage.add_command(quota)
storage.add_command(home)
storage.add_command(vast_usage)
storage.add_command(scratch)
storage.add_command(lfs_stripe)
storage.add_command(lfs_inodes)
