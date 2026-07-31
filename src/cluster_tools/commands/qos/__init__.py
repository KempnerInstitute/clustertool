"""QoS inspection and administration commands."""

import click

from cluster_tools.commands.qos.create import create
from cluster_tools.commands.qos.delete import delete
from cluster_tools.commands.qos.grant import grant
from cluster_tools.commands.qos.holders import holders
from cluster_tools.commands.qos.modify import modify
from cluster_tools.commands.qos.retire import retire
from cluster_tools.commands.qos.revoke import revoke
from cluster_tools.commands.qos.sync import sync
from cluster_tools.grouping import SectionedGroup


@click.group(cls=SectionedGroup)
def qos() -> None:
    """Slurm QoS: who holds them, and (admin) provisioning and assignment."""


qos.add_command(holders)
qos.add_command(create)
qos.add_command(modify)
qos.add_command(delete)
qos.add_command(grant)
qos.add_command(revoke)
qos.add_command(retire)
qos.add_command(sync)
