"""QoS inspection and administration commands."""

import click

from cluster_tools.commands.qos.create import create
from cluster_tools.commands.qos.delete import delete
from cluster_tools.commands.qos.holders import holders
from cluster_tools.commands.qos.modify import modify
from cluster_tools.grouping import SectionedGroup


@click.group(cls=SectionedGroup)
def qos() -> None:
    """Slurm QoS: who holds them, and (admin) provisioning their limits."""


qos.add_command(holders)
qos.add_command(create)
qos.add_command(modify)
qos.add_command(delete)
